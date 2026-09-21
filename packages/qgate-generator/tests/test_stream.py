from itertools import pairwise
from pathlib import Path

import pytest

from qgate_core.models import BuildEvent, EolResult, Measurement, Result
from qgate_generator.line import Line
from qgate_generator.scenario import Scenario
from qgate_generator.stream import Run, generate

pytestmark = pytest.mark.unit
SCENARIOS = Path(__file__).parents[3] / "scenarios"
LINE = Line.load(SCENARIOS / "line.yaml")


def run(name: str, vehicles: int = 2000) -> Run:
    scenario = Scenario.load(SCENARIOS / f"{name}.yaml", LINE)
    return generate(LINE, scenario.model_copy(update={"vehicles": vehicles}))


def test_same_seed_gives_identical_stream() -> None:
    a, b = run("tool_wear", 300), run("tool_wear", 300)
    assert a.events == b.events
    assert a.truth == b.truth


def test_stream_is_time_ordered_and_complete() -> None:
    r = run("clean_baseline", 200)
    stamps = [
        e.entered_at
        if isinstance(e, BuildEvent)
        else e.measured_at
        if isinstance(e, Measurement)
        else e.tested_at
        for e in r.events
    ]
    assert stamps == sorted(stamps)
    builds = [e for e in r.events if isinstance(e, BuildEvent)]
    eols = [e for e in r.events if isinstance(e, EolResult)]
    assert len(builds) == 200 * len(LINE.stations)
    assert len(eols) == 200
    assert all(e.result in {Result.PASS, Result.FAIL} for e in eols)


def test_bench_drift_fails_good_cars() -> None:
    """Review Focus 4: the bench lies, the cars are fine — the abstention family depends on it."""
    r = run("bench_drift")
    fails_late = [
        e
        for e in r.events
        if isinstance(e, EolResult) and e.result is Result.FAIL and int(e.vin[-6:]) >= 1000
    ]
    assert r.truth.bench_fault is True
    assert len(r.truth.defective_vins) <= 0.015 * 2000
    assert len(fails_late) > 0.05 * 1000
    assert {e.bench_id for e in fails_late if e.vin not in r.truth.defective_vins} == {"EOL-B2"}


def test_bad_lot_carriers_are_not_contiguous() -> None:
    """Review Focus 5: a time-window containment must not accidentally be correct here."""
    r = run("bad_lot")
    seqs = sorted(int(v[-6:]) for v in r.truth.by_inject[0])
    assert len(seqs) > 50
    assert max(b - a for a, b in pairwise(seqs)) > 1


def test_tool_wear_onset_lands_where_designed() -> None:
    """The ramp crosses the limit near seq 1100; process noise makes the first crossing fuzzy."""
    r = run("tool_wear")
    onset = min(int(v[-6:]) for v in r.truth.by_inject[0])
    assert 950 <= onset <= 1250


def test_eol_repeats_are_a_small_sample() -> None:
    r = run("clean_baseline", 500)
    repeats = {m.vin for m in r.events if isinstance(m, Measurement) and m.repeat_no > 1}
    assert 0.02 * 500 <= len(repeats) <= 0.10 * 500
