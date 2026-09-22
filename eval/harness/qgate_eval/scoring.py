"""Scoring per docs/eval.md. Escapes are summed, never averaged."""

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

ABSTAIN = {"NONE", "ESCALATE"}


@dataclass(frozen=True)
class CaseResult:
    """What one golden produced; the inputs to scoring."""

    golden_id: str
    family: str
    expected: str  # the golden's decision
    decided: str  # the agent's containment kind, or ESCALATE / NONE
    affected: set[str]  # vehicles the correct containment should hold at trigger time
    held: set[str]  # vehicles committed to the plant (after amendment; empty if none)
    approved_unamended: bool
    abstained: bool
    latency_total_ms: int
    latency_llm_ms: int
    cost_usd: float | None
    proposed: set[str] | None = None  # what the agent offered at the gate
    rejected_by_human: bool = (
        False  # the human said no: the agent's proposal is judged, not the hold
    )


@dataclass(frozen=True)
class Score:
    case: CaseResult
    escapes: int
    precision: float
    recall: float
    decision_match: bool
    abstention_correct: bool | None  # None when abstention was neither expected nor done


def score(c: CaseResult) -> Score:
    # a human rejection is a human decision; escapes and recall would otherwise charge it to the
    # agent, so the proposal (what was *offered*) stands in for what was held
    held = c.proposed if c.rejected_by_human and c.proposed is not None else c.held
    hit = len(c.affected & held)
    return Score(
        case=c,
        escapes=len(c.affected - held),
        precision=hit / len(held) if held else (1.0 if not c.affected else 0.0),
        recall=hit / len(c.affected) if c.affected else 1.0,
        decision_match=c.decided == c.expected
        or (c.expected == "MULTI" and c.decided == "LOT"),  # see docs/eval.md
        # judged whenever the agent abstained or should have: wrongful abstention is a miss
        abstention_correct=(c.abstained and not c.affected)
        if (c.abstained or c.expected in ABSTAIN)
        else None,
    )


def summarise(scores: list[Score]) -> dict[str, Any]:
    by_family: dict[str, list[Score]] = defaultdict(list)
    for s in scores:
        by_family[s.case.family].append(s)
    return {**_block(scores), "by_family": {f: _block(v) for f, v in sorted(by_family.items())}}


def _block(scores: list[Score]) -> dict[str, Any]:
    n = len(scores)
    abst = [s.abstention_correct for s in scores if s.abstention_correct is not None]
    totals = [s.case.latency_total_ms for s in scores]
    llm = [s.case.latency_llm_ms for s in scores]
    costs = [s.case.cost_usd for s in scores if s.case.cost_usd is not None]
    return {
        "cases": n,
        "escapes": sum(s.escapes for s in scores),
        "precision": round(statistics.fmean(s.precision for s in scores), 4) if n else None,
        "recall": round(statistics.fmean(s.recall for s in scores), 4) if n else None,
        "decision_match": round(sum(s.decision_match for s in scores) / n, 4) if n else None,
        "agreement_rate": round(sum(s.case.approved_unamended for s in scores) / n, 4)
        if n
        else None,
        "abstention_correct_rate": round(sum(abst) / len(abst), 4) if abst else None,
        "latency_p50_ms": _pct(totals, 50),
        "latency_p95_ms": _pct(totals, 95),
        "latency_llm_p95_ms": _pct(llm, 95),
        "latency_non_llm_p95_ms": _pct([t - m for t, m in zip(totals, llm, strict=True)], 95),
        "cost_per_triage_usd": round(statistics.fmean(costs), 6) if costs else None,
    }


def _pct(values: list[int], p: int) -> int | None:
    if not values:
        return None
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return sorted(values)[k]
