"""Seed the dimension tables from ``line.yaml``. Idempotent: re-running changes nothing."""

import psycopg

from qgate_generator.line import Line


def seed_dims(conn: psycopg.Connection, line: Line) -> None:
    stations = sorted(line.stations, key=lambda s: s.sequence_pos)
    with conn.cursor() as cur:
        cur.executemany(
            "insert into qgate.dim_station (station_id, name, sequence_pos, takt_s, fits_lot) "
            "values (%s, %s, %s, %s, %s) on conflict do nothing",
            [(s.id, s.name, s.sequence_pos, line.takt_s, s.fits_lot) for s in stations],
        )
        cur.executemany(
            "insert into qgate.dim_characteristic "
            "(characteristic_id, station_id, name, unit, nominal, lower_limit, upper_limit) "
            "values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing",
            [
                (c.id, s.id, c.name, c.unit, c.nominal, c.lower_limit, c.upper_limit)
                for s in stations
                for c in s.characteristics
            ],
        )
        cur.executemany(
            "insert into qgate.dim_shift (shift_id, label, starts_at, ends_at, crew) "
            "values (%s, %s, %s, %s, %s) on conflict do nothing",
            [(s.id, s.label, s.starts_at, s.ends_at, s.crew) for s in line.shifts],
        )
        # INLINE is the pseudo-bench for stations that measure without a dedicated gauge.
        cur.executemany(
            "insert into qgate.dim_bench (bench_id, station_id, repeatability_sigma, bias) "
            "values (%s, %s, %s, %s) on conflict do nothing",
            [("INLINE", stations[0].id, 0.0, 0.0)]
            + [(b.id, b.station_id, b.repeatability_sigma, b.bias) for b in line.eol_benches],
        )
    conn.commit()
