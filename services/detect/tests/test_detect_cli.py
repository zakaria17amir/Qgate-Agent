import pytest
from fastapi.testclient import TestClient

from qgate_detect.cli import build_app

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("role", ["api", "worker"])
def test_health_names_role(role: str) -> None:
    assert TestClient(build_app(role)).get("/health").json()["service"] == f"detect-{role}"
