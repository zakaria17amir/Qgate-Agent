"""Consume the three ``line.*`` topics into Postgres.

At-least-once: the offset is committed only after the row is in the database. Anything that
cannot be decoded, validated or written goes to ``line.dlq`` with the reason, and the offset is
committed so one bad message never stalls the line.
"""

import logging
import threading

import psycopg
from confluent_kafka import Message, Producer
from pydantic import BaseModel

from qgate_core import kafka, metrics
from qgate_core.health import health_app, ok, serve
from qgate_core.models import TOPIC, BuildEvent, EolResult, LineRecord, Measurement
from qgate_core.settings import Settings
from qgate_ingest.upsert import upsert

log = logging.getLogger("ingest")
MODELS: dict[str, type[BaseModel]] = {TOPIC[m]: m for m in (BuildEvent, Measurement, EolResult)}
app = health_app("ingest", lambda: {"kafka": ok(lambda: kafka.reachable(Settings()))})


def run(settings: Settings, group: str = "ingest", idle_timeout: float | None = None) -> None:
    """Poll forever, or until ``idle_timeout`` seconds pass with no message (used by tests)."""
    kafka.ensure_topics(settings)  # a consumer must not depend on a producer having run first
    consumer = kafka.consumer(settings, group, list(MODELS))
    dlq = kafka.producer(settings)
    with psycopg.connect(settings.database_url) as conn:
        while True:
            msg = kafka.poll(consumer, timeout=idle_timeout or 1.0)
            if msg is None:
                if idle_timeout is not None:
                    break
                continue
            handle(settings, conn, dlq, msg)
            consumer.commit(message=msg)
    dlq.flush(10)
    consumer.close()


def handle(settings: Settings, conn: psycopg.Connection, dlq: Producer, msg: Message) -> bool:
    """Write one message; return True if it was parked in the DLQ instead.

    Bad *messages* (undecodable, invalid, constraint-violating) are parked so the line never
    stalls on one record. A lost *database* is not a message problem: it propagates, the offset
    stays uncommitted, and the message is redelivered when the service comes back.
    """
    topic = msg.topic() or ""
    try:
        record = kafka.decode(settings, msg, MODELS[topic])
        upsert(conn, _as_line_record(record))
        conn.commit()
        metrics.INGEST_RECORDS.labels(topic=topic, result="ok").inc()
        return False
    except psycopg.OperationalError:
        raise
    except Exception as e:
        conn.rollback()
        log.warning("dlq %s@%s: %s", topic, msg.offset(), e)
        kafka.send_to_dlq(dlq, msg, e)
        metrics.INGEST_RECORDS.labels(topic=topic, result="dlq").inc()
        return True


def _as_line_record(record: BaseModel) -> LineRecord:
    assert isinstance(record, BuildEvent | Measurement | EolResult)
    return record


def main() -> None:
    logging.basicConfig(level="INFO")
    settings = Settings()
    threading.Thread(target=serve, args=(app,), daemon=True).start()
    run(settings)
