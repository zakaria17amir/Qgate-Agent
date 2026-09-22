"""Turn the evaluation numbers into the static page GitHub Pages serves (design §14)."""

import json
import shutil
from html import escape
from pathlib import Path
from typing import Any

from prefect import flow, task

ROOT = Path(__file__).parents[2]


def _f(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def render_site(m: dict[str, Any]) -> str:
    """One HTML page, no dependencies: the headline table, the per-family table, the links."""
    rows = "".join(
        f"<tr><td>{escape(str(k))}</td><td>{v}</td></tr>"
        for k, v in (
            ("Golden cases", m["cases"]),
            ("Escapes", f"<strong>{m['escapes']}</strong>"),
            ("Containment precision / recall", f"{_f(m['precision'])} / {_f(m['recall'])}"),
            ("Decision match", _f(m["decision_match"])),
            ("Agreement rate (approved unamended)", _f(m["agreement_rate"])),
            ("Abstention correct rate", _f(m["abstention_correct_rate"])),
            ("Latency p50 / p95 (total)", f"{m['latency_p50_ms']} / {m['latency_p95_ms']} ms"),
            (
                "Latency p95 (LLM only / non-LLM)",
                f"{m['latency_llm_p95_ms']} / {m['latency_non_llm_p95_ms']} ms",
            ),
            ("Cost per triage", f"{m['cost_per_triage_usd']} USD (price table is an assumption)"),
            ("Mode / model", f"{escape(str(m['mode']))} / {escape(str(m['model']))}"),
            ("Recorded", escape(str(m["recorded_at"])[:19].replace("T", " ")) + " UTC"),
        )
    )
    fam = "".join(
        f"<tr><td>{escape(f)}</td><td>{b['cases']}</td><td>{b['escapes']}</td>"
        f"<td>{_f(b['precision'])}</td><td>{_f(b['recall'])}</td><td>{_f(b['decision_match'])}</td></tr>"
        for f, b in sorted(m["by_family"].items())
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>qgate-agent — evaluation</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:52rem;margin:3rem auto;padding:0 1rem;
  color:#14181c}}
table{{border-collapse:collapse;margin:1rem 0 2rem}}
td,th{{padding:.3rem .8rem;border-bottom:1px solid #c9cfd5;text-align:left}}
th{{font-weight:500;color:#4b5560}}code{{font-family:ui-monospace,monospace}}
</style>
<h1>qgate-agent — evaluation</h1>
<p>Fifty golden cases run end to end (failure → proposal → scripted human → plant-system hold),
scored per <a href="https://github.com/zakaria17amir/Qgate-Agent/blob/main/docs/eval.md">docs/eval.md</a>.
Synthetic data throughout; escapes are all in the <code>overlap</code> family, where two
containments are needed and one is proposed (known limitation).</p>
<table>{rows}</table>
<h2>By family</h2>
<table><tr><th>Family</th><th>Cases</th><th>Escapes</th><th>Precision</th><th>Recall</th>
<th>Decision match</th></tr>{fam}</table>
<p>Artifacts: <a href="report.md">report.md</a> · <a href="metrics.json">metrics.json</a> ·
<a href="baseline.json">baseline.json</a> (the CI gate's reference) ·
<a href="https://github.com/zakaria17amir/Qgate-Agent/blob/main/docs/latency.md">latency
methodology</a> ·
<a href="https://github.com/zakaria17amir/Qgate-Agent/blob/main/observability/grafana/dashboards/qgate.json"
>dashboard</a></p>
"""


@task
def write_site(metrics_path: Path, out: Path) -> Path:
    metrics = json.loads(metrics_path.read_text(encoding="utf8"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_site(metrics), encoding="utf8", newline="\n")
    for name in ("report.md", "metrics.json", "baseline.json"):
        src = metrics_path.parent / name
        if src.exists():
            shutil.copy(src, out / name)
    return out


@flow(name="publish-report")
def publish_report(
    metrics_path: Path = ROOT / "eval" / "metrics.json", out: Path = ROOT / "eval" / "site"
) -> str:
    """Render ``eval/site/``; the nightly workflow deploys that directory to GitHub Pages."""
    return str(write_site(metrics_path, out))
