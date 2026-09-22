"""The nine nodes of the triage graph (design §8.2).

Two kinds of function live here. Pure rules — ``route``, ``decide_bounds``,
``validate_hypotheses`` — take state and return a decision; they are what the unit tests pin.
Node closures — built by ``make_nodes(deps)`` — call tools and the model and return the state
they add. The model appears in ``hypothesise``, ``compose`` and ``escalate`` only (ADR-004).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from langgraph.types import interrupt
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from qgate_agent.llm import Ask
from qgate_agent.state import (
    Bounds,
    Explanation,
    HumanDecision,
    Hypotheses,
    Hypothesis,
    Order,
    TriageState,
)
from qgate_agent.tools import (
    check_bench,
    check_station_drift,
    find_correlated_failures,
    get_station_spec,
    get_vehicle_genealogy,
    vins_by_lot,
    vins_in_window,
)
from qgate_agent.tools.detect_client import HttpGetter
from qgate_agent.tools.mes import Breaker, post_hold
from qgate_core.pricing import Usage, cost_usd

BREAKER = Breaker()  # one per process: every triage worker learns the MES is down at once
NO_PATTERN = 1  # up to one earlier defect with the same code is noise, not a run (Gate 2)
LOT_SHARE = 0.8  # siblings this concentrated in one lot make it a lot problem
LOT_MIN = 3
LOT_SPREAD_TAKTS = 60  # siblings must span more than a lot block (25 vehicles) to implicate the lot
LOOKBACK = timedelta(days=3)  # how far back correlation and drift look from the trigger
PROMPT_VERSION = "1"


class HttpClient(Protocol):
    """The slice of ``httpx.Client`` the nodes use; Starlette's TestClient satisfies it too."""

    def get(self, url: str) -> Any: ...
    def post(self, url: str, *, json: Any = None, headers: Any = None) -> Any: ...
    def patch(self, url: str, *, json: Any = None) -> Any: ...


@dataclass
class Deps:
    ro: ConnectionPool  # agent_ro: the tools cannot write
    detect: HttpGetter
    api: HttpClient  # service token
    mes: HttpClient  # the plant's system, its own API key
    ask: Ask
    fault_map: dict[str, Any]


# ----------------------------------------------------------------------------- pure rules


def route(s: TriageState) -> str:
    """After drift_check: bench_alert | escalate | bound."""
    b = s["bench"]
    if not b.capable and b.method != "insufficient-data":  # unknown is not the same as bad
        return "bench_alert"
    if s["drift"].verdict in ("DRIFT", "STEP") and s["siblings"].n <= NO_PATTERN:
        return "escalate"  # the gauge says something changed, the line says nobody else failed
    return "bound"


def validate_hypotheses(h: Hypotheses, allowed: dict[str, list[str]]) -> list[Hypothesis]:
    """The model may rank the fault map's candidates, never add to them."""
    for x in h.ranked:
        if x.station_id not in allowed or x.characteristic_id not in allowed[x.station_id]:
            raise ValueError(f"{x.station_id}/{x.characteristic_id} is not a fault-map candidate")
    return h.ranked


def decide_bounds(
    s: TriageState,
    vins_by_lot: Callable[[str, str], list[str]],
    vins_in_window: Callable[[str, datetime, datetime], list[str]],
) -> Bounds:
    """Turn evidence into a concrete hold: by lot, by window, or the single vehicle."""
    station = s["hypotheses"][0].station_id
    sib, drift = s["siblings"], s["drift"]
    lot = sib.top_lot
    lot_like = sib.n >= LOT_MIN and lot is not None and sib.top_lot_share >= LOT_SHARE
    if lot is not None and lot_like and sib.spread_takts() > LOT_SPREAD_TAKTS:
        vins = vins_by_lot(station, lot)
        return Bounds(
            kind="LOT",
            station_id=station,
            lot_ids=[lot],
            vins=_with(vins, s["vin"]),
            confidence=round(0.5 + 0.5 * sib.top_lot_share, 2),
        )
    if drift.verdict in ("DRIFT", "STEP") and drift.onset is not None:
        end = s["eol_ts"]  # everything built up to the moment the trigger failed
        vins = vins_in_window(station, drift.onset, end)
        return Bounds(
            kind="WINDOW",
            station_id=station,
            window_start=drift.onset,
            window_end=end,
            vins=_with(vins, s["vin"]),
            confidence=drift.confidence,
        )
    return Bounds(kind="SINGLE", station_id=station, vins=[s["vin"]], confidence=0.6)


def _with(vins: list[str], vin: str) -> list[str]:
    return vins if vin in vins else [*vins, vin]


# ----------------------------------------------------------------------------- node closures


def make_nodes(deps: Deps) -> dict[str, Callable[[TriageState], dict[str, Any]]]:
    fm = deps.fault_map["faults"]

    def intake(s: TriageState) -> dict[str, Any]:
        codes = sorted({c.strip().upper() for c in s["fault_codes"] if c.strip()})
        unknown = [c for c in codes if c not in fm]
        if not codes or unknown:
            raise ValueError(f"unknown fault codes {unknown or s['fault_codes']}")
        return {
            "fault_codes": codes,
            "timings_ms": {},
            "errors": [],
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_ms": 0.0,
        }

    def genealogy(s: TriageState) -> dict[str, Any]:
        with deps.ro.connection() as conn:
            g = get_vehicle_genealogy(conn, s["vin"])
        if g.eol is None:
            raise ValueError(f"{s['vin']} has no end-of-line result to triage")
        # a manual trigger may omit the clock; the vehicle's own EOL time is the honest one
        return {"genealogy": g, **({} if s.get("eol_ts") else {"eol_ts": g.eol.tested_at})}

    def hypothesise(s: TriageState) -> dict[str, Any]:
        candidates = [c for code in s["fault_codes"] for c in fm[code]["candidates"]]
        allowed = {c["station_id"]: list(c["characteristic_ids"]) for c in candidates}
        inputs = {
            "vin": s["vin"],
            "fault_codes": ", ".join(s["fault_codes"]),
            "candidates": "\n".join(
                f"- {c['station_id']} {c['characteristic_ids']} prior {c['prior']}: "
                f"{c['rationale']}"
                for c in candidates
            ),
            "oot_stations": ", ".join(s["genealogy"].out_of_tolerance_stations()) or "none",
        }
        answer, acct = _ask(deps, s, "hypothesise", inputs, Hypotheses)
        try:
            return {"hypotheses": validate_hypotheses(answer, allowed), **acct}
        except ValueError as e:  # the model went off the map: fall back to the authored order
            authored = [
                Hypothesis(
                    station_id=c["station_id"],
                    characteristic_id=c["characteristic_ids"][0],
                    reasoning=c["rationale"],
                )
                for c in candidates
            ]
            return {
                "hypotheses": authored,
                "errors": [*s.get("errors", []), f"hypothesise: {e}"],
                **acct,
            }

    def correlate(s: TriageState) -> dict[str, Any]:
        h = s["hypotheses"][0]
        with deps.ro.connection() as conn:
            sib = find_correlated_failures(
                conn,
                f"F-{h.station_id[-2:]}",
                h.station_id,
                s["eol_ts"] - LOOKBACK,
                s["eol_ts"],
                exclude_vin=s["vin"],
            )
        return {"siblings": sib}

    def drift_check(s: TriageState) -> dict[str, Any]:
        h = s["hypotheses"][0]
        start, end = s["eol_ts"] - LOOKBACK, s["eol_ts"] + timedelta(minutes=1)
        d = check_station_drift(deps.detect, h.station_id, h.characteristic_id, start, end)
        # the bench is judged on the EOL characteristics this vehicle actually failed; one
        # untrustworthy reading is enough to distrust the verdict
        g = s["genealogy"]
        bench_id = g.eol.bench_id if g.eol else "INLINE"
        eol_meas = g.visits[-1].measurements
        chars = [m.characteristic_id for m in eol_meas if m.out_of_tolerance] or [
            eol_meas[0].characteristic_id
        ]
        results = [check_bench(deps.detect, bench_id, c, start, end) for c in dict.fromkeys(chars)]
        bench = next((b for b in results if not b.capable), results[0])
        return {"drift": d, "bench": bench}

    def bound(s: TriageState) -> dict[str, Any]:
        with deps.ro.connection() as conn:
            b = decide_bounds(
                s,
                vins_by_lot=lambda st, lot: vins_by_lot(conn, st, lot),
                vins_in_window=lambda st, a, z: vins_in_window(conn, st, a, z),
            )
        return {"bounds": b}

    def compose(s: TriageState) -> dict[str, Any]:
        b = s["bounds"]
        with deps.ro.connection() as conn:
            spec = get_station_spec(conn, b.station_id or "")
        scope = (
            f"lot {', '.join(b.lot_ids)}"
            if b.kind == "LOT"
            else f"{b.window_start:%Y-%m-%d %H:%M} to {b.window_end:%Y-%m-%d %H:%M} UTC"
            if b.kind == "WINDOW"
            else "this vehicle only"
        )
        inputs = {
            "kind": b.kind,
            "station_id": b.station_id,
            "station_name": spec.name,
            "vin_count": len(b.vins),
            "scope": scope,
            "vin": s["vin"],
            "fault_codes": ", ".join(s["fault_codes"]),
            "evidence": f"{s['siblings'].n} other vehicles with the same code; "
            f"drift {s['drift'].verdict} ({s['drift'].severity}); "
            f"bench capable {s['bench'].capable}",
        }
        order, acct = _ask(deps, s, "compose", inputs, Order)
        text = order.text
        if (b.station_id or "") not in text or str(len(b.vins)) not in text:  # numbers must be ours
            text = f"Hold {len(b.vins)} vehicle(s) — station {b.station_id}, {scope}. " + text
        return {"draft_order": text, **acct}

    def submit(s: TriageState) -> dict[str, Any]:
        """Write the proposal. Its own node: a node that interrupts re-runs from its first line
        on resume, so any side effect before ``interrupt()`` would happen twice."""
        b = s["bounds"]
        r = deps.api.post(
            "/internal/containments",
            json={
                "thread_id": s["thread_id"],
                "kind": b.kind,
                "station_id": b.station_id,
                "window_start": _iso(b.window_start),
                "window_end": _iso(b.window_end),
                "lot_ids": b.lot_ids,
                "vins": b.vins,
                "confidence": b.confidence,
                "reason": f"{s['siblings'].n} siblings; "
                f"drift {s['drift'].verdict} {s['drift'].severity}",
                "draft_order": s["draft_order"],
                "golden_id": s.get("golden_id"),
            },
        )
        r.raise_for_status()
        return {"containment_id": r.json()["containment_id"], "outcome": "PROPOSED"}

    def gate(s: TriageState) -> dict[str, Any]:
        """Stop. Nothing continues without a human decision (ADR-003). Side-effect free."""
        decision = interrupt(
            {"containment_id": s["containment_id"], "draft_order": s["draft_order"]}
        )
        human = HumanDecision.model_validate(decision)
        bounds = s["bounds"]
        if human.decision == "AMEND" and human.bounds is not None:
            bounds = human.bounds.model_copy(update={"vins": _with(human.bounds.vins, s["vin"])})
        return {
            "human": human,
            "bounds": bounds,
            "outcome": "REJECTED" if human.decision == "REJECT" else "PROPOSED",
        }

    def commit(s: TriageState) -> dict[str, Any]:
        """The one write to the plant: idempotent on the containment id, retried, behind a
        breaker. "Not now" parks the containment instead of failing the thread."""
        b = s["bounds"]
        r = post_hold(
            deps.mes,
            BREAKER,
            s["containment_id"],
            {
                "external_ref": s["containment_id"],
                "station_id": b.station_id,
                "window_start": _iso(b.window_start),
                "window_end": _iso(b.window_end),
                "lot_ids": b.lot_ids,
                "vins": b.vins,
                "reason": s["draft_order"][:2000],
            },
        )
        if r is None:
            return {"outcome": "COMMIT_PENDING", "errors": [*s["errors"], "mes unavailable"]}
        r.raise_for_status()
        return {"mes_ref": r.json()["hold_ref"], "outcome": "COMMITTED"}

    def pending(s: TriageState) -> dict[str, Any]:
        """Tell the api the approved containment is parked; its sweeper will ask us to retry."""
        deps.api.patch(
            f"/internal/containments/{s['containment_id']}",
            json={"state": "COMMIT_PENDING", "reason": s["errors"][-1]},
        ).raise_for_status()
        return {}

    def retry_gate(s: TriageState) -> dict[str, Any]:
        """Wait for the sweeper's RETRY. Side-effect free, like ``gate``; resuming re-runs
        ``commit`` from its first line, which is exactly one more attempt."""
        interrupt({"containment_id": s["containment_id"], "waiting": "mes"})
        return {}

    def bench_alert(s: TriageState) -> dict[str, Any]:
        b = s["bench"]
        reason = (
            f"Bench {b.bench_id} is not capable (GRR {b.grr_pct}, "
            f"bias vs peers {b.bias_vs_peers}); the vehicle's readings cannot be trusted. "
            "Hold nothing; recalibrate."
        )
        return _no_proposal(deps, s, "NO_CONTAINMENT", reason)

    def escalate(s: TriageState) -> dict[str, Any]:
        inputs = {
            "vin": s["vin"],
            "fault_codes": ", ".join(s["fault_codes"]),
            "drift": f"{s['drift'].verdict} {s['drift'].severity}",
            "siblings": s["siblings"].n,
            "bench": f"capable={s['bench'].capable}",
        }
        why, acct = _ask(deps, s, "escalate", inputs, Explanation)
        return {**_no_proposal(deps, s, "ESCALATED", why.text), **acct}

    def report(s: TriageState) -> dict[str, Any]:
        """Close the audit row: final state plus what the run cost in time and tokens."""
        total = sum(s["timings_ms"].values())
        final = {"NO_CONTAINMENT": "ESCALATED"}.get(s["outcome"], s["outcome"])
        deps.api.patch(
            f"/internal/containments/{s['containment_id']}",
            json={
                "state": final,
                "mes_ref": s.get("mes_ref"),
                "latency_total_ms": int(total),
                "latency_llm_ms": int(s["llm_ms"]),
                "latency_non_llm_ms": int(total - s["llm_ms"]),
                "prompt_tokens": s["prompt_tokens"],
                "completion_tokens": s["completion_tokens"],
                "cost_usd": _cost(deps, s),
            },
        ).raise_for_status()
        return {}

    return {
        "intake": intake,
        "genealogy": genealogy,
        "hypothesise": hypothesise,
        "correlate": correlate,
        "drift_check": drift_check,
        "bound": bound,
        "compose": compose,
        "submit": submit,
        "gate": gate,
        "commit": commit,
        "pending": pending,
        "retry_gate": retry_gate,
        "bench_alert": bench_alert,
        "escalate": escalate,
        "report": report,
    }


def _no_proposal(deps: Deps, s: TriageState, outcome: str, reason: str) -> dict[str, Any]:
    """Record a decision *not* to propose, so abstentions are audited like proposals."""
    r = deps.api.post(
        "/internal/containments",
        json={
            "thread_id": s["thread_id"],
            "kind": "NONE",
            "state": "ESCALATED",
            "station_id": s["hypotheses"][0].station_id,
            "vins": [],
            "reason": reason,
            "golden_id": s.get("golden_id"),
        },
    )
    r.raise_for_status()
    return {"containment_id": r.json()["containment_id"], "outcome": outcome, "draft_order": reason}


def _ask[S: BaseModel](
    deps: Deps, s: TriageState, prompt_id: str, inputs: dict[str, Any], schema: type[S]
) -> tuple[S, dict[str, Any]]:
    """Call the model through the cassette layer; return the answer and the state update that
    accounts for its time and tokens (nodes must *return* updates, not mutate state)."""
    t0 = time.perf_counter()
    answer, usage = deps.ask(prompt_id, PROMPT_VERSION, inputs, schema)
    acct = {
        "llm_ms": s.get("llm_ms", 0.0) + (time.perf_counter() - t0) * 1000,
        "prompt_tokens": s.get("prompt_tokens", 0) + usage.prompt_tokens,
        "completion_tokens": s.get("completion_tokens", 0) + usage.completion_tokens,
    }
    return answer, acct


def _cost(deps: Deps, s: TriageState) -> float | None:
    return cost_usd(deps.ask.model.name, Usage(s["prompt_tokens"], s["completion_tokens"]))


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() if t else None
