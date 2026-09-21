"""The fifty goldens must be internally consistent with the generator's ground truth."""

from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from qgate_core.models import EolResult, Result
from qgate_eval.golden import Decision, Family, Golden, load_all
from qgate_generator.line import Line
from qgate_generator.scenario import Scenario
from qgate_generator.stream import Run, generate

ROOT = Path(__file__).parents[3]
LINE = Line.load(ROOT / "scenarios" / "line.yaml")
GOLDENS = load_all(ROOT / "eval" / "goldens")
EXPECTED_COUNTS = {
    Family.ISOLATED: 12,
    Family.DRIFT: 12,
    Family.LOT: 8,
    Family.BENCH: 8,
    Family.CONTRADICTORY: 6,
    Family.OVERLAP: 4,
}


@cache
def run_for(scenario: str, seed: int) -> Run:
    s = Scenario.load(ROOT / "scenarios" / f"{scenario}.yaml", LINE)
    return generate(LINE, s.model_copy(update={"seed": seed}))


@pytest.mark.unit
def test_fifty_cases_in_the_designed_families() -> None:
    assert len(GOLDENS) == 50
    assert Counter(g.family for g in GOLDENS) == EXPECTED_COUNTS
    assert len({g.id for g in GOLDENS}) == 50


@pytest.mark.slow
@pytest.mark.parametrize("golden", GOLDENS, ids=lambda g: g.id)
def test_trigger_is_a_real_failure_with_matching_codes(golden: Golden) -> None:
    run = run_for(golden.scenario, golden.seed)
    eol = next(e for e in run.events if isinstance(e, EolResult) and e.vin == golden.trigger.vin)
    assert eol.result is Result.FAIL
    assert eol.fault_codes == golden.trigger.fault_codes


@pytest.mark.slow
@pytest.mark.parametrize(
    "golden", [g for g in GOLDENS if g.expected.decision is Decision.NONE], ids=lambda g: g.id
)
def test_bench_cases_trigger_on_a_genuinely_good_car(golden: Golden) -> None:
    assert golden.trigger.vin not in run_for(golden.scenario, golden.seed).truth.defective_vins


@pytest.mark.unit
@pytest.mark.parametrize(
    "golden", [g for g in GOLDENS if g.expected.station_id], ids=lambda g: g.id
)
def test_expected_station_exists(golden: Golden) -> None:
    LINE.station(golden.expected.station_id or "")


@pytest.mark.unit
def test_some_humans_amend_or_reject_so_the_audit_diff_path_is_exercised() -> None:
    actions = Counter(g.human.action for g in GOLDENS)
    assert actions["AMEND"] >= 2 and actions["REJECT"] >= 1
