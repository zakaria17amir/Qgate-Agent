"""Fixtures for the chaos suite: real containers started by ``make chaos``, driven over HTTP.

Skipped unless ``CHAOS=1`` — these tests kill containers and cut network links. Credentials come
from ``.env`` (the same file compose used), never from the repository.
"""

import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from dotenv import dotenv_values

from qgate_core.auth import Role, mint
from qgate_eval.golden import Golden
from qgate_eval.runner import load_case

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.chaos

if os.environ.get("CHAOS") != "1":
    pytest.skip("set CHAOS=1 with a `make chaos` stack running", allow_module_level=True)

ENV = {k: (v or "").split("#")[0].strip() for k, v in dotenv_values(ROOT / ".env").items()}
PG_URL = (
    f"postgres://postgres:{ENV['POSTGRES_PASSWORD']}@localhost:"
    f"{ENV.get('POSTGRES_HOST_PORT') or 5432}/qgate"
)


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    token = mint("chaos", Role.APPROVER, ENV["JWT_SECRET"])
    return httpx.Client(
        base_url=os.environ.get("CHAOS_API_URL", "http://localhost:8000"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )


@pytest.fixture(scope="session")
def mes() -> httpx.Client:
    return httpx.Client(base_url="http://localhost:8003", headers={"X-API-Key": ENV["MES_API_KEY"]})


@pytest.fixture(scope="session")
def toxiproxy() -> httpx.Client:
    return httpx.Client(base_url="http://localhost:8474")


def compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "--profile", "core", "--profile", "chaos", *args], check=True
    )


def wait_for(pred: Callable[[], bool], timeout_s: float, every_s: float = 1.0) -> None:
    """Poll until ``pred`` holds; the wait is bounded and named by the caller's assertion."""
    deadline = time.monotonic() + timeout_s
    while not pred():
        if time.monotonic() > deadline:
            raise TimeoutError(f"condition not met within {timeout_s}s")
        time.sleep(every_s)


def triage_to_gate(api: httpx.Client, golden_id: str) -> dict[str, Any]:
    """Load a golden into the stack's database, trigger it, return the PROPOSED row."""
    g = Golden.load(ROOT / "eval" / "goldens" / f"{golden_id}.yaml")
    load_case(PG_URL, g)
    api.post("/triage", json={"vin": g.trigger.vin, "fault_codes": g.trigger.fault_codes})
    rows: list[dict[str, Any]] = []

    def proposed() -> bool:
        rows[:] = [
            r
            for r in api.get("/containments", params={"state": "PROPOSED"}).json()
            if r["reason"] and r["state"] == "PROPOSED"
        ]
        return bool(rows)

    wait_for(proposed, timeout_s=60)
    return rows[0]
