"""The simulated line: stations, measured characteristics, shifts and EOL benches.

Loaded from ``scenarios/line.yaml``, which is the single source of truth for every id
the rest of the system references.
"""

from datetime import time
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, model_validator


class Characteristic(BaseModel):
    """One measured feature with its nominal and tolerance limits."""

    id: str
    station_id: str = ""  # filled from the owning station on load
    name: str
    unit: str
    nominal: float
    lower_limit: float
    upper_limit: float

    @property
    def half_tolerance(self) -> float:
        return (self.upper_limit - self.lower_limit) / 2


class Station(BaseModel):
    id: str
    name: str
    sequence_pos: int
    fits_lot: bool = False
    characteristics: list[Characteristic]

    @model_validator(mode="after")
    def _stamp_station_id(self) -> Self:
        for c in self.characteristics:
            c.station_id = self.id
        return self


class Shift(BaseModel):
    id: str
    label: str
    starts_at: time
    ends_at: time
    crew: str

    def covers(self, hour: int) -> bool:
        """True if ``hour`` falls in this shift; night shifts wrap past midnight."""
        start, end = self.starts_at.hour, self.ends_at.hour
        return start <= hour < end if start < end else hour >= start or hour < end


class Bench(BaseModel):
    """An EOL measurement system with its own repeatability and bias (metrology)."""

    id: str
    station_id: str
    repeatability_sigma: float
    bias: float


class Line(BaseModel):
    takt_s: int
    shifts: list[Shift]
    eol_benches: list[Bench]
    stations: list[Station]

    @classmethod
    def load(cls, path: Path) -> Self:
        with path.open(encoding="utf8") as f:
            return cls.model_validate(yaml.safe_load(f))

    @property
    def eol_station(self) -> Station:
        return max(self.stations, key=lambda s: s.sequence_pos)

    def characteristic(self, characteristic_id: str) -> Characteristic:
        for s in self.stations:
            for c in s.characteristics:
                if c.id == characteristic_id:
                    return c
        raise KeyError(characteristic_id)

    def station(self, station_id: str) -> Station:
        for s in self.stations:
            if s.id == station_id:
                return s
        raise KeyError(station_id)

    def shift_at_hour(self, hour: int) -> Shift:
        return next(s for s in self.shifts if s.covers(hour))
