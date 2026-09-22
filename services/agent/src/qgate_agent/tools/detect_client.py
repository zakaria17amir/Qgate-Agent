"""Tools backed by the detect service over HTTP; any ``httpx.Client`` works (TestClient too)."""

from datetime import datetime

import httpx

from qgate_agent.tools.models import BenchResult, DriftResult


def check_station_drift(
    client: httpx.Client, station_id: str, characteristic_id: str, start: datetime, end: datetime
) -> DriftResult:
    """Was this characteristic drifting or stepping in the window, and since when?"""
    r = client.get(
        "/drift",
        params={
            "station_id": station_id,
            "characteristic_id": characteristic_id,
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
    )
    r.raise_for_status()
    return DriftResult.model_validate(r.json())


def check_bench(
    client: httpx.Client, bench_id: str, characteristic_id: str, start: datetime, end: datetime
) -> BenchResult:
    """Can this bench's readings of the characteristic be trusted in the window?"""
    r = client.get(
        f"/bench/{bench_id}/capability",
        params={
            "characteristic_id": characteristic_id,
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
    )
    r.raise_for_status()
    return BenchResult.model_validate(r.json())
