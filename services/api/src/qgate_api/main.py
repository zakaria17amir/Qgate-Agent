"""The public api: proposals in, human decisions out, audit for everyone.

Owns the containment tables (ADR-008). Talks to the agent only to resume a waiting thread and
to Kafka only to announce state changes; both are optional so the eval harness can run the api
in-process on Postgres alone.
"""

import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol

import httpx
from confluent_kafka import Producer
from fastapi import Depends, FastAPI, HTTPException
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from qgate_api import store
from qgate_core import kafka
from qgate_core.auth import Principal, Role, mint, require
from qgate_core.health import health_app, ok, serve
from qgate_core.models import ContainmentEvent, State
from qgate_core.settings import Settings

log = logging.getLogger("api")


class ApiSettings(Settings):
    jwt_secret: str = "dev-only-change-me"  # noqa: S105 — overridden by JWT_SECRET in .env
    approval_timeout_s: int = 1800  # env APPROVAL_TIMEOUT_S
    agent_base_url: str = "http://agent:8001"


class AgentClient(Protocol):
    """What the api needs from the agent: a way to resume a waiting thread."""

    def post(self, url: str, *, json: Any = None) -> Any: ...
    def get(self, url: str) -> Any: ...


def build_app(
    settings: ApiSettings, agent: AgentClient | None, producer: Producer | None
) -> FastAPI:
    pool = ConnectionPool(settings.database_url, min_size=1, max_size=8, open=True)

    def db() -> None:
        with pool.connection() as conn:
            conn.execute("select 1")

    def ready() -> dict[str, bool]:
        checks = {"db": ok(db)}
        if agent is not None:
            checks["agent"] = ok(lambda: agent.get("/health").raise_for_status())
        return checks

    app = health_app("api", ready)
    timeout = timedelta(seconds=settings.approval_timeout_s)
    viewer = require(Role.VIEWER, Role.APPROVER, Role.ADMIN, secret=settings.jwt_secret)
    approver = require(Role.APPROVER, Role.ADMIN, secret=settings.jwt_secret)
    service = require(Role.SERVICE, secret=settings.jwt_secret)

    def announce(row: dict[str, Any], actor: str) -> None:
        if producer is None:
            return
        event = ContainmentEvent(
            containment_id=str(row["containment_id"]),
            thread_id=str(row["thread_id"]),
            state=State(row["state"]),
            occurred_at=datetime.now(UTC),
            actor=actor,
            station_id=row["station_id"],
            window_start=row["window_start"],
            window_end=row["window_end"],
            lot_ids=list(row["lot_ids"]),
            vin_count=row["vin_count"],
            mes_ref=row["mes_ref"],
        )
        kafka.produce(settings, producer, event)

    @app.post("/internal/containments", status_code=201, dependencies=[Depends(service)])
    def create(p: store.Proposal) -> dict[str, str]:
        with pool.connection() as conn:
            cid = store.propose(conn, p, timeout)
            row = store.get(conn, cid)
        assert row is not None
        announce(row, "agent")
        return {"containment_id": str(cid)}

    @app.patch("/internal/containments/{cid}", dependencies=[Depends(service)])
    def outcome(cid: uuid.UUID, o: store.Outcome) -> dict[str, Any]:
        with pool.connection() as conn:
            if not store.record_outcome(conn, cid, o):
                raise HTTPException(404, "no such containment")
            row = store.get(conn, cid)
        assert row is not None
        announce(row, "agent")
        return row

    class TriageRequest(BaseModel):
        vin: str
        fault_codes: list[str]

    @app.post("/triage", status_code=202, dependencies=[Depends(approver)])
    def triage(req: TriageRequest) -> dict[str, Any]:
        """Manual trigger; the normal path is the agent's own EOL consumer (ADR-007)."""
        if agent is None:
            raise HTTPException(503, "no agent configured")
        r = agent.post("/triage", json=req.model_dump())
        if r.status_code >= 300:
            raise HTTPException(502, f"agent refused: {r.text}")
        return dict(r.json())

    @app.get("/containments", dependencies=[Depends(viewer)])
    def list_(state: str | None = None) -> list[dict[str, Any]]:
        with pool.connection() as conn:
            return store.list_by_state(conn, state)

    @app.get("/containments/{cid}", dependencies=[Depends(viewer)])
    def get_one(cid: uuid.UUID) -> dict[str, Any]:
        with pool.connection() as conn:
            row = store.get(conn, cid)
        if row is None:
            raise HTTPException(404, "no such containment")
        return row

    @app.get("/audit", dependencies=[Depends(viewer)])
    def audit() -> list[dict[str, Any]]:
        with pool.connection() as conn:
            return store.audit(conn)

    def decide(cid: uuid.UUID, d: store.Decision) -> dict[str, Any]:
        """Shared by approve/amend/reject: persist, announce, wake the waiting thread."""
        with pool.connection() as conn:
            row = store.decide(conn, cid, d)
        if row is None:
            raise HTTPException(409, "containment is not awaiting a decision")
        announce(row, d.actor)
        if agent is not None:
            bounds = {
                k: row[k] for k in ("kind", "station_id", "window_start", "window_end", "lot_ids")
            }
            resume = {
                "decision": d.action,
                "actor": d.actor,
                "reason": d.reason,
                "bounds": {**bounds, "vins": row["vins"]},
            }
            r = agent.post(f"/threads/{row['thread_id']}/resume", json=_jsonable(resume))
            if r.status_code >= 300:
                log.error("resume failed for %s: %s %s", cid, r.status_code, r.text)
        return row

    class Reason(store.Decision):
        action: str = Field(default="", exclude=True)
        actor: str = Field(default="", exclude=True)

    @app.post("/containments/{cid}/approve")
    def approve(
        cid: uuid.UUID, body: Reason, p: Annotated[Principal, Depends(approver)]
    ) -> dict[str, Any]:
        return decide(cid, store.Decision(action="APPROVE", actor=p.sub, reason=body.reason))

    @app.post("/containments/{cid}/amend")
    def amend(
        cid: uuid.UUID, body: Reason, p: Annotated[Principal, Depends(approver)]
    ) -> dict[str, Any]:
        d = store.Decision(
            **body.model_dump(exclude={"action", "actor"}), action="AMEND", actor=p.sub
        )
        return decide(cid, d)

    @app.post("/containments/{cid}/reject")
    def reject(
        cid: uuid.UUID, body: Reason, p: Annotated[Principal, Depends(approver)]
    ) -> dict[str, Any]:
        return decide(cid, store.Decision(action="REJECT", actor=p.sub, reason=body.reason))

    def sweep_forever() -> None:
        while True:
            time.sleep(30)  # the sweeper's cadence; expiry granularity is 30 s
            try:
                with pool.connection() as conn:
                    for cid in store.sweep_expired(conn, datetime.now(UTC)):
                        row = store.get(conn, cid)
                        if row is not None:
                            announce(row, "system")
                            if agent is not None:  # the graph must learn the gate closed
                                agent.post(
                                    f"/threads/{row['thread_id']}/resume",
                                    json={
                                        "decision": "REJECT",
                                        "actor": "system",
                                        "reason": "expired",
                                    },
                                )
            except Exception:  # keep sweeping; a transient error must not kill the thread
                log.exception("sweep failed")

    app.state.sweep_forever = sweep_forever
    return app


def _jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, datetime | uuid.UUID):
        return str(o.isoformat() if isinstance(o, datetime) else o)
    return o


def main() -> None:
    logging.basicConfig(level="INFO")
    settings = ApiSettings()
    agent = httpx.Client(
        base_url=settings.agent_base_url,
        timeout=10,
        headers={"Authorization": f"Bearer {mint('api', Role.SERVICE, settings.jwt_secret)}"},
    )
    app = build_app(settings, agent, kafka.producer(settings))
    threading.Thread(target=app.state.sweep_forever, daemon=True).start()
    serve(app)
