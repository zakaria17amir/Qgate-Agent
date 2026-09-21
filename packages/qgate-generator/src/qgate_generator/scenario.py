"""Defect scenarios as data.

A scenario is a seed, a vehicle count and a list of *injects* — deviations added to the line's
true values. Magnitudes are in units of the affected characteristic's half-tolerance, so a
scenario file reads the same for a torque in Nm and a gap in mm.
"""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, Field

from qgate_generator.line import Line

InjectKind = Literal["drift", "step", "lot", "noise", "bench_bias"]


class Inject(BaseModel):
    """One deviation applied to true (or, for ``bench_bias``, reported) values.

    * ``drift``: linear ramp from 0 at ``start_sequence`` to ``magnitude`` at ``end_sequence``.
    * ``step``: constant ``magnitude`` from ``start_sequence``.
    * ``lot``: constant ``magnitude`` for vehicles carrying ``lot_id`` at this station.
    * ``noise``: one shared N(0, magnitude) term per vehicle across all of the station's
      characteristics, between ``start_sequence`` and ``end_sequence``.
    * ``bench_bias``: ramp like ``drift`` but on the *reported* EOL value of ``bench_id`` only —
      the cars are fine, the gauge is not.
    """

    kind: InjectKind
    station_id: str
    characteristic_id: str | None = None  # None = every characteristic at the station
    bench_id: str | None = None
    lot_id: str | None = None
    start_sequence: int = 0
    end_sequence: int | None = None
    magnitude: float


class Scenario(BaseModel):
    id: str
    seed: int
    vehicles: int
    base_defect_rate: float = 0.004  # probability a vehicle has a random true OOT somewhere
    injects: list[Inject] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path, line: Line) -> Self:
        """Load and check that every referenced id exists on ``line``."""
        with path.open(encoding="utf8") as f:
            scenario = cls.model_validate(yaml.safe_load(f))
        stations = {s.id for s in line.stations}
        characteristics = {c.id for s in line.stations for c in s.characteristics}
        benches = {b.id for b in line.eol_benches}
        for i in scenario.injects:
            if i.station_id not in stations:
                raise ValueError(f"{path.name}: unknown station {i.station_id}")
            if i.characteristic_id is not None and i.characteristic_id not in characteristics:
                raise ValueError(f"{path.name}: unknown characteristic {i.characteristic_id}")
            if i.bench_id is not None and i.bench_id not in benches:
                raise ValueError(f"{path.name}: unknown bench {i.bench_id}")
        return scenario
