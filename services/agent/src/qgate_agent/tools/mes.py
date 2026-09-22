"""The one write to the plant, made safe to repeat: retries with backoff behind a breaker.

The hold is idempotent on the containment id (mock-mes replays the same key with 200), so
retrying is always safe; the breaker only decides *whether* to try. When it is open the caller
parks the containment as COMMIT_PENDING and the api's sweeper asks again later (design §9.4).
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger("agent.mes")

ATTEMPTS = 5
WAIT = wait_exponential_jitter(initial=1, max=8)  # ~1+2+4+8+8 s: covers a 20 s blip, not an outage


class HttpPoster(Protocol):
    def post(self, url: str, *, json: Any = None, headers: Any = None) -> httpx.Response: ...


class Breaker:
    """Closed → open on a reported failure for ``open_s`` → half-open lets exactly one probe
    through → closed again on success. Per process; two agent replicas learn independently."""

    def __init__(self, open_s: float = 60.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.open_s, self.clock = open_s, clock
        self.opened_at: float | None = None
        self.probing = False
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            if self.opened_at is None:
                return True
            if self.probing or self.clock() - self.opened_at < self.open_s:
                return False
            self.probing = True
            return True

    def succeeded(self) -> None:
        with self.lock:
            self.opened_at, self.probing = None, False

    def failed(self) -> None:
        with self.lock:
            self.opened_at, self.probing = self.clock(), False


def _server_error(r: httpx.Response) -> bool:
    return r.status_code >= 500


def post_hold(
    client: HttpPoster, breaker: Breaker, containment_id: str, body: dict[str, Any]
) -> httpx.Response | None:
    """POST the hold; ``None`` means "not now": breaker open, or every attempt failed."""
    if not breaker.allow():
        log.warning("mes breaker open; %s parked", containment_id)
        return None
    try:
        r: httpx.Response = Retrying(
            stop=stop_after_attempt(ATTEMPTS),
            wait=WAIT,
            retry=retry_if_result(_server_error) | retry_if_exception_type(httpx.TransportError),
            reraise=True,
        )(
            client.post,
            "/v1/holds",
            headers={"Idempotency-Key": containment_id},
            json=body,
        )
    except (httpx.TransportError, RetryError) as e:  # RetryError: the last answer was a 5xx
        log.warning("mes unavailable after %d attempts: %r", ATTEMPTS, e)
        breaker.failed()
        return None
    breaker.succeeded()
    return r
