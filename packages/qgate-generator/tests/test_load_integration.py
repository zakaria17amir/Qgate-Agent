import time
from pathlib import Path

import psycopg
import pytest

from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import generate

pytestmark = pytest.mark.integration
SCENARIOS = Path(__file__).parents[3] / "scenarios"
LINE = Line.load(SCENARIOS / "line.yaml")


def test_copy_run_fills_all_fact_tables_fast(pg_url: str) -> None:
    scenario = Scenario.load(SCENARIOS / "clean_baseline.yaml", LINE)
    run = generate(LINE, scenario.model_copy(update={"vehicles": 200}))
    with psycopg.connect(pg_url) as conn:
        seed_dims(conn, LINE)
        truncate_facts(conn)
        t0 = time.perf_counter()
        copy_run(conn, run)
        elapsed = time.perf_counter() - t0
        n = {
            t: conn.execute(f"select count(*) from qgate.{t}").fetchone()[0]  # type: ignore[index]
            for t in ("fact_build_event", "fact_measurement", "fact_eol_result", "fact_eol_fault")
        }
        truncate_facts(conn)
    assert n["fact_build_event"] == 200 * 30 and n["fact_eol_result"] == 200
    assert n["fact_measurement"] >= 200 * 38 and n["fact_eol_fault"] >= 0
    assert elapsed < 5, f"{elapsed:.1f}s"
