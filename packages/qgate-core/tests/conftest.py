"""Shared integration fixtures: a migrated Postgres. Needs Docker."""

from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "db" / "migrations"
ROLE_PASSWORD = "test-pw"  # throwaway container


def apply_migrations(conn: psycopg.Connection) -> None:
    """Apply every ``db/migrations/*.sql`` "up" section in filename order (what dbmate does)."""
    for path in sorted(MIGRATIONS.glob("*.sql")):
        up = path.read_text(encoding="utf8").split("-- migrate:down")[0]
        conn.execute(up.replace("-- migrate:up", ""))
    sql = (ROOT / "db" / "set_role_passwords.sql").read_text(encoding="utf8")
    conn.execute(sql.replace(":'pw'", f"'{ROLE_PASSWORD}'"))
    conn.commit()


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Connection URL (as the migrate owner) to a fresh, fully migrated database."""
    with PostgresContainer("postgres:16.4", username="qgate_migrate", dbname="qgate") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        with psycopg.connect(url) as conn:
            apply_migrations(conn)
        yield url


@pytest.fixture(scope="session")
def role_url(pg_url: str) -> Callable[[str], str]:
    """Same server, connected as one of the least-privilege application roles."""
    host_part = pg_url.split("://", 1)[1].split("@", 1)[1]
    return lambda role: f"postgresql://{role}:{ROLE_PASSWORD}@{host_part}"
