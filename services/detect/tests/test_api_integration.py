"""detect's HTTP surface over a real, COPY-loaded Postgres."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from qgate_core.settings import Settings
from qgate_detect.api import build_api
from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import EPOCH, generate

pytestmark = pytest.mark.integration
SCENARIOS = Path(__file__).parents[3] / "scenarios"
LINE = Line.load(SCENARIOS / "line.yaml")
START, END = EPOCH.isoformat(), (EPOCH + timedelta(days=2)).isoformat()


def load(pg_url: str, scenario: str) -> None:
    run = generate(LINE, Scenario.load(SCENARIOS / f"{scenario}.yaml", LINE))
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, LINE)
        truncate_facts(conn)
        copy_run(conn, run)


@pytest.fixture(scope="module")
def client(pg_url: str) -> Iterator[TestClient]:
    with TestClient(build_api(Settings(database_url=pg_url))) as c:
        yield c


def test_drift_endpoint_finds_the_tool_wear(pg_url: str, client: TestClient) -> None:
    load(pg_url, "tool_wear")
    r = client.get(
        "/drift",
        params={
            "station_id": "ST-19",
            "characteristic_id": "CH-19-TORQUE",
            "from": START,
            "to": END,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "DRIFT" and body["severity"] == "HIGH"
    assert body["onset"] is not None and body["evidence"]["n"] == 2000
    quiet = client.get(
        "/drift",
        params={"station_id": "ST-05", "characteristic_id": "CH-05-GAP", "from": START, "to": END},
    ).json()
    assert quiet["verdict"] == "NONE"


def test_bench_endpoint_blames_the_drifting_bench_only(pg_url: str, client: TestClient) -> None:
    load(pg_url, "bench_drift")
    params = {"characteristic_id": "CH-30-HEADLAMP", "from": START, "to": END}
    bad = client.get("/bench/EOL-B2/capability", params=params).json()
    good = client.get("/bench/EOL-B1/capability", params=params).json()
    assert bad["capable"] is False and abs(bad["bias_vs_peers"]) > 0.5
    assert good["capable"] is True and bad["grr_pct"] is not None


def test_unknown_characteristic_is_a_404(client: TestClient) -> None:
    r = client.get(
        "/drift",
        params={"station_id": "ST-19", "characteristic_id": "CH-99-X", "from": START, "to": END},
    )
    assert r.status_code == 404
