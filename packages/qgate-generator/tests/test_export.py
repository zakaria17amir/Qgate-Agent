"""``qgate-gen export``: the manifest the C++ line-sim replays (ADR-011)."""

import json
from pathlib import Path

import pytest

from qgate_core.avro import from_avro, load_schema
from qgate_core.models import TOPIC, BuildEvent, EolResult, Measurement, key_of
from qgate_generator.export import export
from qgate_generator.line import Line
from qgate_generator.scenario import Scenario
from qgate_generator.stream import generate

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[3]
MODEL = {TOPIC[m]: m for m in (BuildEvent, Measurement, EolResult)}


def test_manifest_round_trips_every_event_in_takt_order(tmp_path: Path) -> None:
    line = Line.load(ROOT / "scenarios" / "line.yaml")
    run = generate(
        line,
        Scenario.load(ROOT / "scenarios" / "clean_baseline.yaml", line).model_copy(
            update={"vehicles": 5}
        ),
    )
    out = tmp_path / "clean.jsonl"
    n = export(run, out)
    lines = out.read_text(encoding="utf8").splitlines()
    assert n == len(lines) == len(run.events)

    stamps = []
    for raw, event in zip(lines, run.events, strict=True):
        row = json.loads(raw)
        assert row["topic"] == TOPIC[type(event)] and row["key"] == key_of(event)
        decoded = from_avro(
            bytes.fromhex(row["avro_hex"]), load_schema(row["topic"]), MODEL[row["topic"]]
        )
        assert decoded == event
        stamps.append(row["ts_ms"])
    assert stamps == sorted(stamps)
    assert out.read_bytes().endswith(b"\n") and b"\r" not in out.read_bytes()
