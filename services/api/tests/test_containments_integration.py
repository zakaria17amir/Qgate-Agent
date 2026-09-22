"""api owns containment state: propose, read, report outcome, expire."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from qgate_api.main import ApiSettings, build_app
from qgate_api.store import sweep_expired
from qgate_core.auth import Role, mint
from qgate_generator.line import Line
from qgate_generator.seed import seed_dims

pytestmark = pytest.mark.integration
SECRET = "test-secret"


@pytest.fixture(scope="module")
def api(pg_url: str) -> Iterator[TestClient]:
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, Line.load(Path(__file__).parents[3] / "scenarios" / "line.yaml"))
    settings = ApiSettings(database_url=pg_url, jwt_secret=SECRET, approval_timeout_s=60)
    with TestClient(build_app(settings, agent=None, producer=None)) as c:
        yield c


def auth(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint('t', role, SECRET)}"}


def proposal(vin: str = "SYN1") -> dict[str, object]:
    return {
        "thread_id": str(uuid.uuid4()),
        "kind": "WINDOW",
        "station_id": "ST-19",
        "window_start": "2026-01-05T20:00:00Z",
        "window_end": "2026-01-05T21:00:00Z",
        "lot_ids": [],
        "vins": [vin, "SYN2"],
        "confidence": 0.8,
        "reason": "torque drift",
        "draft_order": "Hold 2 vehicles built at ST-19 20:00-21:00.",
    }


def test_propose_then_read_and_list(api: TestClient) -> None:
    created = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE))
    assert created.status_code == 201, created.text
    cid = created.json()["containment_id"]
    detail = api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()
    assert (
        detail["state"] == "PROPOSED"
        and detail["vin_count"] == 2
        and detail["vins"] == ["SYN1", "SYN2"]
    )
    assert detail["expires_at"] is not None
    listed = api.get(
        "/containments", params={"state": "PROPOSED"}, headers=auth(Role.VIEWER)
    ).json()
    assert cid in {c["containment_id"] for c in listed}


def test_internal_endpoints_need_the_service_role(api: TestClient) -> None:
    assert (
        api.post("/internal/containments", json=proposal(), headers=auth(Role.APPROVER)).status_code
        == 403
    )
    assert api.get("/containments", headers={}).status_code == 401


def test_outcome_patch_records_audit_metrics(api: TestClient) -> None:
    cid = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    r = api.patch(
        f"/internal/containments/{cid}",
        headers=auth(Role.SERVICE),
        json={
            "state": "ESCALATED",
            "reason": "contradictory evidence",
            "latency_total_ms": 1200,
            "latency_llm_ms": 800,
            "latency_non_llm_ms": 400,
            "prompt_tokens": 900,
            "completion_tokens": 120,
            "cost_usd": 0.0012,
        },
    )
    assert r.status_code == 200, r.text
    audit = api.get("/audit", headers=auth(Role.VIEWER)).json()
    row = next(a for a in audit if a["containment_id"] == cid)
    assert row["latency_llm_ms"] == 800 and float(row["cost_usd"]) == 0.0012
    assert api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()["state"] == "ESCALATED"


def test_sweep_expires_stale_proposals_only(api: TestClient, pg_url: str) -> None:
    cid = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    with psycopg.connect(pg_url) as conn:
        assert sweep_expired(conn, now=datetime.now(UTC)) == []  # 60 s timeout has not passed
        expired = sweep_expired(conn, now=datetime.now(UTC) + timedelta(hours=1))
    assert uuid.UUID(cid) in expired
    assert api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()["state"] == "EXPIRED"
