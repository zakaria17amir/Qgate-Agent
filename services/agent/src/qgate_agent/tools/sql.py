"""Read-only tools backed by named SQL, connected as ``agent_ro``."""

from collections import Counter
from datetime import datetime

import psycopg

from qgate_agent.tools.models import (
    CharacteristicSpec,
    CorrelationResult,
    EolSummary,
    Genealogy,
    MeasurementRow,
    StationSpec,
    StationVisit,
)
from qgate_core.sql import queries


def get_vehicle_genealogy(conn: psycopg.Connection, vin: str) -> Genealogy:
    """Every station the vehicle passed, in build order, with measurements, lots and shift."""
    rows = queries("genealogy").genealogy_by_vin(conn, vin=vin)
    visits = [
        StationVisit(
            station_id=station,
            entered_at=entered,
            shift_id=shift,
            operator_id=operator,
            parts_lots=list(lots),
            measurements=[MeasurementRow(**m) for m in measurements],
        )
        for station, entered, shift, operator, lots, measurements in rows
    ]
    eol_row = queries("station").eol_of(conn, vin=vin)
    eol = None
    if eol_row is not None:
        tested_at, bench_id, result, codes = eol_row
        eol = EolSummary(
            tested_at=tested_at, bench_id=bench_id, result=result, fault_codes=list(codes)
        )
    return Genealogy(vin=vin, visits=visits, eol=eol)


def get_station_spec(conn: psycopg.Connection, station_id: str) -> StationSpec:
    q = queries("station")
    row = q.station_spec(conn, station_id=station_id)
    if row is None:
        raise KeyError(station_id)
    sid, name, pos, takt, fits_lot = row
    chars = [
        CharacteristicSpec(
            characteristic_id=c, name=n, unit=u, nominal=nom, lower_limit=lo, upper_limit=hi
        )
        for c, n, u, nom, lo, hi in q.station_characteristics(conn, station_id=station_id)
    ]
    return StationSpec(
        station_id=sid,
        name=name,
        sequence_pos=pos,
        takt_s=takt,
        fits_lot=fits_lot,
        characteristics=chars,
    )


def find_correlated_failures(
    conn: psycopg.Connection,
    fault_code: str,
    station_id: str,
    start: datetime,
    end: datetime,
    exclude_vin: str | None = None,
) -> CorrelationResult:
    """Other vehicles with the same code that passed the station, broken down by shift and lot."""
    rows = list(
        queries("correlate").correlated_failures(
            conn,
            fault_code=fault_code,
            station_id=station_id,
            start=start,
            end=end,
            exclude_vin=exclude_vin,
        )
    )
    by_shift = Counter(shift for _, shift, _, _, _ in rows)
    by_lot = Counter(lot for _, _, lots, _, _ in rows for lot in lots)
    return CorrelationResult(
        fault_code=fault_code,
        station_id=station_id,
        vins=[r[0] for r in rows],
        entered_at=[r[3] for r in rows],
        by_shift=dict(by_shift),
        by_lot=dict(by_lot),
    )


def vins_in_window(
    conn: psycopg.Connection, station_id: str, start: datetime, end: datetime
) -> list[str]:
    """Vehicles that entered ``station_id`` in ``[start, end)``: a window containment."""
    return [
        r[0]
        for r in queries("window").vins_in_window(conn, station_id=station_id, start=start, end=end)
    ]


def vins_by_lot(conn: psycopg.Connection, station_id: str, lot_id: str) -> list[str]:
    """Vehicles that received ``lot_id`` at ``station_id``: the shape of a lot containment."""
    return [r[0] for r in queries("window").vins_by_lot(conn, station_id=station_id, lot_id=lot_id)]
