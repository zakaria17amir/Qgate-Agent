"""Genealogy query budget: index scans only, median < 50 ms at 1M measurement rows."""

import json
import statistics
import time
from pathlib import Path
from typing import Any

import aiosql
import psycopg
import pytest

from qgate_generator.line import Line
from qgate_generator.seed import seed_dims

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
QUERIES = aiosql.from_path(ROOT / "db" / "queries", "psycopg")
VINS = 27_000  # x 38 characteristics = ~1M fact_measurement rows


@pytest.fixture(scope="module")
def loaded(pg_url: str) -> str:
    """Bulk-load a synthetic genealogy with plain SQL (fast) rather than through the generator."""
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, Line.load(ROOT / "scenarios" / "line.yaml"))
        conn.execute(
            """
            insert into qgate.fact_build_event
              (vin, station_id, sequence_no, entered_at, shift_id, operator_id, parts_lots)
            select 'BENCH' || lpad(v::text, 12, '0'), s.station_id, v,
                   timestamptz '2026-01-05 06:00+00'
                     + make_interval(secs => (v + s.sequence_pos) * 60),
                   'S1', 'OP', case when s.fits_lot then array['L-' || v / 25 %% 8] else '{}' end
            from generate_series(0, %s) v cross join qgate.dim_station s
            on conflict do nothing
            """,
            (VINS - 1,),
        )
        conn.execute(
            """
            insert into qgate.fact_measurement
              (vin, station_id, characteristic_id, bench_id, measured_at, value,
               nominal, lower_limit, upper_limit)
            select b.vin, b.station_id, c.characteristic_id, 'INLINE', b.entered_at,
                   c.nominal + (random() - 0.5) * (c.upper_limit - c.lower_limit) / 3,
                   c.nominal, c.lower_limit, c.upper_limit
            from qgate.fact_build_event b
            join qgate.dim_characteristic c on c.station_id = b.station_id
            where b.vin like 'BENCH%'
            on conflict do nothing
            """
        )
        conn.execute("analyze qgate.fact_build_event; analyze qgate.fact_measurement")
        conn.commit()
    return pg_url


def test_genealogy_returns_full_ordered_path(loaded: str) -> None:
    with psycopg.connect(loaded) as conn:
        rows = list(QUERIES.genealogy_by_vin(conn, vin="BENCH000000000123"))
    assert len(rows) == 30
    assert [r[0] for r in rows] == [f"ST-{i:02d}" for i in range(1, 31)]
    measurements = rows[18][5]  # ST-19 (steering column): one torque characteristic
    assert measurements[0]["characteristic_id"] == "CH-19-TORQUE"
    assert {"value", "deviation", "out_of_tolerance", "bench_id", "repeat_no"} <= set(
        measurements[0]
    )


def test_genealogy_uses_indexes_and_meets_budget(loaded: str) -> None:
    sql = QUERIES.genealogy_by_vin.sql
    with psycopg.connect(loaded) as conn:
        n = conn.execute("select count(*) from qgate.fact_measurement").fetchone()
        assert n is not None and n[0] >= 1_000_000
        plan = conn.execute(
            f"explain (analyze, format json) {sql}", {"vin": "BENCH000000004242"}
        ).fetchone()
        assert plan is not None
        assert not _seq_scans_on_facts(plan[0][0]["Plan"]), json.dumps(plan[0])[:400]
        samples = []
        for i in range(20):
            t0 = time.perf_counter()
            list(QUERIES.genealogy_by_vin(conn, vin=f"BENCH{i * 997:012d}"))
            samples.append((time.perf_counter() - t0) * 1000)
    assert statistics.median(samples) < 50, f"median {statistics.median(samples):.1f} ms"


def _seq_scans_on_facts(node: dict[str, Any]) -> list[str]:
    """Relation names of fact tables the planner chose to scan sequentially (should be none)."""
    hits = []
    if node.get("Node Type") == "Seq Scan" and str(node.get("Relation Name", "")).startswith(
        "fact_"
    ):
        hits.append(str(node["Relation Name"]))
    for child in node.get("Plans", []):
        hits += _seq_scans_on_facts(child)
    return hits
