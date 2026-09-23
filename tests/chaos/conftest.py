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

if os.environ.get("CHAOS") != "1":
    pytest.skip("set CHAOS=1 with a `make chaos` stack running", allow_module_level=True)

ENV = {k: (v or "").split("#")[0].strip() for k, v in dotenv_values(ROOT / ".env").items()}
PG_URL = (  # the migrate role: the suite loads a golden's run into the stack's fact tables
    f"postgres://qgate_migrate:{ENV['POSTGRES_PASSWORD']}@localhost:"
    f"{ENV.get('POSTGRES_HOST_PORT') or 15432}/qgate"
)


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    token = mint("chaos", Role.APPROVER, ENV["JWT_SECRET"])
    return httpx.Client(
        base_url=os.environ.get("CHAOS_API_URL", "http://localhost:8000"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
        transport=httpx.HTTPTransport(retries=3),  # pooled connections die when containers churn
    )


@pytest.fixture(scope="session")
def mes() -> httpx.Client:
    return httpx.Client(base_url="http://localhost:8003", headers={"X-API-Key": ENV["MES_API_KEY"]})


@pytest.fixture(scope="session")
def toxiproxy() -> httpx.Client:
    return httpx.Client(base_url="http://localhost:8474")


@pytest.fixture(scope="session")
def pg_url() -> str:
    return PG_URL


@pytest.fixture(scope="session")
def compose() -> Callable[..., None]:
    def run(*args: str) -> None:
        cmd = ["docker", "compose", "--profile", "core", "--profile", "chaos", *args]
        # same interpolation as `make chaos`, or `up -d agent` would recreate it bypassing toxiproxy
        env = {**os.environ, "MES_BASE_URL": "http://toxiproxy:8003"}
        subprocess.run(cmd, check=True, env=env)

    return run


def committed(api: httpx.Client) -> int:
    return len(api.get("/containments", params={"state": "COMMITTED"}).json())


def wait_for(pred: Callable[[], bool], timeout_s: float, every_s: float = 1.0) -> None:
    """Poll until ``pred`` holds; the wait is bounded and named by the caller's assertion."""
    deadline = time.monotonic() + timeout_s
    while not pred():
        if time.monotonic() > deadline:
            raise TimeoutError(f"condition not met within {timeout_s}s")
        time.sleep(every_s)


@pytest.fixture(scope="session")
def wait() -> Callable[..., None]:
    return wait_for


@pytest.fixture
def triage_to_gate(api: httpx.Client) -> Callable[[str], dict[str, Any]]:
    """Load a golden into the stack's database, trigger it, return the PROPOSED row."""

    def go(golden_id: str) -> dict[str, Any]:
        g = Golden.load(ROOT / "eval" / "goldens" / f"{golden_id}.yaml")
        load_case(PG_URL, g)
        tid = api.post(
            "/triage", json={"vin": g.trigger.vin, "fault_codes": g.trigger.fault_codes}
        ).json()["thread_id"]
        rows: list[dict[str, Any]] = []

        def proposed() -> bool:
            rows[:] = [
                r
                for r in api.get("/containments", params={"state": "PROPOSED"}).json()
                if r["thread_id"] == tid
            ]
            return bool(rows)

        wait_for(proposed, timeout_s=60)
        return rows[0]

    return go
