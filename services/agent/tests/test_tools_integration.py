"""The agent's read-only tools against a COPY-loaded bad_lot run."""

from collections.abc import Iterator
from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import psycopg
import pytest

from qgate_agent.tools import (
    find_correlated_failures,
    get_station_spec,
    get_vehicle_genealogy,
    vins_by_lot,
    vins_in_window,
)
from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import EPOCH, Run, generate

pytestmark = pytest.mark.integration
SCENARIOS = Path(__file__).parents[3] / "scenarios"
LINE = Line.load(SCENARIOS / "line.yaml")
LOT = "L-24-0004"


@pytest.fixture(scope="module")
def loaded(pg_url: str) -> Iterator[tuple[psycopg.Connection, Run]]:
    run = generate(LINE, Scenario.load(SCENARIOS / "bad_lot.yaml", LINE))
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, LINE)
        truncate_facts(conn)
        copy_run(conn, run)
        yield conn, run


def test_genealogy_is_the_full_ordered_path(loaded: tuple[psycopg.Connection, Run]) -> None:
    conn, run = loaded
    vin = sorted(run.truth.by_inject[0])[3]
    g = get_vehicle_genealogy(conn, vin)
    assert [v.station_id for v in g.visits] == [f"ST-{i:02d}" for i in range(1, 31)]
    assert g.lots_at("ST-24") == [LOT]
    assert g.eol is not None and "F-24" in g.eol.fault_codes
    assert any(m.out_of_tolerance for m in g.visit("ST-24").measurements)


def test_station_spec_carries_tolerances(loaded: tuple[psycopg.Connection, Run]) -> None:
    spec = get_station_spec(loaded[0], "ST-24")
    torque = next(c for c in spec.characteristics if c.characteristic_id == "CH-24-TORQUE")
    assert spec.fits_lot and spec.takt_s == 60
    assert torque.lower_limit < torque.nominal < torque.upper_limit


def test_correlation_is_scoped_to_the_station_and_breaks_down_by_lot(
    loaded: tuple[psycopg.Connection, Run],
) -> None:
    """Review Focus 3: only vehicles that passed ST-24 count; siblings concentrate in the lot."""
    conn, run = loaded
    trigger = sorted(run.truth.by_inject[0])[10]
    start, end = EPOCH, EPOCH + timedelta(days=2)
    r = find_correlated_failures(conn, "F-24", "ST-24", start, end, exclude_vin=trigger)
    assert r.n > 20 and trigger not in r.vins
    assert sum(r.by_shift.values()) == r.n and sum(r.by_lot.values()) >= r.n
    assert r.top_lot == LOT and r.top_lot_share > 0.8
    assert len(r.entered_at) == r.n and r.spread_takts() > 60  # carriers span many lot blocks
    nothing = find_correlated_failures(conn, "F-24", "ST-05", start, end)
    assert (
        nothing.n == r.n + 1
    )  # every vehicle passed ST-05 too: the code, not the station, filters
    absent = find_correlated_failures(conn, "F-99", "ST-24", start, end)
    assert absent.n == 0 and absent.top_lot is None


def test_lot_window_returns_carriers_only(loaded: tuple[psycopg.Connection, Run]) -> None:
    """Review Focus 4: by lot means carriers of that lot at that station, not a time span."""
    conn, _ = loaded
    carriers = vins_by_lot(conn, "ST-24", LOT)
    assert 200 <= len(carriers) <= 300  # 8 rotating lots over 2000 vehicles
    seqs = sorted(int(v[3:]) for v in carriers)
    assert max(b - a for a, b in pairwise(seqs)) > 1  # interleaved


def test_time_window_is_inclusive_of_start_exclusive_of_end(
    loaded: tuple[psycopg.Connection, Run],
) -> None:
    conn, _ = loaded
    pos = LINE.station("ST-19").sequence_pos - 1
    start = EPOCH + timedelta(seconds=(1000 + pos) * 60)
    vins = vins_in_window(conn, "ST-19", start, start + timedelta(seconds=10 * 60))
    assert vins == [f"SYN{n:014d}" for n in range(1000, 1010)]
