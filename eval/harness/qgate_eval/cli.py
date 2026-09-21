import json
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """Golden-case evaluation harness."""


@app.command()
def run(
    mode: str = typer.Option("replay", help="replay | live | record"),
    goldens: Path = typer.Option(Path("eval/goldens"), help="Directory of golden case YAMLs"),
    baseline: Path | None = typer.Option(None, help="Baseline JSON to compare against"),
    report: Path | None = typer.Option(None, help="Write a markdown report here"),
) -> None:
    cases = sorted(goldens.glob("*.yaml"))
    typer.echo(f"{len(cases)} golden cases in {goldens} (mode={mode})")
    if not cases:
        return
    # The CI gate compares against a recorded baseline. Until Phase 3 records one, there is
    # nothing to regress against, so the gate is honestly inactive rather than faked green.
    if baseline is not None and json.loads(baseline.read_text()).get("escapes") is None:
        typer.echo("no baseline recorded yet: gate inactive (runner lands in Phase 3)")
        return
    typer.echo("runner not implemented", err=True)
    raise typer.Exit(code=2)


@app.command()
def goldens(
    out: Path = typer.Option(Path("eval/goldens")),
    scenarios_dir: Path = typer.Option(Path("scenarios")),
) -> None:
    """(Re)author the fifty golden cases from generator ground truth. Deliberate, reviewed."""
    from qgate_eval.author import author

    written = author(scenarios_dir, out)
    typer.echo(f"{len(written)} goldens written to {out}")
