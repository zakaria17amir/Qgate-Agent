"""Needs Docker: uses the session Redpanda from the root conftest."""

from datetime import UTC, datetime

import pytest

from qgate_core import kafka
from qgate_core.models import Measurement
from qgate_core.settings import Settings

pytestmark = pytest.mark.integration


def test_topics_are_created_with_designed_partitions(kafka_settings: Settings) -> None:
    settings = kafka_settings
    kafka.ensure_topics(settings)
    kafka.ensure_topics(settings)  # idempotent
    meta = kafka.producer(settings).list_topics(timeout=10).topics
    assert len(meta["line.measurements"].partitions) == 6
    assert len(meta["quality.alerts"].partitions) == 3
    assert len(meta["line.dlq"].partitions) == 1


def test_measurement_round_trips_through_the_registry(kafka_settings: Settings) -> None:
    settings = kafka_settings
    kafka.ensure_topics(settings)
    m = Measurement(
        vin="SYN1",
        station_id="ST-01",
        characteristic_id="CH-01-WELD",
        bench_id="INLINE",
        measured_at=datetime(2026, 1, 5, 6, tzinfo=UTC),
        value=9.5,
        unit="kA",
        nominal=9.5,
        lower_limit=8.9,
        upper_limit=10.1,
    )
    kafka.produce(settings, kafka.producer(settings), m).flush(10)

    consumer = kafka.consumer(settings, "test-rt", ["line.measurements"])
    msg = None
    for _ in range(6):  # the group join can take a few polls on a fresh broker
        if (msg := kafka.poll(consumer, timeout=10)) is not None:
            break
    assert msg is not None and kafka.decode(settings, msg, Measurement) == m
    assert msg.key() == b"SYN1"


def test_group_lag_is_high_watermark_minus_committed(kafka_settings: Settings) -> None:
    """The replay flow waits on this: exact, from the broker, no scrape delay."""
    kafka.ensure_topics(kafka_settings)
    p = kafka.producer(kafka_settings)
    for i in range(3):
        m = Measurement(
            vin=f"LAG{i}",
            station_id="ST-01",
            characteristic_id="CH-01-WELD",
            bench_id="INLINE",
            measured_at=datetime(2026, 1, 5, 6, tzinfo=UTC),
            value=9.5,
            unit="kA",
            nominal=9.5,
            lower_limit=8.9,
            upper_limit=10.1,
        )
        kafka.produce(kafka_settings, p, m)
    p.flush(10)
    c = kafka.consumer(kafka_settings, "lag-test", ["line.measurements"])
    msg = None
    for _ in range(6):  # the group join can take a few polls on a fresh broker
        if (msg := kafka.poll(c, timeout=10)) is not None:
            break
    assert msg is not None
    c.commit(message=msg, asynchronous=False)  # at least two are still unread
    assert kafka.group_lag(kafka_settings, "lag-test", ["line.measurements"]) >= 2
    while (m2 := kafka.poll(c, timeout=5)) is not None:
        c.commit(message=m2, asynchronous=False)
    assert kafka.group_lag(kafka_settings, "lag-test", ["line.measurements"]) == 0
    c.close()
