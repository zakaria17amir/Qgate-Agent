"""The agent's tools. Every one is read-only; the database role enforces it.

Plain typed functions in Phase 2; Phase 3 wraps them as LangGraph tools without changing them.
"""

from qgate_agent.tools.detect_client import check_bench, check_station_drift
from qgate_agent.tools.sql import (
    find_correlated_failures,
    get_station_spec,
    get_vehicle_genealogy,
    vins_by_lot,
    vins_in_window,
)

__all__ = [
    "check_bench",
    "check_station_drift",
    "find_correlated_failures",
    "get_station_spec",
    "get_vehicle_genealogy",
    "vins_by_lot",
    "vins_in_window",
]
