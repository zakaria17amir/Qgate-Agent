"""Shared integration fixtures: a migrated Postgres and a Redpanda. Needs Docker."""

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import psycopg
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.postgres import PostgresContainer

from qgate_core.migrate import apply_migrations
from qgate_core.settings import Settings

ROOT = Path(__file__).parent
ROLE_PASSWORD = "test-pw"  # throwaway container


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Connection URL (as the migrate owner) to a fresh, fully migrated database."""
    with PostgresContainer("postgres:16.4", username="qgate_migrate", dbname="qgate") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        with psycopg.connect(url) as conn:
            apply_migrations(conn, ROLE_PASSWORD)
        yield url


@pytest.fixture(scope="session")
def role_url(pg_url: str) -> Callable[[str], str]:
    """Same server, connected as one of the least-privilege application roles."""
    host_part = pg_url.split("://", 1)[1].split("@", 1)[1]
    return lambda role: f"postgresql://{role}:{ROLE_PASSWORD}@{host_part}"


@pytest.fixture(scope="session")
def kafka_settings() -> Iterator[Settings]:
    """Bootstrap + registry URLs for a fresh Redpanda container."""
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


@pytest.fixture(scope="session")
def spans() -> "InMemorySpanExporter":
    """The process-wide tracer with an in-memory exporter. OTel accepts one provider per process,
    so every test module that looks at spans shares this one and ``clear()``s it first."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from qgate_core import otel

    exporter = InMemorySpanExporter()
    otel.configure("tests", exporter)
    return exporter
