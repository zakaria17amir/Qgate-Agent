"""The MES path: retries with backoff, and a breaker that stops hammering a dead system."""

from typing import Any

import httpx
import pytest
from tenacity import wait_none

from qgate_agent.tools import mes

pytestmark = pytest.mark.unit


class Scripted:
    """Answers each call with the next scripted status; an exception entry is raised instead."""

    def __init__(self, *script: int | Exception) -> None:
        self.script, self.calls = list(script), 0

    def post(self, url: str, *, json: Any = None, headers: Any = None) -> httpx.Response:
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return httpx.Response(step, json={"hold_ref": "H-1"}, request=httpx.Request("POST", url))


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mes, "WAIT", wait_none())


def test_transient_failures_are_retried_then_succeed() -> None:
    client = Scripted(503, httpx.ConnectError("down"), 201)
    breaker = mes.Breaker()
    r = mes.post_hold(client, breaker, "cid-1", {"vins": []})
    assert r is not None and r.status_code == 201
    assert client.calls == 3
    assert breaker.allow()


def test_exhausted_attempts_return_none_and_open_the_breaker() -> None:
    client = Scripted(*[503] * mes.ATTEMPTS)
    breaker = mes.Breaker()
    assert mes.post_hold(client, breaker, "cid-1", {}) is None
    assert client.calls == mes.ATTEMPTS
    assert not breaker.allow()


def test_open_breaker_skips_the_call() -> None:
    client = Scripted(201)
    breaker = mes.Breaker()
    breaker.failed()
    assert mes.post_hold(client, breaker, "cid-1", {}) is None
    assert client.calls == 0


def test_breaker_lets_one_probe_through_after_open_period() -> None:
    now = [1000.0]
    breaker = mes.Breaker(open_s=60, clock=lambda: now[0])
    breaker.failed()
    assert not breaker.allow()
    now[0] += 61
    assert breaker.allow()  # half-open: one probe
    assert not breaker.allow()  # a second caller still waits for the probe's verdict
    breaker.succeeded()
    assert breaker.allow()


def test_client_errors_are_not_retried() -> None:
    client = Scripted(409)
    r = mes.post_hold(client, mes.Breaker(), "cid-1", {})
    assert r is not None and r.status_code == 409
    assert client.calls == 1
