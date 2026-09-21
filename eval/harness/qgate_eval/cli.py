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
    # Runner, scorers and the baseline gate land in Phase 3 (checklist §3.4).
    if not cases:
        return
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
