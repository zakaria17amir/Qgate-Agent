"""Run the goldens through the in-process stack and score them (docs/eval.md)."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import psycopg

from qgate_eval.golden import Golden
from qgate_eval.scoring import CaseResult
from qgate_eval.stack import Stack
from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.stream import Run, generate

log = logging.getLogger("eval")
ROOT = Path(__file__).parents[3]
LINE = Line.load(ROOT / "scenarios" / "line.yaml")


def load_case(pg_url: str, g: Golden) -> tuple[Run, datetime]:
    """Regenerate the golden's run into an emptied database; returns it and the trigger's EOL
    time (what the consumer would pass as ``eol_ts``)."""
    run = generate(
        LINE,
        Scenario.load(ROOT / "scenarios" / f"{g.scenario}.yaml", LINE).model_copy(
            update={"seed": g.seed}
        ),
    )
    with psycopg.connect(pg_url) as conn:
        truncate_facts(conn)
        copy_run(conn, run)
        eol_ts = conn.execute(
            "select tested_at from qgate.fact_eol_result where vin = %s", (g.trigger.vin,)
        ).fetchone()
    assert eol_ts is not None
    return run, eol_ts[0]


def run_golden(stack: Stack, g: Golden, on_log: Callable[[str], None] = log.info) -> CaseResult:
    """Load the case, trigger the agent, act as the golden's human, read back what happened."""
    run, eol_ts = load_case(stack.pg_url, g)
    assert stack.agent is not None
    tid = stack.agent.post(
        "/triage",
        json={
            "vin": g.trigger.vin,
            "fault_codes": g.trigger.fault_codes,
            "eol_ts": eol_ts.isoformat(),
            "golden_id": g.id,
        },
    ).json()["thread_id"]
    snap = stack.agent.get(f"/threads/{tid}").json()
    cid = snap["containment_id"]
    approved_unamended = False
    if snap["status"] == "WAITING_GATE":
        approved_unamended = _act_as_human(stack, g, cid)
    elif snap["status"] != "DONE" or cid is None:
        # the graph failed before proposing anything: score it as a silent failure, not a crash
        on_log(f"{g.id}: thread ended in {snap['status']} (errors {snap['errors']})")
        return CaseResult(
            golden_id=g.id,
            family=g.family.value,
            expected=g.expected.decision.value,
            decided="FAILED",
            affected=_affected(g, run),
            held=set(),
            approved_unamended=False,
            abstained=False,
            latency_total_ms=0,
            latency_llm_ms=0,
            cost_usd=None,
        )

    row = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
    held = set(row["vins"]) if row["state"] == "COMMITTED" else set()
    audit = next(
        a
        for a in stack.api.get("/audit", headers=stack.human()).json()
        if a["containment_id"] == cid
    )
    proposed = set(audit["proposed"].get("vins", []))
    decided = (
        "ESCALATE"
        if row["kind"] == "NONE" and row["vin_count"] == 0 and snap["outcome"] == "ESCALATED"
        else "NONE"
        if row["kind"] == "NONE"
        else row["kind"]
    )
    return CaseResult(
        golden_id=g.id,
        family=g.family.value,
        expected=g.expected.decision.value,
        decided=decided,
        affected=_affected(g, run),
        held=held,
        proposed=proposed,
        approved_unamended=approved_unamended,
        rejected_by_human=row["state"] == "REJECTED",
        abstained=row["kind"] == "NONE",
        latency_total_ms=audit["latency_total_ms"] or 0,
        latency_llm_ms=audit["latency_llm_ms"] or 0,
        cost_usd=float(audit["cost_usd"]) if audit["cost_usd"] is not None else None,
    )


def _act_as_human(stack: Stack, g: Golden, cid: str) -> bool:
    """The golden says what a person would do at the gate; do exactly that through the api."""
    h = g.human
    if h.action == "REJECT":
        stack.api.post(
            f"/containments/{cid}/reject", json={"reason": h.reason}, headers=stack.human()
        )
        return False
    if h.action == "AMEND":
        row = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
        body: dict[str, object] = {"reason": h.reason}
        if h.amend_start_delta_takts is not None and row["window_start"]:
            from datetime import datetime

            start = datetime.fromisoformat(row["window_start"]) + timedelta(
                seconds=h.amend_start_delta_takts * LINE.takt_s
            )
            body["window_start"] = start.isoformat()
        stack.api.post(f"/containments/{cid}/amend", json=body, headers=stack.human())
        return False
    stack.api.post(f"/containments/{cid}/approve", json={"reason": h.reason}, headers=stack.human())
    return True


def _affected(g: Golden, run: Run) -> set[str]:
    """Vehicles the correct containment should hold at trigger time (docs/eval.md)."""
    trigger_seq = int(g.trigger.vin[3:])
    if g.expected.decision.value in ("NONE", "ESCALATE"):
        return set()
    if g.expected.decision.value == "SINGLE":
        return {g.trigger.vin}
    injected = {
        v for vins in run.truth.by_inject.values() for v in vins if int(v[3:]) <= trigger_seq
    }
    return injected | {g.trigger.vin}
