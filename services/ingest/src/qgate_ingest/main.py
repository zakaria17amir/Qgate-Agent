"""Consume the three ``line.*`` topics into Postgres.

At-least-once: the offset is committed only after the row is in the database. Anything that
cannot be decoded, validated or written goes to ``line.dlq`` with the reason, and the offset is
committed so one bad message never stalls the line.
"""

import logging
import threading

import psycopg
from pydantic import BaseModel

from qgate_core import kafka
from qgate_core.health import health_app, serve
from qgate_core.models import TOPIC, BuildEvent, EolResult, LineRecord, Measurement
from qgate_core.settings import Settings
from qgate_ingest.upsert import upsert

log = logging.getLogger("ingest")
MODELS: dict[str, type[BaseModel]] = {TOPIC[m]: m for m in (BuildEvent, Measurement, EolResult)}
app = health_app("ingest")


def run(settings: Settings, group: str = "ingest", idle_timeout: float | None = None) -> None:
    """Poll forever, or until ``idle_timeout`` seconds pass with no message (used by tests)."""
    consumer = kafka.consumer(settings, group, list(MODELS))
    dlq = kafka.producer(settings)
    with psycopg.connect(settings.database_url) as conn:
        while True:
            msg = kafka.poll(consumer, timeout=idle_timeout or 1.0)
            if msg is None:
                if idle_timeout is not None:
                    break
                continue
            try:
                record = kafka.decode(settings, msg, MODELS[msg.topic() or ""])
                upsert(conn, _as_line_record(record))
                conn.commit()
            except Exception as e:  # anything unwritable is parked, not fatal
                conn.rollback()
                log.warning("dlq %s@%s: %s", msg.topic(), msg.offset(), e)
                kafka.send_to_dlq(dlq, msg, e)
            consumer.commit(message=msg)
    dlq.flush(10)
    consumer.close()


def _as_line_record(record: BaseModel) -> LineRecord:
    assert isinstance(record, BuildEvent | Measurement | EolResult)
    return record


def main() -> None:
    logging.basicConfig(level="INFO")
    settings = Settings()
    threading.Thread(target=serve, args=(app,), daemon=True).start()
    run(settings)
