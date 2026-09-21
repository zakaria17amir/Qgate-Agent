"""``qgate-gen``: replay a scenario onto Kafka, or inspect its ground truth."""

import json
import time
from pathlib import Path

import typer

from qgate_core import kafka
from qgate_core.models import BuildEvent, LineRecord, Measurement
from qgate_core.settings import Settings
from qgate_generator.line import Line
from qgate_generator.scenario import Scenario
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
    first = _stamp(run.events[0])
    for e in run.events:
        if speed > 0:  # sleep until this event's simulated time, compressed by `speed`
            due = (_stamp(e) - first) / speed
            if (wait := due - (time.monotonic() - t0)) > 0:
                time.sleep(wait)
        kafka.produce(settings, p, e)
    p.flush(30)
    typer.echo(f"{len(run.events)} events from {scenario} produced")


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


def _stamp(e: LineRecord) -> float:
    if isinstance(e, BuildEvent):
        return e.entered_at.timestamp()
    if isinstance(e, Measurement):
        return e.measured_at.timestamp()
    return e.tested_at.timestamp()
