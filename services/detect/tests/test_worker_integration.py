"""The worker turns a 4-sigma measurement into one RULE_VIOLATION alert keyed by station.

One VIN for every message so all land on one partition and arrive in time order; the worker
also handles interleaving, but this test is about the rule, not the ordering.
"""

from datetime import UTC, datetime, timedelta

import pytest

from qgate_core import kafka
from qgate_core.models import AlertKind, Measurement, QualityAlert
from qgate_core.settings import Settings
from qgate_detect.worker import run

pytestmark = pytest.mark.integration


def measurement(i: int, value: float) -> Measurement:
    return Measurement(
        vin="W00001",
        station_id="ST-08",
        characteristic_id="CH-08-TORQUE",
        bench_id="INLINE",
        measured_at=datetime(2026, 1, 5, 6, tzinfo=UTC) + timedelta(minutes=i),
        value=value,
        unit="Nm",
        nominal=12.0,
        lower_limit=10.5,
        upper_limit=13.5,
    )


def test_out_of_control_point_raises_one_alert(kafka_settings: Settings) -> None:
    kafka.ensure_topics(kafka_settings)
    p = kafka.producer(kafka_settings)
    for i in range(40):  # in control: within +-0.1 Nm of nominal
        kafka.produce(kafka_settings, p, measurement(i, 12.0 + 0.1 * (-1) ** i))
    kafka.produce(kafka_settings, p, measurement(40, 13.4))  # far beyond 3 sigma of the above
    p.flush(10)

    run(kafka_settings, group="detect-worker-test", idle_timeout=5)

    c = kafka.consumer(kafka_settings, "alert-reader", ["quality.alerts"])
    msg = kafka.poll(c, timeout=20)
    assert msg is not None and msg.key() == b"ST-08"
    alert = kafka.decode(kafka_settings, msg, QualityAlert)
    assert alert.kind is AlertKind.RULE_VIOLATION and alert.characteristic_id == "CH-08-TORQUE"
    assert alert.evidence["rule"] == 1.0
