"""Event-driven trigger (ADR-007): every EOL FAIL on ``line.eol.results`` starts a triage.

PASS results are committed and ignored. The triage itself runs through the same HTTP handler
a manual ``POST /triage`` uses, so there is one code path whichever way a failure arrives.
"""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qgate_core import kafka
from qgate_core.models import EolResult, Result
from qgate_core.settings import Settings

log = logging.getLogger("agent-consumer")
GROUP = "agent-triage"


def run(settings: Settings, app: FastAPI, idle_timeout: float | None = None) -> None:
    kafka.ensure_topics(settings)
    # a freshly deployed agent triages failures from now on, not the whole history
    c = kafka.consumer(settings, GROUP, ["line.eol.results"], offset_reset="latest")
    local = TestClient(app)  # in-process call into our own HTTP layer
    while True:
        msg = kafka.poll(c, timeout=idle_timeout or 1.0)
        if msg is None:
            if idle_timeout is not None:
                break
            continue
        try:
            r = kafka.decode(settings, msg, EolResult)
            if r.result is Result.FAIL:
                resp = local.post(
                    "/triage",
                    json={
                        "vin": r.vin,
                        "fault_codes": r.fault_codes,
                        "eol_ts": r.tested_at.isoformat(),
                    },
                )
                log.info("triage %s for %s %s", resp.json().get("thread_id"), r.vin, r.fault_codes)
        except Exception:  # a bad record must not stop the line's triage stream
            log.exception("skip %s@%s", msg.topic(), msg.offset())
        c.commit(message=msg)
    c.close()
