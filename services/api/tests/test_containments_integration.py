"""api owns containment state: propose, read, report outcome, expire."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from qgate_api.main import ApiSettings, build_app
from qgate_api.store import sweep_expired
from qgate_core.auth import Role, mint
from qgate_generator.line import Line
from qgate_generator.seed import seed_dims
from qgate_generator.stream import Run

pytestmark = pytest.mark.integration
SECRET = "test-secret"
ROOT = Path(__file__).parents[3]


@pytest.fixture(scope="module")
def api(pg_url: str) -> Iterator[TestClient]:
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, Line.load(ROOT / "scenarios" / "line.yaml"))
    settings = ApiSettings(database_url=pg_url, jwt_secret=SECRET, approval_timeout_s=60)
    with TestClient(build_app(settings, agent=None, producer=None)) as c:
        yield c


def auth(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint('t', role, SECRET)}"}


def proposal(vin: str = "SYN1") -> dict[str, object]:
    return {
        "thread_id": str(uuid.uuid4()),
        "kind": "WINDOW",
        "station_id": "ST-19",
        "window_start": "2026-01-05T20:00:00Z",
        "window_end": "2026-01-05T21:00:00Z",
        "lot_ids": [],
        "vins": [vin, "SYN2"],
        "confidence": 0.8,
        "reason": "torque drift",
        "draft_order": "Hold 2 vehicles built at ST-19 20:00-21:00.",
    }


def test_propose_then_read_and_list(api: TestClient) -> None:
    created = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE))
    assert created.status_code == 201, created.text
    cid = created.json()["containment_id"]
    detail = api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()
    assert (
        detail["state"] == "PROPOSED"
        and detail["vin_count"] == 2
        and detail["vins"] == ["SYN1", "SYN2"]
    )
    assert detail["expires_at"] is not None
    listed = api.get(
        "/containments", params={"state": "PROPOSED"}, headers=auth(Role.VIEWER)
    ).json()
    assert cid in {c["containment_id"] for c in listed}


def test_internal_endpoints_need_the_service_role(api: TestClient) -> None:
    assert (
        api.post("/internal/containments", json=proposal(), headers=auth(Role.APPROVER)).status_code
        == 403
    )
    assert api.get("/containments", headers={}).status_code == 401


def test_outcome_patch_records_audit_metrics(api: TestClient) -> None:
    cid = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    r = api.patch(
        f"/internal/containments/{cid}",
        headers=auth(Role.SERVICE),
        json={
            "state": "ESCALATED",
            "reason": "contradictory evidence",
            "latency_total_ms": 1200,
            "latency_llm_ms": 800,
            "latency_non_llm_ms": 400,
            "prompt_tokens": 900,
            "completion_tokens": 120,
            "cost_usd": 0.0012,
        },
    )
    assert r.status_code == 200, r.text
    audit = api.get("/audit", headers=auth(Role.VIEWER)).json()
    row = next(a for a in audit if a["containment_id"] == cid)
    assert row["latency_llm_ms"] == 800 and float(row["cost_usd"]) == 0.0012
    assert api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()["state"] == "ESCALATED"


def test_sweep_expires_stale_proposals_only(api: TestClient, pg_url: str) -> None:
    cid = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    with psycopg.connect(pg_url) as conn:
        assert sweep_expired(conn, now=datetime.now(UTC)) == []  # 60 s timeout has not passed
        expired = sweep_expired(conn, now=datetime.now(UTC) + timedelta(hours=1))
    assert uuid.UUID(cid) in expired
    assert api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()["state"] == "EXPIRED"


def test_evidence_travels_with_the_proposal(api: TestClient) -> None:
    """The console's case view reads what the agent saw, from the row, not from the agent."""
    evidence = {
        "siblings": {"vins": ["SYN2"], "by_shift": {"S1": 1}},
        "drift": {"verdict": "DRIFT"},
    }
    cid = api.post(
        "/internal/containments",
        json={**proposal(), "evidence": evidence},
        headers=auth(Role.SERVICE),
    ).json()["containment_id"]
    assert api.get(f"/containments/{cid}", headers=auth(Role.VIEWER)).json()["evidence"] == evidence


@pytest.fixture(scope="module")
def run_loaded(pg_url: str) -> Run:
    """A small tool_wear run in the fact tables, for VIN scoping."""
    from qgate_generator.load import copy_run, truncate_facts
    from qgate_generator.scenario import Scenario
    from qgate_generator.stream import generate

    line = Line.load(ROOT / "scenarios" / "line.yaml")
    scenario = Scenario.load(ROOT / "scenarios" / "tool_wear.yaml", line)
    run = generate(line, scenario.model_copy(update={"vehicles": 300}))
    with psycopg.connect(pg_url) as conn:
        truncate_facts(conn)
        copy_run(conn, run)
    return run


def _window_proposal(pg_url: str, run: Run) -> tuple[dict[str, object], str, int]:
    """A WINDOW proposal over the run's first hour at ST-19, plus a trigger built in that hour."""
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "select min(entered_at) from qgate.fact_build_event where station_id = 'ST-19'"
        ).fetchone()
        assert row is not None
        first = row[0]
        end = first + timedelta(hours=1)
        vins = [
            r[0]
            for r in conn.execute(
                "select vin from qgate.fact_build_event where station_id = 'ST-19' "
                "and entered_at >= %s and entered_at < %s order by entered_at",
                (first, end),
            )
        ]
    trigger = vins[-1]
    p = {
        **proposal(trigger),
        "window_start": first.isoformat(),
        "window_end": end.isoformat(),
        "vins": vins,
        "trigger_vin": trigger,
    }
    return p, trigger, len(vins)


def test_preview_counts_vins_the_amended_window_would_hold(
    api: TestClient, pg_url: str, run_loaded: Run
) -> None:
    p, trigger, n = _window_proposal(pg_url, run_loaded)
    cid = api.post("/internal/containments", json=p, headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    start = datetime.fromisoformat(str(p["window_start"])) + timedelta(minutes=10)
    preview = api.get(
        f"/containments/{cid}/preview",
        params={"window_start": start.isoformat()},
        headers=auth(Role.VIEWER),
    ).json()
    assert 0 < preview["vin_count"] < n and trigger in preview["vins"]


def test_amend_recomputes_vins_and_keeps_the_trigger(
    api: TestClient, pg_url: str, run_loaded: Run
) -> None:
    """Review Focus 3: a window that excludes the trigger still holds the trigger."""
    p, trigger, n = _window_proposal(pg_url, run_loaded)
    cid = api.post("/internal/containments", json=p, headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    end = datetime.fromisoformat(str(p["window_end"])) - timedelta(minutes=30)
    r = api.post(
        f"/containments/{cid}/amend",
        json={"window_end": end.isoformat(), "reason": "tool changed at :30"},
        headers=auth(Role.APPROVER),
    )
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["state"] == "AMENDED" and 0 < row["vin_count"] < n
    assert trigger in row["vins"]  # built after :30, yet the failing car is never released


def test_list_accepts_several_states(api: TestClient) -> None:
    api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE))
    api.post(
        "/internal/containments",
        json={**proposal(), "kind": "NONE", "state": "ESCALATED", "vins": []},
        headers=auth(Role.SERVICE),
    )
    states = {
        c["state"]
        for c in api.get(
            "/containments", params={"state": "PROPOSED,ESCALATED"}, headers=auth(Role.VIEWER)
        ).json()
    }
    assert states == {"PROPOSED", "ESCALATED"}


def test_console_origin_passes_cors_preflight(api: TestClient) -> None:
    r = api.options(
        "/containments",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_gate_pending_counts_proposals_awaiting_a_decision(api: TestClient, pg_url: str) -> None:
    """The gauge is counted on scrape from the table, so it is right across processes."""
    with psycopg.connect(pg_url) as conn:
        expected = conn.execute(
            "select count(*) from qgate.containment where state = 'PROPOSED'"
        ).fetchone()
    assert expected is not None
    text = api.get("/metrics").text
    assert f"gate_pending {float(expected[0])}" in text


def test_a_decision_is_counted_and_timed(api: TestClient) -> None:
    cid = api.post("/internal/containments", json=proposal(), headers=auth(Role.SERVICE)).json()[
        "containment_id"
    ]
    before = api.get("/metrics").text
    api.post(f"/containments/{cid}/reject", json={"reason": "no"}, headers=auth(Role.APPROVER))
    after = api.get("/metrics").text

    def count(text: str) -> float:
        line = next(
            (
                ln
                for ln in text.splitlines()
                if ln.startswith('gate_decisions_total{decision="REJECT"}')
            ),
            None,
        )
        return float(line.split()[-1]) if line else 0.0

    assert count(after) == count(before) + 1
    assert "gate_decision_seconds_count" in after
