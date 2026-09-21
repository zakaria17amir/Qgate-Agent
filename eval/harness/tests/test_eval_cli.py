from pathlib import Path

import pytest
from typer.testing import CliRunner

from qgate_eval.cli import app

pytestmark = pytest.mark.unit


def test_run_with_no_goldens_exits_zero(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", "--mode", "replay", "--goldens", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0 golden cases" in result.output


def test_gate_is_inactive_until_a_baseline_is_recorded(tmp_path: Path) -> None:
    goldens = tmp_path / "goldens"
    goldens.mkdir()
    (goldens / "x.yaml").write_text("id: x\n")
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"escapes": null}')
    result = CliRunner().invoke(
        app, ["run", "--mode", "replay", "--goldens", str(goldens), "--baseline", str(baseline)]
    )
    assert result.exit_code == 0, result.output
    assert "inactive" in result.output


def test_runner_is_required_once_a_baseline_exists(tmp_path: Path) -> None:
    goldens = tmp_path / "goldens"
    goldens.mkdir()
    (goldens / "x.yaml").write_text("id: x\n")
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"escapes": 0}')
    result = CliRunner().invoke(
        app, ["run", "--mode", "replay", "--goldens", str(goldens), "--baseline", str(baseline)]
    )
    assert result.exit_code == 2
