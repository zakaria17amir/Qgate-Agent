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
