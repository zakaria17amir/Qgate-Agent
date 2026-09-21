"""Needs Docker: spins up a Redpanda (Kafka + schema registry) container."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from qgate_core import kafka
from qgate_core.models import Measurement
from qgate_core.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> Iterator[Settings]:
    image = "redpandadata/redpanda:v24.2.7"
    # Two listeners, as in docker-compose.yml: the registry inside the container talks to the
    # internal one; tests on the host reach the external one through the mapped port.
    cmd = (
        "redpanda start --smp 1 --memory 512M --overprovisioned "
        "--kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092 "
        "--advertise-kafka-addr internal://127.0.0.1:9092,external://localhost:29092 "
        "--schema-registry-addr 0.0.0.0:8081"
    )
    with (
        DockerContainer(image)
        .with_bind_ports(19092, 29092)
        .with_bind_ports(8081, 28081)
        .with_command(cmd) as c
    ):
        wait_for_logs(c, "Successfully started Redpanda!", timeout=60)
        for _ in range(
            60
        ):  # the schema registry finishes bootstrapping a few seconds after the broker
            try:
                if httpx.get("http://localhost:28081/subjects").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        yield Settings(
            kafka_bootstrap="localhost:29092", schema_registry_url="http://localhost:28081"
        )


def test_topics_are_created_with_designed_partitions(settings: Settings) -> None:
    kafka.ensure_topics(settings)
    kafka.ensure_topics(settings)  # idempotent
    meta = kafka.producer(settings).list_topics(timeout=10).topics
    assert len(meta["line.measurements"].partitions) == 6
    assert len(meta["quality.alerts"].partitions) == 3
    assert len(meta["line.dlq"].partitions) == 1


def test_measurement_round_trips_through_the_registry(settings: Settings) -> None:
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
    msg = kafka.poll_record(settings, consumer, Measurement, timeout=20)
    assert msg is not None and msg.record == m and msg.key == "SYN1"
