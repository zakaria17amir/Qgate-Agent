"""``qgate-gen``: replay a scenario onto Kafka, or inspect its ground truth."""

import json
import time
from pathlib import Path

import psycopg
import typer

from qgate_core import kafka
from qgate_core.settings import Settings
from qgate_generator.export import export as write_manifest
from qgate_generator.export import stamp_ms
from qgate_generator.line import Line
from qgate_generator.load import copy_run, truncate_facts
from qgate_generator.scenario import Scenario
from qgate_generator.seed import seed_dims
from qgate_generator.stream import Run, generate

app = typer.Typer(add_completion=False)
SCENARIOS = typer.Option(Path("scenarios"), help="Directory holding line.yaml and scenario files")


@app.callback()
def main() -> None:
    """Synthetic line generator."""


def load_run(scenario: str, scenarios_dir: Path, vehicles: int | None = None) -> Run:
    line = Line.load(scenarios_dir / "line.yaml")
    s = Scenario.load(scenarios_dir / f"{scenario}.yaml", line)
    if vehicles is not None:
        s = s.model_copy(update={"vehicles": vehicles})
    return generate(line, s)


@app.command()
def replay(
    scenario: str = typer.Option(..., help="Scenario id, e.g. tool_wear"),
    speed: float = typer.Option(10.0, help="Replay speed multiplier; 0 = as fast as possible"),
    vehicles: int | None = typer.Option(None, help="Override the scenario's vehicle count"),
    scenarios_dir: Path = SCENARIOS,
) -> None:
    """Produce the scenario's events to Kafka in takt order."""
    run = load_run(scenario, scenarios_dir, vehicles)
    settings = Settings()
    kafka.ensure_topics(settings)
    p = kafka.producer(settings)
    t0 = time.monotonic()
    first = stamp_ms(run.events[0])
    for e in run.events:
        if speed > 0:  # sleep until this event's simulated time, compressed by `speed`
            due = (stamp_ms(e) - first) / 1000 / speed
            if (wait := due - (time.monotonic() - t0)) > 0:
                time.sleep(wait)
        kafka.produce(settings, p, e)
    p.flush(30)
    typer.echo(f"{len(run.events)} events from {scenario} produced")


@app.command()
def export(
    scenario: str = typer.Option(..., help="Scenario id, e.g. tool_wear"),
    out: Path = typer.Option(..., help="Manifest path, e.g. /data/tool_wear.jsonl"),
    vehicles: int | None = typer.Option(None),
    scenarios_dir: Path = SCENARIOS,
) -> None:
    """Write the scenario's events as the JSONL manifest the C++ line-sim replays (ADR-011)."""
    n = write_manifest(load_run(scenario, scenarios_dir, vehicles), out)
    typer.echo(f"{n} events from {scenario} written to {out}")


@app.command()
def truth(scenario: str = typer.Option(...), scenarios_dir: Path = SCENARIOS) -> None:
    """Print the scenario's ground truth as JSON (what is *actually* defective)."""
    t = load_run(scenario, scenarios_dir).truth
    typer.echo(
        json.dumps(
            {
                "defective_vins": sorted(t.defective_vins),
                "by_inject": {i: sorted(v) for i, v in t.by_inject.items()},
                "bench_fault": t.bench_fault,
            },
            indent=1,
        )
    )


@app.command()
def load(
    scenario: str = typer.Option(..., help="Scenario id, e.g. tool_wear"),
    seed: int | None = typer.Option(None, help="Override the scenario's seed"),
    vehicles: int | None = typer.Option(None),
    database_url: str = typer.Option(..., envvar="DATABASE_URL"),
    truncate: bool = typer.Option(True, help="Empty the fact tables first"),
    scenarios_dir: Path = SCENARIOS,
) -> None:
    """COPY a scenario straight into Postgres (no Kafka). For demos and tests."""
    line = Line.load(scenarios_dir / "line.yaml")
    s = Scenario.load(scenarios_dir / f"{scenario}.yaml", line)
    updates = {k: v for k, v in {"seed": seed, "vehicles": vehicles}.items() if v is not None}
    run = generate(line, s.model_copy(update=updates))
    with psycopg.connect(database_url) as conn:
        if truncate:
            truncate_facts(conn)
        copy_run(conn, run)
    typer.echo(f"{len(run.events)} events loaded")


@app.command(name="seed-dims")
def seed_dims_cmd(
    database_url: str = typer.Option(..., envvar="DATABASE_URL", help="ingest_rw or migrate URL"),
    scenarios_dir: Path = SCENARIOS,
) -> None:
    """Insert stations, characteristics, shifts and benches from line.yaml (idempotent)."""
    with psycopg.connect(database_url) as conn:
        seed_dims(conn, Line.load(scenarios_dir / "line.yaml"))
    typer.echo("dims seeded")
