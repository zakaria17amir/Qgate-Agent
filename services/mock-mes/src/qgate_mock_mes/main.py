"""A stand-in plant MES. Deliberately shares no code with qgate-core: it is the foreign system.

Implements ``services/mock-mes/openapi.yaml``. In-memory on purpose — a restart is an empty
plant, which is fine for a mock and useful for tests. Failure injection lets the agent's commit
path prove its retries, breaker and idempotency against something that actually misbehaves.
"""

import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import uvicorn
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, BeforeValidator, Field

# The authored contract is the one the server publishes; the code is validated against it.
CONTRACT = Path(os.environ.get("MES_OPENAPI_PATH", Path(__file__).parents[2] / "openapi.yaml"))


def _iso_only(v: object) -> object:
    """A plant system does not coerce ``0`` into a timestamp: strings (or null) only."""
    if v is not None and not isinstance(v, str | datetime):
        raise ValueError("timestamp must be an ISO-8601 string")
    return v


Timestamp = Annotated[datetime | None, BeforeValidator(_iso_only)]


class HoldRequest(BaseModel):
    external_ref: str
    station_id: str | None = None
    window_start: Timestamp = None
    window_end: Timestamp = None
    lot_ids: list[str] = Field(default_factory=list)
    vins: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)


class Hold(HoldRequest):
    hold_ref: str
    created_at: datetime


class ChaosRequest(BaseModel):
    mode: Literal["latency", "error", "drop_ack"]
    seconds: int = Field(ge=0, le=600)  # 0 clears the active fault
    status: int = 503


@dataclass
class Chaos:
    """The active fault injection, if any; expires on its own."""

    mode: str | None = None
    until: float = 0.0
    status: int = 503

    def active(self) -> bool:
        if self.mode is not None and time.monotonic() > self.until:
            self.mode = None
        return self.mode is not None


def build_app(api_key: str, chaos_enabled: bool) -> FastAPI:
    app = FastAPI(title="Mock MES — Hold Management", version="1.0.0")
    authored: dict[str, Any] = yaml.safe_load(CONTRACT.read_text(encoding="utf8"))
    app.openapi = lambda: authored  # type: ignore[method-assign]
    holds: dict[str, Hold] = {}  # hold_ref -> hold
    by_key: dict[str, tuple[HoldRequest, str]] = {}  # idempotency key -> (body, hold_ref)
    stats = {"holds": 0, "duplicate_replays": 0, "duplicate_conflicts": 0}
    chaos = Chaos()

    def authed(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if x_api_key != api_key:
            raise HTTPException(401, "invalid API key")

    def maybe_misbehave() -> None:
        if not chaos.active():
            return
        if chaos.mode == "error":
            raise HTTPException(chaos.status, "injected outage")
        if chaos.mode == "latency":
            time.sleep(5)  # the injected fault: long enough to trip a sane client timeout

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "mock-mes"}

    @app.post("/v1/holds", dependencies=[Depends(authed)], status_code=201)
    def create_hold(
        body: HoldRequest,
        response: Response,
        idempotency_key: Annotated[uuid.UUID, Header()],
    ) -> Hold:
        maybe_misbehave()
        key = str(idempotency_key)
        if key in by_key:
            previous, ref = by_key[key]
            if previous != body:
                stats["duplicate_conflicts"] += 1
                raise HTTPException(409, "Idempotency-Key reused with a different body")
            stats["duplicate_replays"] += 1
            response.status_code = 200
            return holds[ref]
        hold = Hold(
            **body.model_dump(), hold_ref=f"HOLD-{len(holds) + 1:06d}", created_at=datetime.now(UTC)
        )
        holds[hold.hold_ref] = hold
        by_key[key] = (body, hold.hold_ref)
        stats["holds"] += 1
        if chaos.active() and chaos.mode == "drop_ack":  # hold exists; caller never hears back
            raise HTTPException(504, "injected dropped acknowledgement")
        return hold

    @app.get("/v1/holds/{hold_ref}", dependencies=[Depends(authed)])
    def get_hold(hold_ref: str) -> Hold:
        if hold_ref not in holds:
            raise HTTPException(404, "no such hold")
        return holds[hold_ref]

    @app.post("/_chaos", dependencies=[Depends(authed)], status_code=204)
    def set_chaos(body: ChaosRequest) -> None:
        if not chaos_enabled:
            raise HTTPException(403, "chaos disabled; set MES_CHAOS=1")
        chaos.mode, chaos.until, chaos.status = (
            body.mode,
            time.monotonic() + body.seconds,
            body.status,
        )

    @app.get("/_stats", dependencies=[Depends(authed)])
    def get_stats() -> dict[str, int]:
        return dict(stats)

    return app


app = build_app(os.environ.get("MES_API_KEY", "dev-mes-key"), os.environ.get("MES_CHAOS") == "1")


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8003")))  # noqa: S104
