"""Streaming SPC: consume ``line.measurements``, emit ``quality.alerts`` on rule violations.

One window per (station, characteristic), kept in *measurement* order: topics are keyed by VIN
(ADR-002), so one characteristic's readings arrive interleaved across partitions. Deviations are
standardised against the window's own history, so a characteristic that has always been noisy
is not an alert. Onset estimation is deliberately *not* done here — the agent asks ``/drift``
for that with a window (ADR-009).
"""

import bisect
import logging
import threading
import uuid
from collections import defaultdict
from datetime import datetime

import numpy as np

from qgate_core import kafka, otel
from qgate_core.health import health_app, ok, serve
from qgate_core.logs import configure_logging
from qgate_core.models import AlertKind, Measurement, QualityAlert, Severity
from qgate_core.settings import Settings
from qgate_detect.spc import western_electric

log = logging.getLogger("detect-worker")
WINDOW = 500  # points kept per characteristic
WARMUP = 20  # points needed before standardising means anything
app = health_app("detect-worker", lambda: {"kafka": ok(lambda: kafka.reachable(Settings()))})


class Charts:
    """Per-characteristic windows in time order; returns the alert a new point triggers, if any."""

    def __init__(self) -> None:
        self.series: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)

    def observe(self, m: Measurement) -> QualityAlert | None:
        if m.repeat_no != 1:
            return None
        buf = self.series[(m.station_id, m.characteristic_id)]
        dev = (m.value - m.nominal) / ((m.upper_limit - m.lower_limit) / 2)
        bisect.insort(buf, (m.measured_at, dev))
        if len(buf) > WINDOW:
            del buf[0]
        if len(buf) < WARMUP:
            return None
        pos = buf.index((m.measured_at, dev))
        values = np.array([d for _, d in buf])
        history = np.delete(values, pos)
        sigma = float(np.std(history)) or 1e-9
        z = (values - float(np.mean(history))) / sigma
        # only violations that complete on the point that just arrived are new information
        fresh = [v for v in western_electric(z[: pos + 1]) if v.index == pos]
        if not fresh:
            return None
        rule = min(v.rule for v in fresh)
        return QualityAlert(
            alert_id=str(uuid.uuid4()),
            station_id=m.station_id,
            characteristic_id=m.characteristic_id,
            bench_id=m.bench_id,
            kind=AlertKind.RULE_VIOLATION,
            severity=Severity.HIGH if rule == 1 else Severity.MEDIUM,
            detected_at=m.measured_at,
            method=f"we_rule_{rule}",
            evidence={"rule": float(rule), "z": round(float(z[-1]), 3), "n": float(len(buf))},
        )


def run(
    settings: Settings, group: str = "detect-worker", idle_timeout: float | None = None
) -> None:
    kafka.ensure_topics(settings)
    consumer = kafka.consumer(settings, group, ["line.measurements"])
    producer = kafka.producer(settings)
    charts = Charts()
    while True:
        msg = kafka.poll(consumer, timeout=idle_timeout or 1.0)
        if msg is None:
            if idle_timeout is not None:
                break
            continue
        try:
            alert = charts.observe(kafka.decode(settings, msg, Measurement))
        except Exception as e:  # a bad measurement is ingest's DLQ problem, not a chart's
            log.warning("skip %s@%s: %s", msg.topic(), msg.offset(), e)
            alert = None
        if alert is not None:
            kafka.produce(settings, producer, alert)
        consumer.commit(message=msg)
    producer.flush(10)
    consumer.close()


def main() -> None:
    configure_logging()
    otel.configure("detect-worker")
    threading.Thread(target=serve, args=(app,), daemon=True).start()
    run(Settings())
