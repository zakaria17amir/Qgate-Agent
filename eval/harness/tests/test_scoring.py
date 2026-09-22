"""Scoring definitions from docs/eval.md, pinned."""

import pytest

from qgate_eval.scoring import CaseResult, score, summarise

pytestmark = pytest.mark.unit


def case(**kw: object) -> CaseResult:
    base: dict[str, object] = {
        "golden_id": "x",
        "family": "drift",
        "expected": "WINDOW",
        "decided": "WINDOW",
        "affected": {"a", "b", "c"},
        "held": {"a", "b", "c"},
        "approved_unamended": True,
        "abstained": False,
        "latency_total_ms": 1000,
        "latency_llm_ms": 600,
        "cost_usd": 0.001,
    }
    base.update(kw)
    return CaseResult(**base)  # type: ignore[arg-type]


def test_escapes_are_affected_vehicles_not_held() -> None:
    s = score(case(affected={"a", "b", "c"}, held={"a"}))
    assert s.escapes == 2 and s.precision == 1.0 and s.recall == pytest.approx(1 / 3)


def test_over_holding_costs_precision_not_escapes() -> None:
    s = score(case(affected={"a"}, held={"a", "x", "y", "z"}))
    assert s.escapes == 0 and s.precision == 0.25 and s.recall == 1.0


def test_abstention_is_correct_only_when_nothing_should_be_held() -> None:
    right = score(case(expected="NONE", decided="NONE", affected=set(), held=set(), abstained=True))
    wrong = score(
        case(expected="WINDOW", decided="ESCALATE", affected={"a"}, held=set(), abstained=True)
    )
    assert right.abstention_correct is True and right.precision == 1.0 and right.recall == 1.0
    assert wrong.abstention_correct is False and wrong.escapes == 1


def test_summary_aggregates_across_cases() -> None:
    results = [
        case(decided="WINDOW"),
        case(golden_id="y", family="lot", expected="LOT", decided="LOT", approved_unamended=False),
        case(
            golden_id="z",
            family="bench",
            expected="NONE",
            decided="NONE",
            affected=set(),
            held=set(),
            abstained=True,
            latency_total_ms=3000,
        ),
    ]
    m = summarise([score(r) for r in results])
    assert m["cases"] == 3 and m["escapes"] == 0 and m["decision_match"] == 1.0
    assert (
        m["agreement_rate"] == pytest.approx(2 / 3, abs=1e-3)
        and m["abstention_correct_rate"] == 1.0
    )
    assert m["latency_p95_ms"] >= 1000 and m["by_family"]["bench"]["cases"] == 1
