"""Load a generated run straight into Postgres with COPY, bypassing Kafka.

For tests and demos that need a filled database in seconds. Ingest remains the production path;
this loader assumes empty fact tables (``truncate_facts`` first) and lets a duplicate key fail.
"""

import psycopg

from qgate_core.models import BuildEvent, EolResult, Measurement
from qgate_generator.stream import Run

FACT_TABLES = ("fact_eol_fault", "fact_eol_result", "fact_measurement", "fact_build_event")


def truncate_facts(conn: psycopg.Connection) -> None:
    conn.execute("truncate " + ", ".join(f"qgate.{t}" for t in FACT_TABLES))
    conn.commit()


def copy_run(conn: psycopg.Connection, run: Run) -> None:
    builds = [e for e in run.events if isinstance(e, BuildEvent)]
    measurements = [e for e in run.events if isinstance(e, Measurement)]
    eols = [e for e in run.events if isinstance(e, EolResult)]
    with conn.cursor() as cur:
        with cur.copy(
            "copy qgate.fact_build_event (vin, station_id, sequence_no, entered_at, shift_id, "
            "operator_id, parts_lots) from stdin"
        ) as cp:
            for b in builds:
                cp.write_row(
                    (
                        b.vin,
                        b.station_id,
                        b.sequence_no,
                        b.entered_at,
                        b.shift_id,
                        b.operator_id,
                        b.parts_lots,
                    )
                )
        with cur.copy(
            "copy qgate.fact_measurement (vin, station_id, characteristic_id, bench_id, "
            "measured_at, value, nominal, lower_limit, upper_limit, repeat_no) from stdin"
        ) as cp:
            for m in measurements:
                cp.write_row(
                    (
                        m.vin,
                        m.station_id,
                        m.characteristic_id,
                        m.bench_id,
                        m.measured_at,
                        m.value,
                        m.nominal,
                        m.lower_limit,
                        m.upper_limit,
                        m.repeat_no,
                    )
                )
        with cur.copy(
            "copy qgate.fact_eol_result (vin, tested_at, bench_id, result) from stdin"
        ) as cp:
            for e in eols:
                cp.write_row((e.vin, e.tested_at, e.bench_id, e.result.value))
        with cur.copy("copy qgate.fact_eol_fault (vin, tested_at, fault_code) from stdin") as cp:
            for e in eols:
                for code in e.fault_codes:
                    cp.write_row((e.vin, e.tested_at, code))
    conn.commit()
