"""The whole system in one process: api + agent + detect + mock-mes as ASGI apps over Postgres.

Used by the eval harness and the agent's end-to-end tests. Compose runs the same code as
separate containers; this wiring exists so `replay` needs neither compose nor Kafka.
"""

from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from qgate_agent.checkpoint import saver
from qgate_agent.graph import build_graph
from qgate_agent.http import build_http
from qgate_agent.llm import Ask, Mode, StructuredModel
from qgate_agent.nodes import Deps
from qgate_api.main import ApiSettings
from qgate_api.main import build_app as build_api
from qgate_core.auth import Role, mint
from qgate_core.settings import Settings
from qgate_detect.api import build_api as build_detect
from qgate_mock_mes.main import build_app as build_mes

ROOT = Path(__file__).parents[3]
SECRET = "in-process-secret-long-enough-for-hs256-0123456789"  # noqa: S105 — never leaves this process


class _LazyAgent:
    """api -> agent client resolved at call time, so the agent can be replaced (restart tests)."""

    def __init__(self, stack: "Stack") -> None:
        self.stack = stack

    def post(self, url: str, *, json: Any = None) -> Any:
        assert self.stack.agent is not None
        return self.stack.agent.post(url, json=json)


class Stack:
    def __init__(self, pg_url: str, model: StructuredModel, mode: Mode, cassette_dir: Path) -> None:
        self.pg_url, self.model, self.mode, self.cassette_dir = pg_url, model, mode, cassette_dir
        settings = Settings(database_url=pg_url)
        self.mes = TestClient(
            build_mes(api_key="k", chaos_enabled=True), headers={"X-API-Key": "k"}
        )
        self.detect = TestClient(build_detect(settings))
        api_settings = ApiSettings(database_url=pg_url, jwt_secret=SECRET, approval_timeout_s=600)
        self.agent: TestClient | None = None
        self.api = TestClient(build_api(api_settings, agent=_LazyAgent(self), producer=None))
        self._saver_cm = saver(pg_url)
        self.saver = self._saver_cm.__enter__()
        self.ro = ConnectionPool(pg_url, min_size=1, max_size=4, open=True)
        self.fault_map = yaml.safe_load(
            (ROOT / "knowledge" / "fault_map.yaml").read_text(encoding="utf8")
        )
        self.start_agent()

    def start_agent(self) -> None:
        """A fresh graph + HTTP app on the same checkpointer — what a process restart looks like."""
        deps = Deps(
            ro=self.ro,
            detect=self.detect,
            api=TestClient(
                self.api.app,
                headers={"Authorization": f"Bearer {mint('agent', Role.SERVICE, SECRET)}"},
            ),
            mes=self.mes,
            ask=Ask(self.mode, self.cassette_dir, self.model),
            fault_map=self.fault_map,
        )
        self.agent = TestClient(build_http(build_graph(deps, self.saver), run_in_thread=False))

    def human(self, role: Role = Role.APPROVER, sub: str = "harness") -> dict[str, str]:
        return {"Authorization": f"Bearer {mint(sub, role, SECRET)}"}

    def close(self) -> None:
        self._saver_cm.__exit__(None, None, None)
        self.ro.close()
