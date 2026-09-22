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
from fastapi.middleware.cors import CORSMiddleware
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
    cors_origins: str = "http://localhost:8080,http://localhost:4173,http://localhost:5173"


class AgentClient(Protocol):
    """What the api needs from the agent: a way to resume a waiting thread."""

    def post(self, url: str, *, json: Any = None) -> Any: ...


def build_app(
    settings: ApiSettings, agent: AgentClient | None, producer: Producer | None
) -> FastAPI:
    pool = ConnectionPool(settings.database_url, min_size=1, max_size=8, open=True)

    def db() -> None:
        with pool.connection() as conn:
            conn.execute("select 1")

    def ready() -> dict[str, bool]:
        # db only: the agent depends on the api being ready, so the api must not wait for the agent
        return {"db": ok(db)}

    app = health_app("api", ready)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )
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

    @app.get("/containments/{cid}/preview", dependencies=[Depends(viewer)])
    def preview(
        cid: uuid.UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        lot_ids: str | None = None,
    ) -> dict[str, Any]:
        """What an amendment *would* hold: the console's live VIN count."""
        with pool.connection() as conn:
            row = store.get(conn, cid)
            if row is None:
                raise HTTPException(404, "no such containment")
            row.update(
                {
                    k: v
                    for k, v in {
                        "window_start": window_start,
                        "window_end": window_end,
                        "lot_ids": lot_ids.split(",") if lot_ids else None,
                    }.items()
                    if v is not None
                }
            )
            vins = store.scope_vins(conn, row)
        return {"vin_count": len(vins), "vins": vins}

    @app.get("/audit", dependencies=[Depends(viewer)])
    def audit() -> list[dict[str, Any]]:
        with pool.connection() as conn:
            return store.audit(conn)

    def resume(row: dict[str, Any], body: dict[str, Any]) -> None:
        """Wake the thread. Never raises: the decision is already in Postgres, and the sweeper
        re-sends it until the agent takes it; 409 means a worker already has it."""
        if agent is None:
            return
        try:
            r = agent.post(f"/threads/{row['thread_id']}/resume", json=_jsonable(body))
        except httpx.HTTPError as e:
            log.warning(
                "agent unreachable; %s will be re-sent by the sweeper: %s", row["thread_id"], e
            )
            return
        if r.status_code == 409:
            log.info("thread %s not waiting; skipped", row["thread_id"])
        elif r.status_code >= 300:
            log.error("resume of %s failed: %s %s", row["thread_id"], r.status_code, r.text)

    def human_resume(row: dict[str, Any], action: str, actor: str, reason: str | None) -> None:
        bounds = {
            k: row[k] for k in ("kind", "station_id", "window_start", "window_end", "lot_ids")
        }
        resume(
            row,
            {
                "decision": action,
                "actor": actor,
                "reason": reason,
                "bounds": {**bounds, "vins": row["vins"]},
            },
        )

    def decide(cid: uuid.UUID, d: store.Decision) -> dict[str, Any]:
        """Shared by approve/amend/reject: persist, announce, wake the waiting thread."""
        with pool.connection() as conn:
            row = store.decide(conn, cid, d)
        if row is None:
            raise HTTPException(409, "containment is not awaiting a decision")
        announce(row, d.actor)
        human_resume(row, d.action, d.actor, d.reason)
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

    def sweep() -> None:
        """One pass: expire stale proposals; re-send decisions the agent has not acted on
        (it was down, or died between the gate and the plant write); retry parked commits."""
        with pool.connection() as conn:
            for cid in store.sweep_expired(conn, datetime.now(UTC)):
                row = store.get(conn, cid)
                if row is not None:
                    announce(row, "system")
                    # the graph must learn the gate closed
                    resume(row, {"decision": "REJECT", "actor": "system", "reason": "expired"})
            decided = [  # with VIN lists: an AMEND re-scoped the row; the agent takes it as is
                full
                for r in store.list_by_state(conn, "APPROVED,AMENDED,REJECTED")
                if (full := store.get(conn, r["containment_id"])) is not None
            ]
            parked = store.list_by_state(conn, "COMMIT_PENDING")
        for row in decided:
            action = {"APPROVED": "APPROVE", "AMENDED": "AMEND"}.get(row["state"], "REJECT")
            human_resume(row, action, row["decided_by"] or "system", None)
        for row in parked:
            resume(row, {"decision": "RETRY", "actor": "system", "reason": "sweeper"})

    def sweep_forever() -> None:
        while True:
            time.sleep(30)  # the sweeper's cadence; expiry granularity and retry clock are 30 s
            try:
                sweep()
            except Exception:  # keep sweeping; a transient error must not kill the thread
                log.exception("sweep failed")

    app.state.sweep = sweep
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
