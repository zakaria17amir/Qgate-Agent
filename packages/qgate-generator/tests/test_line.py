from pathlib import Path

import pytest

from qgate_generator.line import Line

pytestmark = pytest.mark.unit
LINE_YAML = Path(__file__).parents[3] / "scenarios" / "line.yaml"


@pytest.fixture(scope="module")
def line() -> Line:
    return Line.load(LINE_YAML)


def test_thirty_stations_in_unique_sequence(line: Line) -> None:
    assert len(line.stations) == 30
    assert sorted(s.sequence_pos for s in line.stations) == list(range(1, 31))


def test_every_characteristic_has_ordered_limits(line: Line) -> None:
    chars = [c for s in line.stations for c in s.characteristics]
    assert chars
    assert all(c.lower_limit < c.nominal < c.upper_limit for c in chars)
    assert all(c.station_id for c in chars)


def test_last_station_is_eol_with_benches(line: Line) -> None:
    assert line.eol_station.sequence_pos == 30
    assert line.eol_benches
    assert all(b.station_id == line.eol_station.id for b in line.eol_benches)


def test_lookup_unknown_characteristic_raises(line: Line) -> None:
    with pytest.raises(KeyError):
        line.characteristic("CH-99-NOPE")


def test_three_shifts_cover_the_day(line: Line) -> None:
    assert len(line.shifts) == 3
    assert line.shift_at_hour(7).id != line.shift_at_hour(15).id != line.shift_at_hour(23).id
