"""Containment state in Postgres. The api is the only writer of these tables (ADR-008).

One audit row per proposal: created with the proposal, completed by the human decision and by
the agent's outcome report. That row is the metrics table the README charts.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from qgate_core.sql import queries

DECIDABLE = ("PROPOSED",)  # only a pending proposal can be approved, amended or rejected


class Proposal(BaseModel):
    thread_id: uuid.UUID
    kind: str  # WINDOW | LOT | SINGLE | NONE
    station_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    lot_ids: list[str] = Field(default_factory=list)
    vins: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reason: str
    draft_order: str | None = None
    golden_id: str | None = None  # eval harness only
    state: str = "PROPOSED"  # ESCALATED for "no proposal"
    evidence: dict[str, Any] = Field(default_factory=dict)  # for the console's case view
    trigger_vin: str | None = None  # the failing vehicle; never released by an amendment


class Outcome(BaseModel):
    """What the agent reports after the gate (or instead of a proposal)."""

    state: str  # COMMITTED | COMMIT_PENDING | ESCALATED
    reason: str | None = None
    mes_ref: str | None = None
    latency_total_ms: int | None = None
    latency_llm_ms: int | None = None
    latency_non_llm_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


class Decision(BaseModel):
    action: str  # APPROVE | AMEND | REJECT
    actor: str
    reason: str | None = None
    station_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    lot_ids: list[str] | None = None
    vins: list[str] | None = None


def propose(conn: psycopg.Connection, p: Proposal, timeout: timedelta) -> uuid.UUID:
    cid = uuid.uuid4()
    now = datetime.now(UTC)
    conn.execute(
        "insert into qgate.containment (containment_id, thread_id, state, kind, station_id, "
        "window_start, window_end, lot_ids, vin_count, confidence, reason, draft_order, "
        "proposed_at, expires_at, idempotency_key, evidence, trigger_vin) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            cid,
            p.thread_id,
            p.state,
            p.kind,
            p.station_id,
            p.window_start,
            p.window_end,
            p.lot_ids,
            len(p.vins),
            p.confidence,
            p.reason,
            p.draft_order,
            now,
            now + timeout if p.state == "PROPOSED" else None,
            cid,
            Jsonb(p.evidence),
            p.trigger_vin,
        ),
    )
    _set_vins(conn, cid, p.vins)
    conn.execute(
        "insert into qgate.containment_audit (containment_id, thread_id, golden_id, proposed, "
        "decided, diff, decision, actor) values (%s, %s, %s, %s, '{}', '{}', %s, 'agent')",
        (
            cid,
            p.thread_id,
            p.golden_id,
            Jsonb(p.model_dump(mode="json")),
            "PENDING" if p.state == "PROPOSED" else p.state,
        ),
    )
    conn.commit()
    return cid


def get(conn: psycopg.Connection, cid: uuid.UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "select * from qgate.containment where containment_id = %s", (cid,)
        ).fetchone()
        if row is None:
            return None
        row["vins"] = [
            r["vin"]
            for r in cur.execute(
                "select vin from qgate.containment_vin where containment_id = %s order by vin",
                (cid,),
            )
        ]
    return row


def _set_vins(conn: psycopg.Connection, cid: uuid.UUID, vins: list[str]) -> None:
    conn.execute("delete from qgate.containment_vin where containment_id = %s", (cid,))
    with conn.cursor() as cur:
        cur.executemany(
            "insert into qgate.containment_vin values (%s, %s)", [(cid, v) for v in vins]
        )
    conn.execute(
        "update qgate.containment set vin_count = %s where containment_id = %s", (len(vins), cid)
    )


def scope_vins(conn: psycopg.Connection, row: dict[str, Any]) -> list[str]:
    """The vehicles a row's bounds hold, recomputed from the build events (never trusted from a
    client) and always including the trigger: an amendment may narrow, never release the failing
    car."""
    q, kind, st = queries("window"), row["kind"], row["station_id"]
    if kind == "WINDOW" and st and row["window_start"] and row["window_end"]:
        found = {
            r[0]
            for r in q.vins_in_window(
                conn, station_id=st, start=row["window_start"], end=row["window_end"]
            )
        }
    elif kind == "LOT" and st:
        found = {
            r[0] for lot in row["lot_ids"] for r in q.vins_by_lot(conn, station_id=st, lot_id=lot)
        }
    else:
        found = set()
    return sorted(found | ({row["trigger_vin"]} if row["trigger_vin"] else set()))


def list_by_state(conn: psycopg.Connection, state: str | None) -> list[dict[str, Any]]:
    """``state`` may be a comma-separated list (the console queue shows PROPOSED and ESCALATED)."""
    with conn.cursor(row_factory=dict_row) as cur:
        if state:
            return cur.execute(
                "select * from qgate.containment where state = any(%s) order by proposed_at desc",
                (state.split(","),),
            ).fetchall()
        return cur.execute(
            "select * from qgate.containment order by proposed_at desc limit 200"
        ).fetchall()


def list_unreported(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Decided by a human but never closed by the agent's report (it was down, or died between the
    gate and the plant write). The sweeper re-sends these decisions until the agent takes them."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "select c.* from qgate.containment c "
            "join qgate.containment_audit a using (containment_id) "
            "where c.state in ('APPROVED', 'AMENDED', 'REJECTED') and a.latency_total_ms is null "
            "order by c.decided_at"
        ).fetchall()


def audit(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "select * from qgate.containment_audit order by created_at desc limit 500"
        ).fetchall()


def record_outcome(conn: psycopg.Connection, cid: uuid.UUID, o: Outcome) -> bool:
    """Agent's report after the gate. Returns False if the containment does not exist."""
    updated = conn.execute(
        "update qgate.containment set state = %s, mes_ref = coalesce(%s, mes_ref), "
        "reason = coalesce(%s, reason) where containment_id = %s",
        (o.state, o.mes_ref, o.reason, cid),
    ).rowcount
    conn.execute(
        "update qgate.containment_audit set "
        "latency_total_ms = coalesce(%s, latency_total_ms), "
        "latency_llm_ms = coalesce(%s, latency_llm_ms), "
        "latency_non_llm_ms = coalesce(%s, latency_non_llm_ms), "
        "prompt_tokens = coalesce(%s, prompt_tokens), "
        "completion_tokens = coalesce(%s, completion_tokens), "
        "cost_usd = coalesce(%s, cost_usd) where containment_id = %s",
        (
            o.latency_total_ms,
            o.latency_llm_ms,
            o.latency_non_llm_ms,
            o.prompt_tokens,
            o.completion_tokens,
            o.cost_usd,
            cid,
        ),
    )
    conn.commit()
    return updated == 1


def decide(conn: psycopg.Connection, cid: uuid.UUID, d: Decision) -> dict[str, Any] | None:
    """Apply a human decision. Returns the updated row, or None if it was not decidable (409)."""
    with conn.cursor(row_factory=dict_row) as cur:
        current = cur.execute(
            "select * from qgate.containment where containment_id = %s for update", (cid,)
        ).fetchone()
    if current is None or current["state"] not in DECIDABLE:
        conn.rollback()
        return None
    state = {"APPROVE": "APPROVED", "AMEND": "AMENDED", "REJECT": "REJECTED"}[d.action]
    if d.action == "AMEND":
        conn.execute(
            "update qgate.containment set station_id = coalesce(%s, station_id), "
            "window_start = coalesce(%s, window_start), window_end = coalesce(%s, window_end), "
            "lot_ids = coalesce(%s, lot_ids) where containment_id = %s",
            (d.station_id, d.window_start, d.window_end, d.lot_ids, cid),
        )
        if d.vins is not None:
            _set_vins(conn, cid, d.vins)
        elif _diff(current, d):  # bounds moved: re-scope from the build events
            amended = get(conn, cid)
            assert amended is not None
            _set_vins(conn, cid, scope_vins(conn, amended))
    conn.execute(
        "update qgate.containment set state = %s, decided_at = now(), decided_by = %s "
        "where containment_id = %s",
        (state, d.actor, cid),
    )
    decided = d.model_dump(mode="json", exclude_none=True)
    diff = _diff(current, d)
    conn.execute(
        "update qgate.containment_audit set decided = %s, diff = %s, decision = %s, actor = %s "
        "where containment_id = %s",
        (Jsonb(decided), Jsonb(diff), d.action, d.actor, cid),
    )
    conn.commit()
    return get(conn, cid)


def _diff(before: dict[str, Any], d: Decision) -> dict[str, Any]:
    """Which bounds the human changed, as {field: {from, to}} — the widened/narrowed statistic."""
    out: dict[str, Any] = {}
    for field in ("station_id", "window_start", "window_end", "lot_ids"):
        new = getattr(d, field)
        if new is not None and new != before[field]:
            out[field] = {"from": _json(before[field]), "to": _json(new)}
    return out


def _json(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else v


def sweep_expired(conn: psycopg.Connection, now: datetime) -> list[uuid.UUID]:
    """PROPOSED past its deadline becomes EXPIRED. Never approves anything (ADR-003)."""
    rows = conn.execute(
        "update qgate.containment set state = 'EXPIRED', decided_at = %s, decided_by = 'system' "
        "where state = 'PROPOSED' and expires_at < %s returning containment_id",
        (now, now),
    ).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        conn.execute(
            "update qgate.containment_audit set decision = 'EXPIRED', actor = 'system' "
            "where containment_id = any(%s)",
            (ids,),
        )
    conn.commit()
    return ids
