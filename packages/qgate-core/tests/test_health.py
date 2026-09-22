import pytest
from fastapi.testclient import TestClient

from qgate_core.health import health_app

pytestmark = pytest.mark.unit


def test_health_reports_service_name() -> None:
    client = TestClient(health_app("ingest"))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "ingest"}


def test_metrics_is_prometheus_text() -> None:
    client = TestClient(health_app("ingest"))
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "python_info" in r.text


def test_ready_is_200_when_every_check_passes() -> None:
    client = TestClient(health_app("api", ready=lambda: {"db": True, "agent": True}))
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"db": True, "agent": True}


def test_ready_is_503_naming_the_failed_check() -> None:
    client = TestClient(health_app("api", ready=lambda: {"db": True, "agent": False}))
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"db": True, "agent": False}


def test_ready_without_checks_is_liveness() -> None:
    assert TestClient(health_app("mock")).get("/ready").status_code == 200
