"""The whole triage in one process: api + agent + detect + mock-mes over Postgres, fake model.

This is the Gate 3 spine: a failure produces a proposal; a human approves, amends or rejects
through the api; the amendment is recorded with its diff; and a thread waiting at the gate
survives the agent process being thrown away (Review Focus 5).
"""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from qgate_agent.graph import build_graph
from qgate_agent.http import build_http
from qgate_agent.llm import Ask
from qgate_agent.nodes import Deps
from qgate_agent.state import Explanation, Hypotheses, Hypothesis, Order
from qgate_api.main import ApiSettings
from qgate_api.main import build_app as build_api_app
from qgate_core.auth import Role, mint
from qgate_core.pricing import Usage
from qgate_core.settings import Settings
from qgate_detect.api import build_api as build_detect
from qgate_eval.golden import Golden
from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import generate
from qgate_mock_mes.main import build_app as build_mes

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
LINE = Line.load(ROOT / "scenarios" / "line.yaml")
SECRET = "e2e-secret"


class FakeModel:
    """Answers every prompt plausibly without a provider; the graph's rules do the real work."""

    name = "fake"

    def invoke(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        if schema is Hypotheses:
            station = prompt.split("- ")[1].split(" ")[0]  # first candidate in the rendered map
            char = prompt.split("['")[1].split("'")[0]
            out: BaseModel = Hypotheses(
                ranked=[
                    Hypothesis(
                        station_id=station, characteristic_id=char, reasoning="first candidate"
                    )
                ]
            )
        elif schema is Order:
            out = Order(
                text="Hold the listed vehicles at the named station; check the torque tool first."
            )
        else:
            out = Explanation(
                text="The gauge reports a change but no other vehicle failed; a person must check."
            )
        return out, Usage(prompt_tokens=100, completion_tokens=30)


class Stack:
    def __init__(self, pg_url: str) -> None:
        self.pg_url = pg_url
        settings = Settings(database_url=pg_url)
        self.mes = TestClient(
            build_mes(api_key="k", chaos_enabled=True), headers={"X-API-Key": "k"}
        )
        self.detect = TestClient(build_detect(settings))
        self.api_settings = ApiSettings(
            database_url=pg_url, jwt_secret=SECRET, approval_timeout_s=600
        )
        self.agent: TestClient | None = None
        self.api = TestClient(build_api_app(self.api_settings, agent=_Lazy(self), producer=None))
        self.checkpointer = PostgresSaver.from_conn_string(
            pg_url + "?options=-c%20search_path%3Dcheckpoint"
        )
        self.saver = self.checkpointer.__enter__()
        self.saver.setup()
        self.ro = ConnectionPool(pg_url, min_size=1, max_size=4, open=True)
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
            ask=Ask("live", ROOT / "eval" / "cassettes", FakeModel()),
            fault_map=yaml.safe_load(
                (ROOT / "knowledge" / "fault_map.yaml").read_text(encoding="utf8")
            ),
        )
        self.agent = TestClient(build_http(build_graph(deps, self.saver), run_in_thread=False))

    def human(self, role: Role = Role.APPROVER) -> dict[str, str]:
        return {"Authorization": f"Bearer {mint('alice', role, SECRET)}"}


class _Lazy:
    """api -> agent client that resolves at call time, so the agent can be replaced mid-test."""

    def __init__(self, stack: Stack) -> None:
        self.stack = stack

    def post(self, url: str, *, json: Any = None) -> Any:
        assert self.stack.agent is not None
        return self.stack.agent.post(url, json=json)


@pytest.fixture(scope="module")
def stack(pg_url: str) -> Iterator[Stack]:
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, LINE)
    s = Stack(pg_url)
    yield s
    s.checkpointer.__exit__(None, None, None)


def load_golden(stack: Stack, golden_id: str) -> Golden:
    g = Golden.load(ROOT / "eval" / "goldens" / f"{golden_id}.yaml")
    scenario = Scenario.load(ROOT / "scenarios" / f"{g.scenario}.yaml", LINE)
    with psycopg.connect(stack.pg_url) as conn:
        truncate_facts(conn)
        copy_run(conn, generate(LINE, scenario.model_copy(update={"seed": g.seed})))
    return g


def triage(stack: Stack, g: Golden) -> tuple[str, dict[str, Any]]:
    assert stack.agent is not None
    eol_ts = next(  # the trigger's EOL time, as the consumer would pass it
        r[0]
        for r in psycopg.connect(stack.pg_url).execute(
            "select tested_at from qgate.fact_eol_result where vin = %s", (g.trigger.vin,)
        )
    )
    tid = stack.agent.post(
        "/triage",
        json={
            "vin": g.trigger.vin,
            "fault_codes": g.trigger.fault_codes,
            "eol_ts": eol_ts.isoformat(),
            "golden_id": g.id,
        },
    ).json()["thread_id"]
    return tid, stack.agent.get(f"/threads/{tid}").json()


def test_drift_case_waits_at_the_gate_then_commits_on_approve(stack: Stack) -> None:
    g = load_golden(stack, "drift-03")
    _, snap = triage(stack, g)
    assert snap["status"] == "WAITING_GATE", snap
    cid = snap["containment_id"]
    detail = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
    assert (
        detail["state"] == "PROPOSED"
        and detail["kind"] == "WINDOW"
        and detail["station_id"] == "ST-19"
    )
    assert (
        g.trigger.vin in detail["vins"] and stack.mes.get("/_stats").json()["holds"] == 0
    )  # nothing written yet

    r = stack.api.post(
        f"/containments/{cid}/approve", json={"reason": "looks right"}, headers=stack.human()
    )
    assert r.status_code == 200, r.text
    final = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
    assert final["state"] == "COMMITTED" and final["mes_ref"] is not None
    assert stack.mes.get(f"/v1/holds/{final['mes_ref']}").json()["vins"] == final["vins"]
    audit = next(
        a
        for a in stack.api.get("/audit", headers=stack.human()).json()
        if a["containment_id"] == cid
    )
    assert (
        audit["decision"] == "APPROVE"
        and audit["latency_total_ms"] > 0
        and audit["prompt_tokens"] == 200
    )
    # a second decision is refused (Review Focus 2)
    assert (
        stack.api.post(f"/containments/{cid}/approve", json={}, headers=stack.human()).status_code
        == 409
    )


def test_amend_is_recorded_as_a_diff_and_still_holds_the_trigger(stack: Stack) -> None:
    """Review Focus 1: a narrower amendment can never drop the vehicle that failed."""
    g = load_golden(stack, "drift-04")
    _, snap = triage(stack, g)
    cid = snap["containment_id"]
    before = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
    later_start = before["window_end"]  # absurdly narrow: start == end
    r = stack.api.post(
        f"/containments/{cid}/amend",
        headers=stack.human(),
        json={"window_start": later_start, "vins": [], "reason": "narrow it"},
    )
    assert r.status_code == 200, r.text
    final = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
    assert final["state"] == "COMMITTED"
    held = stack.mes.get(f"/v1/holds/{final['mes_ref']}").json()["vins"]
    assert held == [g.trigger.vin]
    audit = next(
        a
        for a in stack.api.get("/audit", headers=stack.human()).json()
        if a["containment_id"] == cid
    )
    assert audit["decision"] == "AMEND" and "window_start" in audit["diff"]


def test_reject_ends_the_thread_without_touching_the_plant(stack: Stack) -> None:
    g = load_golden(stack, "lot-02")
    holds_before = stack.mes.get("/_stats").json()["holds"]
    tid, snap = triage(stack, g)
    cid = snap["containment_id"]
    assert stack.api.get(f"/containments/{cid}", headers=stack.human()).json()["kind"] == "LOT"
    stack.api.post(
        f"/containments/{cid}/reject", json={"reason": "already quarantined"}, headers=stack.human()
    )
    assert (
        stack.api.get(f"/containments/{cid}", headers=stack.human()).json()["state"] == "REJECTED"
    )
    assert stack.mes.get("/_stats").json()["holds"] == holds_before
    assert stack.agent is not None and stack.agent.get(f"/threads/{tid}").json()["status"] == "DONE"


def test_bench_case_proposes_nothing(stack: Stack) -> None:
    g = load_golden(stack, "bench-02")
    _, snap = triage(stack, g)
    assert snap["status"] == "DONE" and snap["outcome"] == "NO_CONTAINMENT", snap
    row = stack.api.get(f"/containments/{snap['containment_id']}", headers=stack.human()).json()
    assert row["kind"] == "NONE" and row["state"] == "ESCALATED" and row["vin_count"] == 0


def test_restart_mid_gate_loses_nothing(stack: Stack) -> None:
    """Review Focus 5: the process that proposed dies; a fresh one resumes the same thread."""
    g = load_golden(stack, "drift-05")
    tid, snap = triage(stack, g)
    assert snap["status"] == "WAITING_GATE"
    cid = snap["containment_id"]
    holds_before = stack.mes.get("/_stats").json()["holds"]

    stack.start_agent()  # throw the old graph + app away; same checkpointer
    assert stack.agent is not None
    assert stack.agent.get(f"/threads/{tid}").json()["status"] == "WAITING_GATE"

    stack.api.post(f"/containments/{cid}/approve", json={}, headers=stack.human())
    final = stack.api.get(f"/containments/{cid}", headers=stack.human()).json()
    assert final["state"] == "COMMITTED"
    assert stack.mes.get("/_stats").json()["holds"] == holds_before + 1
    with psycopg.connect(stack.pg_url) as conn:
        n = conn.execute(
            "select count(*) from qgate.containment where thread_id = %s", (uuid.UUID(tid),)
        ).fetchone()
    assert n == (1,)
