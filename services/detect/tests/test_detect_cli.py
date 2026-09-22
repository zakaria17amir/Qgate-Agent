import pytest
from fastapi.testclient import TestClient

from qgate_detect import worker
from qgate_detect.api import build_api

pytestmark = pytest.mark.unit


def test_api_health_names_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qgate_detect.api.ConnectionPool", lambda *a, **k: object())
    from qgate_core.settings import Settings

    assert TestClient(build_api(Settings())).get("/health").json()["service"] == "detect-api"


def test_worker_health_names_the_service() -> None:
    assert TestClient(worker.app).get("/health").json()["service"] == "detect-worker"
