import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from qgate_eval.cli import _gate, app

pytestmark = pytest.mark.unit
METRICS = {"escapes": 3, "latency_non_llm_p95_ms": 1000}


def test_run_with_no_goldens_exits_zero(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", "--mode", "replay", "--goldens", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0 golden cases" in result.output


def test_gate_is_inactive_until_a_baseline_is_recorded(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"escapes": null}')
    _gate(METRICS, baseline)  # does not raise


def test_gate_fails_when_escapes_rise_or_non_llm_latency_regresses(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"escapes": 2, "latency_non_llm_p95_ms": 1000}))
    with pytest.raises(typer.Exit):
        _gate(METRICS, baseline)
    baseline.write_text(json.dumps({"escapes": 3, "latency_non_llm_p95_ms": 700}))
    with pytest.raises(typer.Exit):
        _gate(METRICS, baseline)


def test_gate_passes_when_within_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"escapes": 3, "latency_non_llm_p95_ms": 900}))
    _gate(METRICS, baseline)
