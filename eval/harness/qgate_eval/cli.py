"""``qgate-eval``: author goldens, run them, gate CI on the result."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False)
console = Console()
LATENCY_SLACK_MS = 500
ROOT = Path(
    os.environ.get("QGATE_ROOT", Path(__file__).parents[3])
)  # repo, or /workspace in an image


@app.callback()
def main() -> None:
    """Golden-case evaluation harness."""


@app.command()
def run(
    mode: str = typer.Option("replay", help="replay | live | record"),
    goldens: Path = typer.Option(Path("eval/goldens"), help="Directory of golden case YAMLs"),
    cassettes: Path = typer.Option(Path("eval/cassettes")),
    baseline: Path | None = typer.Option(None, help="Baseline JSON to compare against (CI gate)"),
    report: Path | None = typer.Option(None, help="Write a markdown report here"),
    metrics_out: Path | None = typer.Option(None, help="Write the metrics JSON here"),
    only: str | None = typer.Option(None, help="Run one golden id (debugging)"),
    database_url: str | None = typer.Option(
        None,
        envvar="EVAL_DATABASE_URL",
        help="Migrated Postgres to use; default: a throwaway container",
    ),
) -> None:
    """Run every golden through the in-process stack; fail if the baseline gate is broken."""
    from qgate_eval.golden import load_all
    from qgate_eval.scoring import score, summarise

    if mode not in ("replay", "live", "record"):
        raise typer.BadParameter("mode must be replay, live or record")
    cases = load_all(goldens)
    if only:
        cases = [c for c in cases if c.id == only]
    typer.echo(f"{len(cases)} golden cases in {goldens} (mode={mode})")
    if not cases:
        return

    model = _model(mode)
    with _Database(database_url) as url:
        from qgate_eval.runner import run_golden
        from qgate_eval.stack import Stack

        stack = Stack(url, model, mode, cassettes)  # type: ignore[arg-type]  # validated below
        try:
            scores = []
            for g in cases:
                s = score(run_golden(stack, g, on_log=lambda m: console.print(f"[yellow]{m}")))
                scores.append(s)
                console.print(
                    f"{g.id:18s} expected {g.expected.decision.value:8s} got {s.case.decided:8s} "
                    f"escapes {s.escapes:3d}  held {len(s.case.held):4d}  "
                    f"{'ok' if s.decision_match else 'MISMATCH'}"
                )
        finally:
            stack.close()

    metrics = summarise(scores)
    metrics["mode"], metrics["model"], metrics["recorded_at"] = (
        mode,
        model.name,
        datetime.now(UTC).isoformat(),
    )
    _print(metrics)
    if metrics_out:  # committed files: LF and a trailing newline on every OS
        _write(metrics_out, json.dumps(metrics, indent=1) + "\n")
    if report:
        _write(report, _markdown(metrics))
    if baseline is not None:
        _gate(metrics, baseline)


@app.command()
def serve(
    golden: str = typer.Option("drift-05", help="Golden to load and run to the gate"),
    port: int = typer.Option(8000),
    tokens_out: Path = typer.Option(
        Path("console/e2e/.tokens.json"), help="Where to write dev JWTs for the console/Playwright"
    ),
    cassettes: Path = typer.Option(Path("eval/cassettes")),
) -> None:
    """The in-process stack on a real port with one proposal waiting at the gate: what the console
    and its Playwright smoke test talk to. Replay mode, throwaway Postgres, no compose."""
    import uvicorn

    from qgate_core.auth import Role, mint
    from qgate_eval.golden import Golden
    from qgate_eval.runner import load_case
    from qgate_eval.stack import SECRET, Stack

    with _Database(None) as url:
        stack = Stack(url, _model("replay"), "replay", cassettes)
        try:
            g = Golden.load(ROOT / "eval" / "goldens" / f"{golden}.yaml")
            _, eol_ts = load_case(url, g)
            assert stack.agent is not None
            stack.agent.post(
                "/triage",
                json={
                    "vin": g.trigger.vin,
                    "fault_codes": g.trigger.fault_codes,
                    "eol_ts": eol_ts.isoformat(),
                    "golden_id": g.id,
                },
            )
            tokens = {
                role.value: mint(f"dev-{role.value}", role, SECRET)
                for role in (Role.VIEWER, Role.APPROVER)
            }
            _write(tokens_out, json.dumps(tokens, indent=1) + "\n")
            typer.echo(f"{golden} waiting at the gate; tokens in {tokens_out}")
            uvicorn.run(stack.api_app, host="127.0.0.1", port=port, log_level="warning")
        finally:
            stack.close()


@app.command()
def goldens(
    out: Path = typer.Option(Path("eval/goldens")),
    scenarios_dir: Path = typer.Option(Path("scenarios")),
) -> None:
    """(Re)author the fifty golden cases from generator ground truth. Deliberate, reviewed."""
    from qgate_eval.author import author

    written = author(scenarios_dir, out)
    typer.echo(f"{len(written)} goldens written to {out}")


def _model(mode: str) -> Any:
    """Replay needs no provider; live/record build the configured one."""
    if mode == "replay":

        class Recorded:
            name = os.environ.get("LLM_MODEL", "recorded")

            def invoke(self, prompt: str, schema: Any) -> Any:
                raise RuntimeError("replay must never reach the model")

        return Recorded()
    from qgate_agent.llm import LangChainModel

    return LangChainModel(
        os.environ["LLM_MODEL"], os.environ["LLM_PROVIDER"], os.environ.get("LLM_API_KEY")
    )


class _Database:
    """A migrated Postgres: the one given, or a throwaway container."""

    def __init__(self, url: str | None) -> None:
        self.url = url
        self.container: Any = None

    def __enter__(self) -> str:
        if self.url:
            return self.url
        import psycopg
        from testcontainers.postgres import PostgresContainer

        from qgate_core.migrate import apply_migrations
        from qgate_generator.line import Line
        from qgate_generator.seed import seed_dims

        self.container = PostgresContainer(
            "postgres:16.4", username="qgate_migrate", dbname="qgate"
        ).__enter__()
        url = self.container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
        with psycopg.connect(url) as conn:
            apply_migrations(conn, role_password="eval")  # noqa: S106 — throwaway container
            seed_dims(conn, Line.load(ROOT / "scenarios" / "line.yaml"))
        return str(url)

    def __exit__(self, *exc: object) -> None:
        if self.container is not None:
            self.container.__exit__(None, None, None)


def _gate(metrics: dict[str, Any], baseline: Path) -> None:
    base = json.loads(baseline.read_text(encoding="utf8"))
    if base.get("escapes") is None:
        typer.echo("no baseline recorded yet: gate inactive (write one with --metrics-out)")
        return
    failures = []
    if metrics["escapes"] > base["escapes"]:
        failures.append(f"escapes rose: {base['escapes']} -> {metrics['escapes']}")
    p95, base_p95 = metrics["latency_non_llm_p95_ms"], base.get("latency_non_llm_p95_ms")
    # shared CI runners jitter by hundreds of ms; only a real regression should fail the build
    if base_p95 and p95 > max(2 * base_p95, base_p95 + LATENCY_SLACK_MS):
        failures.append(f"non-LLM p95 regressed: {base_p95} -> {p95} ms")
    if failures:
        for f in failures:
            typer.echo(f"GATE FAILED: {f}", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        f"gate passed: escapes {metrics['escapes']} <= {base['escapes']}, non-LLM p95 {p95} ms"
    )


def _print(m: dict[str, Any]) -> None:
    t = Table(title=f"qgate-agent — {m['cases']} goldens, {m['mode']} / {m['model']}")
    for col in (
        "family",
        "cases",
        "escapes",
        "precision",
        "recall",
        "decision",
        "agreement",
        "abstain ok",
        "p95 ms",
    ):
        t.add_column(col)
    rows = [("all", m), *sorted(m["by_family"].items())]
    for name, b in rows:
        t.add_row(
            name,
            str(b["cases"]),
            str(b["escapes"]),
            _f(b["precision"]),
            _f(b["recall"]),
            _f(b["decision_match"]),
            _f(b["agreement_rate"]),
            _f(b["abstention_correct_rate"]),
            str(b["latency_p95_ms"]),
        )
    console.print(t)
    console.print(f"cost per triage: {m['cost_per_triage_usd']} USD (price table is an assumption)")


def _f(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def _markdown(m: dict[str, Any]) -> str:
    lines = [
        f"# Evaluation — {m['cases']} goldens ({m['mode']}, {m['model']}, {m['recorded_at'][:10]})",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Escapes | **{m['escapes']}** |",
        f"| Containment precision / recall | {_f(m['precision'])} / {_f(m['recall'])} |",
        f"| Decision match | {_f(m['decision_match'])} |",
        f"| Agreement rate (approved unamended) | {_f(m['agreement_rate'])} |",
        f"| Abstention correct rate | {_f(m['abstention_correct_rate'])} |",
        f"| Latency p50 / p95 (total) | {m['latency_p50_ms']} / {m['latency_p95_ms']} ms |",
        f"| Latency p95 (LLM only / non-LLM) | {m['latency_llm_p95_ms']} / "
        f"{m['latency_non_llm_p95_ms']} ms |",
        f"| Cost per triage | {m['cost_per_triage_usd']} USD (assumption) |",
        "",
        "| Family | Cases | Escapes | Precision | Recall | Decision match |",
        "|---|---|---|---|---|---|",
    ]
    for f, b in sorted(m["by_family"].items()):
        lines.append(
            f"| {f} | {b['cases']} | {b['escapes']} | {_f(b['precision'])} | {_f(b['recall'])} | "
            f"{_f(b['decision_match'])} |"
        )
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf8", newline="\n") as f:
        f.write(text)
