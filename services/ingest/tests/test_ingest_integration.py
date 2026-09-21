"""Needs Docker: Redpanda + Postgres from the root conftest."""

import json
from pathlib import Path

import psycopg
import pytest

from qgate_core import kafka
from qgate_core.settings import Settings
from qgate_generator.line import Line
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import generate
from qgate_ingest.main import run

pytestmark = pytest.mark.integration
SCENARIOS = Path(__file__).parents[3] / "scenarios"
VEHICLES = 40


@pytest.fixture(scope="module")
def settings(kafka_settings: Settings, pg_url: str) -> Settings:
    kafka.ensure_topics(kafka_settings)
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, Line.load(SCENARIOS / "line.yaml"))
    return kafka_settings.model_copy(update={"database_url": pg_url})


def replay(settings: Settings) -> None:
    line = Line.load(SCENARIOS / "line.yaml")
    scenario = Scenario.load(SCENARIOS / "clean_baseline.yaml", line)
    p = kafka.producer(settings)
    for e in generate(line, scenario.model_copy(update={"vehicles": VEHICLES})).events:
        kafka.produce(settings, p, e)
    p.flush(30)


def counts(settings: Settings) -> dict[str, int]:
    with psycopg.connect(settings.database_url) as conn:
        return {
            t: conn.execute(f"select count(*) from qgate.{t}").fetchone()[0]  # type: ignore[index]
            for t in ("fact_build_event", "fact_measurement", "fact_eol_result")
        }


def test_replaying_the_same_stream_twice_does_not_duplicate_facts(settings: Settings) -> None:
    replay(settings)
    run(settings, group="ingest-test", idle_timeout=5)
    first = counts(settings)
    assert first["fact_build_event"] == VEHICLES * 30
    assert first["fact_eol_result"] == VEHICLES
    assert first["fact_measurement"] >= VEHICLES * 38

    replay(settings)
    run(settings, group="ingest-test", idle_timeout=5)
    assert counts(settings) == first


def test_poison_message_goes_to_dlq_and_consumer_continues(settings: Settings) -> None:
    p = kafka.producer(settings)
    p.produce("line.eol.results", key=b"POISON", value=b"\x00not-avro")
    p.flush(10)
    before = counts(settings)["fact_eol_result"]
    replay(settings)  # valid records after the poison
    run(settings, group="ingest-dlq", idle_timeout=5)

    dlq = kafka.consumer(settings, "dlq-reader", [kafka.DLQ_TOPIC])
    msg = kafka.poll(dlq, timeout=20)
    assert msg is not None
    body = json.loads(msg.value())  # type: ignore[arg-type]
    assert body["topic"] == "line.eol.results" and "error" in body
    assert counts(settings)["fact_eol_result"] >= before  # the good records still landed
