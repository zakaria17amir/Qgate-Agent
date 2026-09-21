"""Idempotent writes: every statement is ``insert ... on conflict do nothing`` on a natural key,
so a Kafka redelivery (at-least-once) is a no-op instead of a duplicate."""

import psycopg

from qgate_core.models import BuildEvent, EolResult, LineRecord, Measurement


def upsert(conn: psycopg.Connection, record: LineRecord) -> None:
    match record:
        case BuildEvent():
            conn.execute(
                "insert into qgate.fact_build_event "
                "(vin, station_id, sequence_no, entered_at, shift_id, operator_id, parts_lots) "
                "values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                (
                    record.vin,
                    record.station_id,
                    record.sequence_no,
                    record.entered_at,
                    record.shift_id,
                    record.operator_id,
                    record.parts_lots,
                ),
            )
        case Measurement():
            conn.execute(
                "insert into qgate.fact_measurement (vin, station_id, characteristic_id, bench_id, "
                "measured_at, value, nominal, lower_limit, upper_limit, repeat_no) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
                (
                    record.vin,
                    record.station_id,
                    record.characteristic_id,
                    record.bench_id,
                    record.measured_at,
                    record.value,
                    record.nominal,
                    record.lower_limit,
                    record.upper_limit,
                    record.repeat_no,
                ),
            )
        case EolResult():
            conn.execute(
                "insert into qgate.fact_eol_result (vin, tested_at, bench_id, result) "
                "values (%s, %s, %s, %s) on conflict do nothing",
                (record.vin, record.tested_at, record.bench_id, record.result.value),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into qgate.fact_eol_fault (vin, tested_at, fault_code) "
                    "values (%s, %s, %s) on conflict do nothing",
                    [(record.vin, record.tested_at, code) for code in record.fault_codes],
                )
