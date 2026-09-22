"""Contract: every response conforms to the *authored* openapi.yaml, which the server publishes."""

from typing import Any

import pytest
import schemathesis
from hypothesis import HealthCheck, settings

from qgate_mock_mes.main import build_app

APP = build_app(api_key="k", chaos_enabled=True)
schema: Any = schemathesis.openapi.from_asgi("/openapi.json", APP)
schema = schema.include(path_regex=r"^/v1/|^/_stats")  # /_chaos has side effects on other calls


@schema.auth()
class ApiKey:
    """Declared auth so schemathesis can also probe missing/invalid keys and expect 401."""

    def get(self, case: Any, context: Any) -> str:
        return "k"

    def set(self, case: Any, data: str, context: Any) -> None:
        case.headers = case.headers or {}
        case.headers["X-API-Key"] = data


@pytest.mark.contract
@schema.parametrize()  # type: ignore[untyped-decorator]
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_responses_match_the_published_schema(case: Any) -> None:
    case.validate_response(case.call())
