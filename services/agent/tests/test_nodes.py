"""Deterministic nodes with fakes: routing and bounding are rules, and the rules are the spec."""

from datetime import UTC, datetime, timedelta

import pytest

from qgate_agent import nodes
from qgate_agent.state import Hypotheses, Hypothesis, TriageState
from qgate_agent.tools.models import BenchResult, CorrelationResult, DriftResult

pytestmark = pytest.mark.unit
T0 = datetime(2026, 1, 5, 6, tzinfo=UTC)


def drift(verdict: str, severity: str = "HIGH", onset: datetime | None = T0) -> DriftResult:
    return DriftResult(
        verdict=verdict,
        onset=onset if verdict != "NONE" else None,
        changed_at=onset,
        severity=severity,
        confidence=0.9,
        evidence={},
    )


def bench(capable: bool, method: str = "grr+bias-vs-peers") -> BenchResult:
    return BenchResult(
        bench_id="EOL-B2",
        capable=capable,
        grr_pct=6.0,
        bias_vs_peers=0.9 if not capable else 0.0,
        n_repeats=10,
        n_values=300,
        method=method,
    )


def siblings(
    vins: list[str], lots: dict[str, int] | None = None, spread_takts: int = 200
) -> CorrelationResult:
    """Siblings ``spread_takts`` apart: contiguous (1) is a run in time, wide looks like a lot."""
    return CorrelationResult(
        fault_code="F-19",
        station_id="ST-19",
        vins=vins,
        entered_at=[T0 + timedelta(seconds=60 * spread_takts * i) for i in range(len(vins))],
        by_shift={"S1": len(vins)},
        by_lot=lots or {},
    )


def state(**kw: object) -> TriageState:
    base: TriageState = {"vin": "SYN1", "fault_codes": ["F-19"], "eol_ts": T0 + timedelta(hours=20)}
    base.update(kw)  # type: ignore[typeddict-item]
    return base


def test_route_bench_incapable_goes_to_bench_alert() -> None:
    s = state(drift=drift("DRIFT"), bench=bench(False), siblings=siblings(["a", "b", "c"]))
    assert nodes.route(s) == "bench_alert"


def test_route_detected_change_without_siblings_escalates_whatever_its_size() -> None:
    s = state(drift=drift("STEP", "MEDIUM"), bench=bench(True), siblings=siblings([]))
    assert nodes.route(s) == "escalate"
    s = state(drift=drift("DRIFT", "HIGH"), bench=bench(True), siblings=siblings(["one"]))
    assert nodes.route(s) == "escalate"  # one earlier defect is noise, not a run


def test_route_unknown_bench_is_not_a_bad_bench() -> None:
    """Too few readings to judge the gauge must not silence the triage."""
    s = state(
        drift=drift("NONE"), bench=bench(False, method="insufficient-data"), siblings=siblings([])
    )
    assert nodes.route(s) == "bound"


def test_route_otherwise_bounds() -> None:
    s = state(drift=drift("DRIFT"), bench=bench(True), siblings=siblings(["a", "b", "c"]))
    assert nodes.route(s) == "bound"
    s = state(drift=drift("NONE"), bench=bench(True), siblings=siblings([]))
    assert nodes.route(s) == "bound"


def test_bound_prefers_lot_when_siblings_concentrate_in_one() -> None:
    s = state(
        drift=drift("NONE"),
        siblings=siblings(["a", "b", "c", "d", "e"], {"L-24-0004": 5}),
        hypotheses=[Hypothesis(station_id="ST-24", characteristic_id="CH-24-TORQUE", reasoning="")],
    )
    b = nodes.decide_bounds(
        s,
        vins_by_lot=lambda st, lot: ["a", "b", "c", "d", "e", "SYN1"],
        vins_in_window=lambda st, a, z: [],
    )
    assert b.kind == "LOT" and b.lot_ids == ["L-24-0004"] and "SYN1" in b.vins


def test_contiguous_siblings_sharing_a_lot_block_are_a_window_not_a_lot() -> None:
    """drift-06: three consecutive failures always share a lot block; that is time, not the lot."""
    onset = T0 + timedelta(hours=10)
    s = state(
        drift=drift("DRIFT", onset=onset),
        siblings=siblings(["a", "b", "c"], {"L-19-0003": 3}, spread_takts=1),
        hypotheses=[Hypothesis(station_id="ST-19", characteristic_id="CH-19-TORQUE", reasoning="")],
    )
    b = nodes.decide_bounds(
        s, vins_by_lot=lambda st, lot: ["x"] * 250, vins_in_window=lambda st, a, z: ["a", "b", "c"]
    )
    assert b.kind == "WINDOW"


def test_bound_uses_drift_onset_for_a_window() -> None:
    onset = T0 + timedelta(hours=10)
    s = state(
        drift=drift("DRIFT", onset=onset),
        siblings=siblings(["a", "b", "c"]),
        hypotheses=[Hypothesis(station_id="ST-19", characteristic_id="CH-19-TORQUE", reasoning="")],
    )
    seen: list[tuple[str, datetime, datetime]] = []

    def window(st: str, a: datetime, z: datetime) -> list[str]:
        seen.append((st, a, z))
        return ["a", "b", "c", "SYN1"]

    b = nodes.decide_bounds(s, vins_by_lot=lambda st, lot: [], vins_in_window=window)
    assert b.kind == "WINDOW" and b.window_start == onset and seen[0][0] == "ST-19"
    assert seen[0][2] > s["eol_ts"] - timedelta(hours=1)  # window runs up to the trigger's time


def test_bound_falls_back_to_the_single_vehicle() -> None:
    s = state(
        drift=drift("NONE"),
        siblings=siblings([]),
        hypotheses=[Hypothesis(station_id="ST-05", characteristic_id="CH-05-GAP", reasoning="")],
    )
    b = nodes.decide_bounds(s, vins_by_lot=lambda st, lot: [], vins_in_window=lambda st, a, z: [])
    assert b.kind == "SINGLE" and b.vins == ["SYN1"]


def test_hypotheses_outside_the_fault_map_are_rejected() -> None:
    """Review Focus 4: the model ranks candidates; it may not invent a station."""
    allowed = {"ST-19": ["CH-19-TORQUE"], "ST-17": ["CH-17-TORQUE", "CH-17-GAP"]}
    good = Hypotheses(
        ranked=[Hypothesis(station_id="ST-19", characteristic_id="CH-19-TORQUE", reasoning="x")]
    )
    assert nodes.validate_hypotheses(good, allowed) == good.ranked
    bad = Hypotheses(
        ranked=[Hypothesis(station_id="ST-42", characteristic_id="CH-42-X", reasoning="x")]
    )
    with pytest.raises(ValueError, match="ST-42"):
        nodes.validate_hypotheses(bad, allowed)


def test_genealogy_waits_for_ingest_to_land_the_eol_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """The consumer sees the EOL event before ingest has written it (found by the fresh clone)."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    answers = [SimpleNamespace(eol=None), SimpleNamespace(eol=SimpleNamespace(tested_at=T0))]
    monkeypatch.setattr(nodes, "get_vehicle_genealogy", lambda conn, vin: answers.pop(0))
    deps = SimpleNamespace(ro=SimpleNamespace(connection=nullcontext), fault_map={"faults": {}})
    genealogy = nodes.make_nodes(deps, eol_wait_s=1.0)["genealogy"]  # type: ignore[arg-type]
    assert genealogy({"vin": "SYN1", "fault_codes": ["F-19"]})["eol_ts"] == T0

    answers[:] = [SimpleNamespace(eol=None)] * 100
    with pytest.raises(ValueError, match="no end-of-line result"):
        nodes.make_nodes(deps, eol_wait_s=0.0)["genealogy"]({"vin": "SYN1", "fault_codes": []})  # type: ignore[arg-type]
