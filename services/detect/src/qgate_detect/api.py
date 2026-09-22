"""detect's HTTP surface: on-demand drift onset and bench capability over ``detect_ro``."""

import os
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import aiosql
import numpy as np
import psycopg
from fastapi import FastAPI, HTTPException, Query
from psycopg_pool import ConnectionPool

from qgate_core.health import health_app
from qgate_core.settings import Settings
from qgate_detect.changepoint import detect_change
from qgate_detect.msa import capability

QUERIES = aiosql.from_path(
    Path(os.environ.get("QGATE_QUERIES_DIR", "db/queries")) / "detect.sql", "psycopg"
)


From = Annotated[datetime, Query(alias="from")]
To = Annotated[datetime, Query()]


def build_api(settings: Settings) -> FastAPI:
    app = health_app("detect-api")
    # opened eagerly: compose starts detect only after the database is migrated and healthy
    pool = ConnectionPool(settings.database_url, min_size=1, max_size=4, open=True)

    @app.get("/drift")
    def drift(station_id: str, characteristic_id: str, from_: From, to: To) -> dict[str, Any]:
        with pool.connection() as conn:
            _require_characteristic(conn, characteristic_id)
            rows = list(
                QUERIES.deviation_series(
                    conn,
                    station_id=station_id,
                    characteristic_id=characteristic_id,
                    start=from_,
                    end=to,
                )
            )
        stamps = [r[0] for r in rows]
        verdict = detect_change(np.array([r[1] for r in rows], dtype=float))
        body = asdict(verdict)
        body["onset"] = stamps[verdict.onset_index] if verdict.onset_index is not None else None
        body["changed_at"] = (
            stamps[verdict.change_index] if verdict.change_index is not None else None
        )
        return body

    @app.get("/bench/{bench_id}/capability")
    def bench(bench_id: str, characteristic_id: str, from_: From, to: To) -> dict[str, Any]:
        with pool.connection() as conn:
            _require_characteristic(conn, characteristic_id)
            reps = QUERIES.bench_repeats(
                conn, bench_id=bench_id, characteristic_id=characteristic_id, start=from_, end=to
            )
            repeats: dict[str, list[float]] = defaultdict(list)
            for vin, _repeat_no, dev in reps:
                repeats[vin].append(float(dev))
            values = list(
                QUERIES.bench_primary_values(
                    conn, characteristic_id=characteristic_id, start=from_, end=to
                )
            )
        own = np.array([float(d) for b, d in values if b == bench_id])
        peers = np.array([float(d) for b, d in values if b != bench_id])
        return asdict(capability(bench_id, dict(repeats), own, peers))

    return app


def _require_characteristic(conn: psycopg.Connection, characteristic_id: str) -> None:
    row = conn.execute(
        "select 1 from qgate.dim_characteristic where characteristic_id = %s", (characteristic_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"unknown characteristic {characteristic_id}")
