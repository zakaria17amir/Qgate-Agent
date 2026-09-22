"""Run the fifty goldens against the live model and write the report (design §14).

The stack runs in-process (the same harness CI uses in replay mode) over ``eval-db`` — a
dedicated Postgres in the ``eval`` profile — so the run can never truncate the demo's tables.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg
from prefect import flow, task
from prefect.artifacts import create_markdown_artifact

ROOT = Path(__file__).parents[2]


def require_eval_db(url: str) -> str:
    """Refuse any database that is not the dedicated ``eval-db`` (Review Focus 3): the harness
    truncates fact tables, and the core stack's data must survive a nightly."""
    if urlparse(url).hostname != "eval-db":
        raise ValueError(f"nightly_eval only runs against eval-db, not {urlparse(url).hostname}")
    return url


@task(retries=3, retry_delay_seconds=10)
def prepare_eval_db(url: str) -> str:
    from qgate_core.migrate import apply_migrations
    from qgate_generator.line import Line
    from qgate_generator.seed import seed_dims

    with psycopg.connect(url) as conn:
        apply_migrations(conn, role_password=os.environ.get("POSTGRES_PASSWORD", "eval"))
        seed_dims(conn, Line.load(ROOT / "scenarios" / "line.yaml"))
    return url


@task(task_run_name="case-{golden_id}")
def run_case(golden_id: str, stack: Any, golden: Any) -> Any:
    from qgate_eval.runner import run_golden
    from qgate_eval.scoring import score

    return score(run_golden(stack, golden))


@task
def write_outputs(scores: list[Any], mode: str, model_name: str, out_dir: Path) -> dict[str, Any]:
    from qgate_eval.cli import _markdown  # the same renderer the CLI uses
    from qgate_eval.scoring import summarise

    metrics = summarise(scores)
    metrics["mode"], metrics["model"] = mode, model_name
    metrics["recorded_at"] = datetime.now(UTC).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n", encoding="utf8")
    (out_dir / "report.md").write_text(_markdown(metrics), encoding="utf8", newline="\n")
    create_markdown_artifact(key="nightly-eval", markdown=_markdown(metrics))
    return metrics


@flow(name="nightly-eval")
def nightly_eval(
    mode: str = "live",
    database_url: str = os.environ.get(
        "EVAL_DATABASE_URL", "postgresql://qgate_migrate:change-me@eval-db:5432/qgate"
    ),
    goldens: Path = ROOT / "eval" / "goldens",
    cassettes: Path = ROOT / "eval" / "cassettes",
    out_dir: Path = ROOT / "eval",
) -> dict[str, Any]:
    """Every golden through the in-process stack; ``eval/metrics.json`` and ``eval/report.md``."""
    from qgate_eval.cli import _model
    from qgate_eval.golden import load_all
    from qgate_eval.stack import Stack

    url = prepare_eval_db(require_eval_db(database_url))
    model = _model(mode)
    stack = Stack(url, model, mode, cassettes)  # type: ignore[arg-type]  # mode validated by _model
    try:
        scores = [run_case(g.id, stack, g) for g in load_all(goldens)]
    finally:
        stack.close()
    return write_outputs(scores, mode, model.name, out_dir)
