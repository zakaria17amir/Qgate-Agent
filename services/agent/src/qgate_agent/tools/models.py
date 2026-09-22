"""Result types the tools return. Plain data; the graph reasons over these, never over rows."""

from datetime import datetime

from pydantic import BaseModel, Field


class MeasurementRow(BaseModel):
    characteristic_id: str
    bench_id: str
    value: float
    deviation: float
    out_of_tolerance: bool
    repeat_no: int


class StationVisit(BaseModel):
    station_id: str
    entered_at: datetime
    shift_id: str
    operator_id: str
    parts_lots: list[str]
    measurements: list[MeasurementRow]


class EolSummary(BaseModel):
    tested_at: datetime
    bench_id: str
    result: str
    fault_codes: list[str]


class Genealogy(BaseModel):
    vin: str
    visits: list[StationVisit]  # in build order
    eol: EolSummary | None

    def visit(self, station_id: str) -> StationVisit:
        return next(v for v in self.visits if v.station_id == station_id)

    def lots_at(self, station_id: str) -> list[str]:
        return self.visit(station_id).parts_lots

    def out_of_tolerance_stations(self) -> list[str]:
        return [
            v.station_id for v in self.visits if any(m.out_of_tolerance for m in v.measurements)
        ]


class CharacteristicSpec(BaseModel):
    characteristic_id: str
    name: str
    unit: str
    nominal: float
    lower_limit: float
    upper_limit: float


class StationSpec(BaseModel):
    station_id: str
    name: str
    sequence_pos: int
    takt_s: int
    fits_lot: bool
    characteristics: list[CharacteristicSpec]


class CorrelationResult(BaseModel):
    """Siblings of a failure: same code, passed the suspect station, inside the window."""

    fault_code: str
    station_id: str
    vins: list[str]
    entered_at: list[datetime] = Field(default_factory=list)  # when each sibling passed the station
    by_shift: dict[str, int] = Field(default_factory=dict)
    by_lot: dict[str, int] = Field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.vins)

    @property
    def top_lot(self) -> str | None:
        return max(self.by_lot, key=lambda k: self.by_lot[k]) if self.by_lot else None

    @property
    def top_lot_share(self) -> float:
        return self.by_lot[self.top_lot] / self.n if self.top_lot and self.n else 0.0

    def spread_takts(self, takt_s: int = 60) -> int:
        """Build-time span of the siblings in takts: consecutive vehicles share a lot block by
        construction, so lot evidence needs siblings spread wider than one block."""
        if len(self.entered_at) < 2:
            return 0
        return int((max(self.entered_at) - min(self.entered_at)).total_seconds() // takt_s)


class DriftResult(BaseModel):
    """Mirror of detect's ``/drift`` response."""

    verdict: str  # NONE | DRIFT | STEP
    onset: datetime | None
    changed_at: datetime | None
    severity: str
    confidence: float
    evidence: dict[str, float]


class BenchResult(BaseModel):
    """Mirror of detect's ``/bench/{id}/capability`` response."""

    bench_id: str
    capable: bool
    grr_pct: float | None
    bias_vs_peers: float | None
    n_repeats: int
    n_values: int
    method: str
