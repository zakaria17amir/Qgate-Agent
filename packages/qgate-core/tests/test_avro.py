from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from qgate_core.avro import from_avro, load_schema, to_avro
from qgate_core.models import (
    TOPIC,
    BuildEvent,
    EolResult,
    Measurement,
    QualityAlert,
    Result,
    Severity,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)

SAMPLES: list[BaseModel] = [
    BuildEvent(
        vin="SYN1",
        station_id="ST-01",
        sequence_no=7,
        entered_at=NOW,
        shift_id="S1",
        operator_id="OP-01-A",
        parts_lots=["L-01-0001"],
    ),
    Measurement(
        vin="SYN1",
        station_id="ST-01",
        characteristic_id="CH-01-WELD",
        bench_id="INLINE",
        measured_at=NOW,
        value=9.51,
        unit="kA",
        nominal=9.5,
        lower_limit=8.9,
        upper_limit=10.1,
    ),
    EolResult(
        vin="SYN1", tested_at=NOW, bench_id="EOL-B1", result=Result.FAIL, fault_codes=["F-19"]
    ),
    QualityAlert(
        alert_id="a",
        station_id="ST-19",
        kind="DRIFT",
        severity=Severity.HIGH,
        detected_at=NOW,
        estimated_onset=NOW,
        method="pelt",
        evidence={"k": 1.0},
    ),
]


@pytest.mark.parametrize("record", SAMPLES, ids=lambda r: type(r).__name__)
def test_round_trip_through_avro_bytes(record: BaseModel) -> None:
    schema = load_schema(TOPIC[type(record)])
    assert from_avro(to_avro(record, schema), schema, type(record)) == record


def test_avro_timestamps_are_millisecond_utc() -> None:
    schema = load_schema("line.eol.results")
    raw = to_avro(EolResult(vin="v", tested_at=NOW, bench_id="b", result=Result.PASS), schema)
    back = from_avro(raw, schema, EolResult)
    assert back.tested_at.tzinfo is not None and back.tested_at == NOW
