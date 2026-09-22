"""Design §9.3: the agent dies while a gate is pending; a fresh container resumes the thread."""

from collections.abc import Callable
from typing import Any

import httpx
import psycopg


def test_agent_restart_mid_gate_loses_nothing(
    api: httpx.Client,
    mes: httpx.Client,
    pg_url: str,
    compose: Callable[..., None],
    triage_to_gate: Callable[[str], dict[str, Any]],
    wait: Callable[..., None],
) -> None:
    row = triage_to_gate("drift-05")
    cid = row["containment_id"]
    holds_before = mes.get("/_stats").json()["holds"]

    compose("kill", "agent")
    compose("up", "-d", "agent")
    wait(lambda: api.get("/ready").status_code == 200, timeout_s=90)

    api.post(f"/containments/{cid}/approve", json={}).raise_for_status()
    wait(lambda: api.get(f"/containments/{cid}").json()["state"] == "COMMITTED", timeout_s=60)
    assert mes.get("/_stats").json()["holds"] == holds_before + 1
    with psycopg.connect(pg_url) as conn:
        n = conn.execute(
            "select count(*) from qgate.containment where thread_id = %s", (row["thread_id"],)
        ).fetchone()
    assert n == (1,)
