"""The foreign plant system's contract, exercised the way the agent's commit node will use it."""

import uuid

import pytest
from fastapi.testclient import TestClient

from qgate_mock_mes.main import build_app

pytestmark = pytest.mark.unit
KEY = {"X-API-Key": "dev-mes-key"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_app(api_key="dev-mes-key", chaos_enabled=False))


def hold(ref: str = "c-1") -> dict[str, object]:
    return {
        "external_ref": ref,
        "station_id": "ST-19",
        "lot_ids": [],
        "vins": ["SYN1", "SYN2"],
        "reason": "torque drift at ST-19",
    }


def test_missing_api_key_is_401(client: TestClient) -> None:
    r = client.post("/v1/holds", json=hold(), headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 401


def test_create_then_identical_replay_is_200_not_a_second_hold(client: TestClient) -> None:
    """Review Focus 5: at-least-once retries must not create a second hold."""
    key = str(uuid.uuid4())
    first = client.post("/v1/holds", json=hold(), headers={**KEY, "Idempotency-Key": key})
    again = client.post("/v1/holds", json=hold(), headers={**KEY, "Idempotency-Key": key})
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["hold_ref"] == again.json()["hold_ref"]
    stats = client.get("/_stats", headers=KEY).json()
    assert stats == {"holds": 1, "duplicate_replays": 1, "duplicate_conflicts": 0}


def test_same_key_different_body_is_409(client: TestClient) -> None:
    key = str(uuid.uuid4())
    client.post("/v1/holds", json=hold(), headers={**KEY, "Idempotency-Key": key})
    r = client.post("/v1/holds", json=hold("c-other"), headers={**KEY, "Idempotency-Key": key})
    assert r.status_code == 409
    assert client.get("/_stats", headers=KEY).json()["duplicate_conflicts"] == 1


def test_get_hold_round_trips_and_unknown_is_404(client: TestClient) -> None:
    created = client.post(
        "/v1/holds", json=hold(), headers={**KEY, "Idempotency-Key": str(uuid.uuid4())}
    )
    ref = created.json()["hold_ref"]
    assert client.get(f"/v1/holds/{ref}", headers=KEY).json()["vins"] == ["SYN1", "SYN2"]
    assert client.get("/v1/holds/nope", headers=KEY).status_code == 404


def test_chaos_is_forbidden_unless_enabled(client: TestClient) -> None:
    assert (
        client.post("/_chaos", json={"mode": "error", "seconds": 5}, headers=KEY).status_code == 403
    )


def test_chaos_error_mode_returns_the_injected_status() -> None:
    c = TestClient(build_app(api_key="k", chaos_enabled=True))
    assert (
        c.post(
            "/_chaos",
            json={"mode": "error", "seconds": 60, "status": 503},
            headers={"X-API-Key": "k"},
        ).status_code
        == 204
    )
    r = c.post(
        "/v1/holds", json=hold(), headers={"X-API-Key": "k", "Idempotency-Key": str(uuid.uuid4())}
    )
    assert r.status_code == 503
