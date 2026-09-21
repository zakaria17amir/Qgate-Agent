"""The hand-authored fault map must only name ids that exist on the line."""

from pathlib import Path

import pytest
import yaml

from qgate_generator.line import Line

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[3]
LINE = Line.load(ROOT / "scenarios" / "line.yaml")
FAULT_MAP = yaml.safe_load((ROOT / "knowledge" / "fault_map.yaml").read_text(encoding="utf8"))


def test_every_station_has_a_fault_code() -> None:
    assert set(FAULT_MAP["faults"]) == {f"F-{s.id[-2:]}" for s in LINE.stations}


def test_candidates_reference_real_ids_and_own_station_first() -> None:
    stations = {s.id for s in LINE.stations}
    chars = {c.id for s in LINE.stations for c in s.characteristics}
    for code, fault in FAULT_MAP["faults"].items():
        cands = fault["candidates"]
        assert cands[0]["station_id"] == f"ST-{code[-2:]}", code
        assert abs(sum(c["prior"] for c in cands) - 1.0) < 1e-9, code
        for c in cands:
            assert c["station_id"] in stations, (code, c["station_id"])
            assert set(c["characteristic_ids"]) <= chars, (code, c["characteristic_ids"])
            assert c["rationale"]


def test_eol_codes_are_bench_sensitive() -> None:
    eol = f"F-{LINE.eol_station.id[-2:]}"
    assert FAULT_MAP["faults"][eol]["bench_sensitive"] is True
    assert all(not f.get("bench_sensitive") for k, f in FAULT_MAP["faults"].items() if k != eol)
