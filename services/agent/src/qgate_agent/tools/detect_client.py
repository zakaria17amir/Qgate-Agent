"""Tools backed by the detect service over HTTP; any ``httpx.Client`` works (TestClient too)."""

from datetime import datetime
from typing import Any, Protocol

from qgate_agent.tools.models import BenchResult, DriftResult


class HttpGetter(Protocol):
    """The slice of ``httpx.Client`` we use; Starlette's TestClient satisfies it too."""

    def get(self, url: str, *, params: dict[str, str]) -> Any: ...


def check_station_drift(
    client: HttpGetter, station_id: str, characteristic_id: str, start: datetime, end: datetime
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
    client: HttpGetter, bench_id: str, characteristic_id: str, start: datetime, end: datetime
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
