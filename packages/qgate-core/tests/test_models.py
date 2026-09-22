import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from qgate_core import models
from qgate_core.models import TOPIC, Measurement, QualityAlert, key_of

pytestmark = pytest.mark.unit
SCHEMAS = Path(__file__).parents[3] / "schemas"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("model", list(TOPIC))
def test_model_fields_match_avro_schema(model: type[BaseModel]) -> None:
    avsc = json.loads((SCHEMAS / f"{TOPIC[model]}.v1.avsc").read_text())
    assert set(model.model_fields) == {f["name"] for f in avsc["fields"]}


def test_line_records_are_keyed_by_vin() -> None:
    m = Measurement(
        vin="SYN00000000000001",
        station_id="ST-22",
        characteristic_id="CH-22-TORQUE",
        bench_id="INLINE",
        measured_at=NOW,
        value=45.1,
        unit="Nm",
        nominal=45.0,
        lower_limit=41.0,
        upper_limit=49.0,
    )
    assert key_of(m) == "SYN00000000000001"


def test_alerts_are_keyed_by_station() -> None:
    a = QualityAlert(
        alert_id="a1",
        station_id="ST-22",
        kind=models.AlertKind.DRIFT,
        severity=models.Severity.HIGH,
        detected_at=NOW,
        method="pelt",
    )
    assert key_of(a) == "ST-22"
    assert a.evidence == {} and a.estimated_onset is None


def test_containment_state_enum_matches_avro_and_the_table() -> None:
    """Every state the api can write must be announceable: the enum, the Avro symbols and the
    table's check constraint name the same set (COMMIT_PENDING was missing from two of three)."""
    from qgate_core.avro import load_schema
    from qgate_core.models import State

    field = next(f for f in load_schema("quality.containment")["fields"] if f["name"] == "state")
    assert set(field["type"]["symbols"]) == {s.value for s in State}
    assert "COMMIT_PENDING" in {s.value for s in State}
