from pathlib import Path

import pytest
from typer.testing import CliRunner

from qgate_eval.cli import app

pytestmark = pytest.mark.unit


def test_run_with_no_goldens_exits_zero(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["run", "--mode", "replay", "--goldens", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "0 golden cases" in result.output
