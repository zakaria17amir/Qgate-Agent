"""Replay one scenario onto the running stack and prove it landed (design §14).

Drives the same two images ``make demo`` uses through the Docker socket the worker mounts:
``gen`` exports the manifest, ``line-sim`` produces it at takt, then we wait for ingest to
catch up and compare Postgres counts with the manifest.
"""

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import docker
import psycopg
from prefect import flow, task
from prefect.artifacts import create_markdown_artifact

OWNER = os.environ.get("IMAGE_OWNER", "zakaria17amir")
NETWORK = os.environ.get("COMPOSE_NETWORK", "qgate_default")
DATA_VOLUME = os.environ.get("SIM_DATA_VOLUME", "qgate_sim-data")
REPO = Path(
    os.environ.get("REPO_ON_HOST", str(Path(__file__).parents[2]))
)  # bind mounts need host paths


def _run(image: str, command: list[str], volumes: dict[str, dict[str, str]]) -> str:
    client = docker.from_env()  # type: ignore[attr-defined]  # docker-py ships no stubs
    out = client.containers.run(
        image, command, network=NETWORK, volumes=volumes, remove=True, stderr=True, user="10001"
    )
    return str(out.decode() if isinstance(out, bytes) else out)


@task(retries=3, retry_delay_seconds=5)
def export_manifest(scenario: str) -> str:
    return _run(
        f"ghcr.io/{OWNER}/qgate-gen:dev",
        ["export", "--scenario", scenario, "--out", f"/data/{scenario}.jsonl"],
        {
            str(REPO / "scenarios"): {"bind": "/scenarios", "mode": "ro"},
            str(REPO / "schemas"): {"bind": "/schemas", "mode": "ro"},
            DATA_VOLUME: {"bind": "/data", "mode": "rw"},
        },
    )


@task
def run_line_sim(scenario: str, speed: float) -> str:
    args = [
        "--file",
        f"/data/{scenario}.jsonl",
        "--brokers",
        "redpanda:9092",
        "--registry",
        "http://redpanda:8081",
        "--schemas",
        "/schemas",
        "--speed",
        str(speed),
    ]
    return _run(
        f"ghcr.io/{OWNER}/qgate-line-sim:dev",
        args,
        {
            str(REPO / "schemas"): {"bind": "/schemas", "mode": "ro"},
            DATA_VOLUME: {"bind": "/data", "mode": "ro"},
        },
    )


@task(retries=180, retry_delay_seconds=5)
def wait_for_lag_zero(group: str = "ingest") -> None:
    """Exact lag from the broker (not the scraped metric: that lags the replay by a scrape)."""
    from qgate_core import kafka
    from qgate_core.settings import Settings

    lag = kafka.group_lag(
        Settings(), group, ["line.build.events", "line.measurements", "line.eol.results"]
    )
    if lag > 0:
        raise RuntimeError(f"{group} lag {lag}")


@task
def assert_counts(
    scenario: str, database_url: str, manifest_dir: Path = Path("/data")
) -> dict[str, Any]:
    expected = Counter(
        json.loads(line)["topic"]
        for line in (manifest_dir / f"{scenario}.jsonl").open(encoding="utf8")
    )
    tables = {
        "line.build.events": "fact_build_event",
        "line.measurements": "fact_measurement",
        "line.eol.results": "fact_eol_result",
    }
    with psycopg.connect(database_url) as conn:
        got = {
            topic: int((conn.execute(f"select count(*) from qgate.{table}").fetchone() or [0])[0])  # noqa: S608 — fixed names
            for topic, table in tables.items()
        }
    rows = "\n".join(
        f"| {t} | {expected[t]} | {got[t]} | {'ok' if got[t] >= expected[t] else 'MISSING'} |"
        for t in expected
    )
    create_markdown_artifact(
        key=f"replay-{scenario.replace('_', '-')}",
        markdown=f"| topic | manifest | postgres | |\n|---|---|---|---|\n{rows}\n",
    )
    missing = {t: expected[t] - got[t] for t in expected if got[t] < expected[t]}
    if missing:
        raise RuntimeError(f"rows missing after replay: {missing}")
    return {"expected": dict(expected), "got": got}


@flow(name="replay-scenario")
def replay_scenario(
    scenario: str = "clean_baseline",
    speed: float = 0,
    database_url: str = os.environ.get("DATABASE_URL", ""),
) -> dict[str, Any]:
    """gen export -> line-sim -> ingest lag 0 -> counts match. The documented way to run a line."""
    export_manifest(scenario)
    run_line_sim(scenario, speed)
    wait_for_lag_zero()
    time.sleep(2)  # ingest commits per message; the last ones land a beat after lag reads 0
    return assert_counts(scenario, database_url)
