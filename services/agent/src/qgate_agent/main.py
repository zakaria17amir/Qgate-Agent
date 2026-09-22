"""The agent process: graph + HTTP + the EOL-failure consumer, wired from the environment.

Two database connections by design (ADR-003): ``agent_ro`` for the tools, ``checkpoint_rw``
for graph state. The tools' code path cannot reach a writable connection.
"""

import logging
import threading
from pathlib import Path

import httpx
import yaml
from psycopg_pool import ConnectionPool

from qgate_agent import consumer
from qgate_agent.checkpoint import saver
from qgate_agent.graph import build_graph
from qgate_agent.http import build_http
from qgate_agent.llm import Ask, LangChainModel, Mode
from qgate_agent.nodes import Deps
from qgate_core.auth import Role, mint
from qgate_core.health import ok, serve
from qgate_core.settings import Settings

log = logging.getLogger("agent")


class AgentSettings(Settings):
    database_url_agent_ro: str = ""
    database_url_checkpoint_rw: str = ""
    detect_base_url: str = "http://detect:8002"
    api_base_url: str = "http://api:8000"
    mes_base_url: str = "http://mock-mes:8003"
    mes_api_key: str = "dev-mes-key"
    jwt_secret: str = "dev-only-change-me"  # noqa: S105 — overridden by JWT_SECRET
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5"
    llm_api_key: str | None = None
    llm_mode: Mode = "replay"
    cassette_dir: Path = Path("/workspace/eval/cassettes")
    fault_map_path: Path = Path("/knowledge/fault_map.yaml")


def main() -> None:
    logging.basicConfig(level="INFO")
    s = AgentSettings()
    service_token = mint("agent", Role.SERVICE, s.jwt_secret)
    deps_kwargs = dict(
        ro=ConnectionPool(s.database_url_agent_ro, min_size=1, max_size=4, open=True),
        detect=httpx.Client(base_url=s.detect_base_url, timeout=30),
        api=httpx.Client(
            base_url=s.api_base_url,
            timeout=10,
            headers={"Authorization": f"Bearer {service_token}"},
        ),
        mes=httpx.Client(base_url=s.mes_base_url, timeout=10, headers={"X-API-Key": s.mes_api_key}),
        ask=Ask(
            s.llm_mode, s.cassette_dir, LangChainModel(s.llm_model, s.llm_provider, s.llm_api_key)
        ),
        fault_map=yaml.safe_load(s.fault_map_path.read_text(encoding="utf8")),
    )
    with saver(s.database_url_checkpoint_rw) as checkpointer:
        deps = Deps(**deps_kwargs)
        graph = build_graph(deps, checkpointer)

        def db_ro() -> None:
            with deps.ro.connection() as conn:
                conn.execute("select 1")

        def ready() -> dict[str, bool]:
            return {
                "db_ro": ok(db_ro),
                "db_checkpoint": ok(lambda: checkpointer.get({"configurable": {"thread_id": "-"}})),
                "detect": ok(lambda: deps.detect.get("/health", params={}).raise_for_status()),
                "api": ok(lambda: deps.api.get("/health").raise_for_status()),
            }

        app = build_http(graph, ready=ready)
        threading.Thread(target=consumer.run, args=(s, app), daemon=True).start()
        serve(app)
