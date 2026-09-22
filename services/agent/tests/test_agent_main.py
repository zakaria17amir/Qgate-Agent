from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from qgate_agent.http import build_http

pytestmark = pytest.mark.unit


def test_health_names_this_service() -> None:
    assert TestClient(build_http(MagicMock())).get("/health").json()["service"] == "agent"
