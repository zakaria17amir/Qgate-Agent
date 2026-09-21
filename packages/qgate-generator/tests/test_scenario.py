from pathlib import Path

import pytest
import yaml

from qgate_generator.line import Line
from qgate_generator.scenario import Scenario

pytestmark = pytest.mark.unit
SCENARIOS = Path(__file__).parents[3] / "scenarios"
NAMES = [
    "clean_baseline",
    "tool_wear",
    "shift_step",
    "bad_lot",
    "correlated_noise",
    "bench_drift",
    "overlap",
]


@pytest.fixture(scope="module")
def line() -> Line:
    return Line.load(SCENARIOS / "line.yaml")


@pytest.mark.parametrize("name", NAMES)
def test_every_scenario_loads_against_the_line(line: Line, name: str) -> None:
    s = Scenario.load(SCENARIOS / f"{name}.yaml", line)
    assert s.id == name
    assert s.vehicles >= 100


def test_unknown_station_id_is_rejected_by_name(line: Line, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "id": "bad",
                "seed": 1,
                "vehicles": 100,
                "injects": [
                    {
                        "kind": "drift",
                        "station_id": "ST-99",
                        "characteristic_id": "CH-99-X",
                        "start_sequence": 10,
                        "magnitude": 0.1,
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="ST-99"):
        Scenario.load(bad, line)


def test_overlap_composes_lot_and_drift(line: Line) -> None:
    kinds = {i.kind for i in Scenario.load(SCENARIOS / "overlap.yaml", line).injects}
    assert kinds == {"lot", "drift"}
