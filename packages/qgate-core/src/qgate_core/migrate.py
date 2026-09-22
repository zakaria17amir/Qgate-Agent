"""Apply ``db/migrations/*.sql`` the way dbmate does, for tests and the eval harness.

The compose ``migrate`` container is the production path; this exists so a throwaway Postgres
can be brought to the same schema without a dbmate binary.
"""

import os
from pathlib import Path

import psycopg

ROOT = Path(os.environ.get("QGATE_ROOT", Path(__file__).parents[4]))  # repo, or /workspace
MIGRATIONS = ROOT / "db" / "migrations"


def apply_migrations(conn: psycopg.Connection, role_password: str) -> None:
    """Every "up" section in filename order, then the role passwords."""
    for path in sorted(MIGRATIONS.glob("*.sql")):
        up = path.read_text(encoding="utf8").split("-- migrate:down")[0]
        conn.execute(up.replace("-- migrate:up", ""))
    sql = (ROOT / "db" / "set_role_passwords.sql").read_text(encoding="utf8")
    conn.execute(sql.replace(":'pw'", f"'{role_password}'"))
    conn.commit()
