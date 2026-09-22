"""Write a run as the manifest the C++ ``line-sim`` replays (ADR-011).

One JSON line per event, in takt order: ``{"topic", "key", "ts_ms", "avro_hex"}``. The value is
the schema-less Avro body; the producer prepends the Confluent wire header once it knows the
registry's schema id. Hex rather than base64: six lines of C++ to decode, and still greppable.
"""

import json
from pathlib import Path

from qgate_core.avro import load_schema, to_avro
from qgate_core.models import TOPIC, BuildEvent, EolResult, LineRecord, Measurement, key_of
from qgate_generator.stream import Run


def stamp_ms(e: LineRecord) -> int:
    """The event's simulated time in epoch milliseconds — what the scheduler replays against."""
    t = (
        e.entered_at
        if isinstance(e, BuildEvent)
        else e.measured_at
        if isinstance(e, Measurement)
        else e.tested_at
    )
    return int(t.timestamp() * 1000)


def export(run: Run, out: Path) -> int:
    """Write ``run.events`` to ``out``; returns the number of lines."""
    schemas = {TOPIC[m]: load_schema(TOPIC[m]) for m in (BuildEvent, Measurement, EolResult)}
    with out.open("w", encoding="utf8", newline="\n") as f:
        for e in run.events:
            topic = TOPIC[type(e)]
            row = {
                "topic": topic,
                "key": key_of(e),
                "ts_ms": stamp_ms(e),
                "avro_hex": to_avro(e, schemas[topic]).hex(),
            }
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    return len(run.events)
