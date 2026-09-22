"""The agent's small HTTP surface: start a triage, look at a thread, resume a waiting gate.

The api calls ``/threads/{id}/resume`` when a human decides. Triage runs in a background thread
so the request returns at once; state lives in the checkpointer, not in this process.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel

from qgate_agent.state import Bounds
from qgate_core.health import health_app

log = logging.getLogger("agent")


class TriageRequest(BaseModel):
    vin: str
    fault_codes: list[str]
    eol_ts: datetime | None = None
    golden_id: str | None = None


class ResumeRequest(BaseModel):
    decision: str  # APPROVE | AMEND | REJECT
    actor: str
    reason: str | None = None
    bounds: Bounds | None = None  # amended bounds, when AMEND


WORKERS = 4  # concurrent triages; the rest queue — a burst on the line must not starve /health


def build_http(
    graph: CompiledStateGraph[Any, Any, Any, Any], run_in_thread: bool = True
) -> FastAPI:
    app = health_app("agent")
    pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="triage")

    def run(thread_id: str, payload: Any) -> None:
        try:
            graph.invoke(payload, config={"configurable": {"thread_id": thread_id}})
        except Exception:  # the thread state is checkpointed; the failure is visible via GET
            log.exception("triage %s failed", thread_id)

    def start(thread_id: str, payload: Any) -> None:
        if run_in_thread:
            pool.submit(run, thread_id, payload)
        else:
            run(thread_id, payload)

    @app.post("/triage", status_code=202)
    def triage(req: TriageRequest) -> dict[str, str]:
        thread_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "thread_id": thread_id,
            "vin": req.vin,
            "fault_codes": req.fault_codes,
            "golden_id": req.golden_id,
        }
        if req.eol_ts is not None:  # otherwise the genealogy node takes the vehicle's real EOL time
            payload["eol_ts"] = req.eol_ts
        start(thread_id, payload)
        return {"thread_id": thread_id}

    @app.get("/threads/{thread_id}")
    def thread(thread_id: str) -> dict[str, Any]:
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        if not snap.values:
            raise HTTPException(404, "unknown thread")
        interrupts = [i for t in snap.tasks for i in t.interrupts]
        status = "WAITING_GATE" if interrupts else "DONE" if not snap.next else "RUNNING"
        v = snap.values
        # while waiting, the gate node has not returned yet: its containment id is in the payload
        cid = interrupts[0].value["containment_id"] if interrupts else v.get("containment_id")
        return {
            "status": status,
            "next": list(snap.next),
            "outcome": v.get("outcome"),
            "containment_id": cid,
            "errors": v.get("errors", []),
            "timings_ms": v.get("timings_ms", {}),
        }

    @app.post("/threads/{thread_id}/resume", status_code=202)
    def resume(thread_id: str, req: ResumeRequest) -> dict[str, str]:
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        if not snap.values:
            raise HTTPException(404, "unknown thread")
        if not (snap.tasks and any(t.interrupts for t in snap.tasks)):
            raise HTTPException(409, "thread is not waiting at the gate")
        start(thread_id, Command(resume=req.model_dump(mode="json")))
        return {"thread_id": thread_id}

    return app
