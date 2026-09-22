import pytest
from fastapi.testclient import TestClient

from qgate_api.main import ApiSettings, build_app

pytestmark = pytest.mark.unit


def test_health_names_this_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qgate_api.main.ConnectionPool", lambda *a, **k: object())
    app = build_app(ApiSettings(database_url="postgresql://x"), agent=None, producer=None)
    assert TestClient(app).get("/health").json()["service"] == "api"
