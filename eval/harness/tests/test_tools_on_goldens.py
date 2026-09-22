"""Gate 2: with no model anywhere, do the deterministic tools give the right answer on every golden?

Per golden: regenerate its run, COPY it into Postgres, then ask the same questions the agent's
deterministic nodes will ask. Expectations come from the frozen goldens (tag goldens-v1).
"""

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from qgate_agent.tools import (
    check_bench,
    check_station_drift,
    find_correlated_failures,
    get_vehicle_genealogy,
    vins_by_lot,
)
from qgate_core.settings import Settings
from qgate_detect.api import build_api
from qgate_eval.golden import Decision, Golden, load_all
from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import EPOCH, generate

pytestmark = [pytest.mark.integration, pytest.mark.slow]
ROOT = Path(__file__).parents[3]
LINE = Line.load(ROOT / "scenarios" / "line.yaml")
GOLDENS = load_all(ROOT / "eval" / "goldens")
WINDOW_END = EPOCH + timedelta(days=3)
NO_PATTERN = 1  # one earlier base-rate defect with the same code is noise, not a run of siblings


@pytest.fixture(scope="module")
def detect(pg_url: str) -> Iterator[TestClient]:
    with TestClient(build_api(Settings(database_url=pg_url))) as c:
        yield c


@pytest.fixture(scope="module")
def conn(pg_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_url) as c:
        seed_dims(c, LINE)
        yield c


def load(conn: psycopg.Connection, golden: Golden) -> None:
    scenario = Scenario.load(ROOT / "scenarios" / f"{golden.scenario}.yaml", LINE)
    truncate_facts(conn)
    copy_run(conn, generate(LINE, scenario.model_copy(update={"seed": golden.seed})))


def seq_of(ts: datetime, station_id: str) -> int:
    """Timestamp at a station -> build sequence number (the takt makes them interchangeable)."""
    pos = LINE.station(station_id).sequence_pos - 1
    return round((ts - EPOCH).total_seconds() / LINE.takt_s) - pos


def within(actual: int, expected: int | None, tolerance: int) -> bool:
    return expected is not None and abs(actual - expected) <= tolerance


@pytest.mark.parametrize("golden", GOLDENS, ids=lambda g: g.id)
def test_tools_alone_reach_the_expected_evidence(
    golden: Golden, conn: psycopg.Connection, detect: TestClient
) -> None:
    load(conn, golden)
    g = get_vehicle_genealogy(conn, golden.trigger.vin)
    assert g.eol is not None and g.eol.fault_codes == golden.trigger.fault_codes
    station = golden.expected.station_id or ""
    code = f"F-{station[-2:]}"
    # the triage runs when the EOL fail arrives: siblings are failures already known by then
    siblings = find_correlated_failures(
        conn, code, station, EPOCH, g.eol.tested_at, exclude_vin=golden.trigger.vin
    )
    char = LINE.station(station).characteristics[0].id
    drift = check_station_drift(detect, station, char, EPOCH, WINDOW_END)

    match golden.expected.decision:
        case Decision.SINGLE:
            assert siblings.n <= NO_PATTERN, siblings.vins
            assert drift.verdict == "NONE", drift
        case Decision.WINDOW:
            assert drift.verdict == "DRIFT" and drift.onset is not None, drift
            onset = seq_of(drift.onset, station)
            assert within(
                onset, golden.expected.window_start_sequence, golden.expected.tolerance_takts
            ), (onset, golden.expected.window_start_sequence)
        case Decision.LOT:
            assert (
                siblings.top_lot == golden.expected.lot_ids[0] and siblings.top_lot_share >= 0.8
            ), siblings
            assert golden.trigger.vin in vins_by_lot(conn, station, golden.expected.lot_ids[0])
        case Decision.NONE:
            bench = check_bench(detect, g.eol.bench_id, char, EPOCH, WINDOW_END)
            assert bench.capable is False and bench.method != "insufficient-data", bench
            assert not g.out_of_tolerance_stations()[:-1], (
                g.out_of_tolerance_stations()
            )  # nothing upstream
        case Decision.ESCALATE:
            assert drift.verdict == "STEP", drift
            assert siblings.n <= NO_PATTERN, siblings.vins  # first failure of the step: no run yet
        case Decision.MULTI:
            assert (
                siblings.top_lot == golden.expected.lot_ids[0] and siblings.top_lot_share >= 0.6
            ), siblings
            drift_station = "ST-19"
            d2 = check_station_drift(detect, drift_station, "CH-19-TORQUE", EPOCH, WINDOW_END)
            assert d2.verdict == "DRIFT" and d2.onset is not None
            assert within(
                seq_of(d2.onset, drift_station),
                golden.expected.window_start_sequence,
                golden.expected.tolerance_takts,
            )
