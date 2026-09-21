import pytest
from fastapi.testclient import TestClient

from qgate_ingest.main import app

pytestmark = pytest.mark.unit


def test_health_names_this_service() -> None:
    assert TestClient(app).get("/health").json()["service"] == "ingest"
