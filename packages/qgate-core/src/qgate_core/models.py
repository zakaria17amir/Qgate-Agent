"""Pydantic mirrors of the Avro records in ``schemas/``.

Field names match the ``.avsc`` files one-to-one (a unit test enforces it), so a record can
be serialised with ``model_dump()`` and deserialised with ``model_validate()`` unchanged.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Result(StrEnum):
    PASS = "PASS"  # noqa: S105 — test verdict, not a secret
    FAIL = "FAIL"


class AlertKind(StrEnum):
    DRIFT = "DRIFT"
    STEP = "STEP"
    RULE_VIOLATION = "RULE_VIOLATION"
    BENCH_INCAPABLE = "BENCH_INCAPABLE"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class State(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    AMENDED = "AMENDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    COMMIT_PENDING = "COMMIT_PENDING"  # approved; plant system unavailable, retrying
    COMMITTED = "COMMITTED"
    ESCALATED = "ESCALATED"


class BuildEvent(BaseModel):
    vin: str
    station_id: str
    sequence_no: int
    entered_at: datetime
    shift_id: str
    operator_id: str
    parts_lots: list[str] = Field(default_factory=list)


class Measurement(BaseModel):
    vin: str
    station_id: str
    characteristic_id: str
    bench_id: str
    measured_at: datetime
    value: float
    unit: str
    nominal: float
    lower_limit: float
    upper_limit: float
    repeat_no: int = 1  # >1 marks gauge repeat measurements used for %GRR


class EolResult(BaseModel):
    vin: str
    tested_at: datetime
    bench_id: str
    result: Result
    fault_codes: list[str] = Field(default_factory=list)


class QualityAlert(BaseModel):
    alert_id: str
    station_id: str
    characteristic_id: str | None = None
    bench_id: str | None = None
    kind: AlertKind
    severity: Severity
    detected_at: datetime
    estimated_onset: datetime | None = None
    method: str
    evidence: dict[str, float] = Field(default_factory=dict)


class ContainmentEvent(BaseModel):
    containment_id: str
    thread_id: str
    state: State
    occurred_at: datetime
    actor: str
    station_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    lot_ids: list[str] = Field(default_factory=list)
    vin_count: int
    mes_ref: str | None = None


LineRecord = BuildEvent | Measurement | EolResult
Record = LineRecord | QualityAlert | ContainmentEvent

TOPIC: dict[type[BaseModel], str] = {
    BuildEvent: "line.build.events",
    Measurement: "line.measurements",
    EolResult: "line.eol.results",
    QualityAlert: "quality.alerts",
    ContainmentEvent: "quality.containment",
}


def key_of(record: Record) -> str:
    """Partition key per ADR-002: VIN for vehicle facts, station for alerts, id for decisions."""
    match record:
        case BuildEvent() | Measurement() | EolResult():
            return record.vin
        case QualityAlert():
            return record.station_id
        case ContainmentEvent():
            return record.containment_id
