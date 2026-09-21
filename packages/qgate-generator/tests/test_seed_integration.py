from pathlib import Path

import psycopg
import pytest

from qgate_generator.line import Line
from qgate_generator.seed import seed_dims

pytestmark = pytest.mark.integration
LINE = Line.load(Path(__file__).parents[3] / "scenarios" / "line.yaml")


def test_seed_dims_is_idempotent(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, LINE)
        seed_dims(conn, LINE)
        counts = {
            t: conn.execute(f"select count(*) from qgate.{t}").fetchone()[0]  # type: ignore[index]
            for t in ("dim_station", "dim_characteristic", "dim_shift", "dim_bench")
        }
    assert counts == {"dim_station": 30, "dim_characteristic": 38, "dim_shift": 3, "dim_bench": 4}
