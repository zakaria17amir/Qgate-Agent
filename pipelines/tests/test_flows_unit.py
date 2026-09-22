"""The pure parts of the flows: the site renderer and the guard that keeps the nightly off the
core stack's database (Phase 5 Review Focus 3)."""

import pytest

from flows.nightly_eval import require_eval_db
from flows.publish_report import render_site

pytestmark = pytest.mark.unit

METRICS = {
    "cases": 50,
    "escapes": 260,
    "precision": 0.59,
    "recall": 0.96,
    "decision_match": 0.96,
    "agreement_rate": 0.66,
    "abstention_correct_rate": 1.0,
    "latency_p50_ms": 106,
    "latency_p95_ms": 128,
    "latency_llm_p95_ms": 2,
    "latency_non_llm_p95_ms": 127,
    "cost_per_triage_usd": 0.003293,
    "mode": "live",
    "model": "claude-haiku-4-5",
    "recorded_at": "2026-09-23T02:00:00+00:00",
    "by_family": {
        "drift": {
            "cases": 12,
            "escapes": 0,
            "precision": 0.8,
            "recall": 1.0,
            "decision_match": 1.0,
        },
        "overlap": {
            "cases": 4,
            "escapes": 260,
            "precision": 0.33,
            "recall": 0.51,
            "decision_match": 0.5,
        },
    },
}


def test_site_is_one_html_page_with_the_numbers_and_the_links() -> None:
    html = render_site(METRICS)
    assert html.startswith("<!doctype html>")
    for needle in ("260", "0.96", "claude-haiku-4-5", "2026-09-23", "overlap", "drift"):
        assert needle in html
    for link in ("report.md", "metrics.json", "baseline.json"):
        assert f'href="{link}"' in html
    assert "assumption" in html  # the cost line is labelled


def test_nightly_refuses_any_database_but_eval_db() -> None:
    require_eval_db("postgresql://qgate_migrate:x@eval-db:5432/qgate")
    with pytest.raises(ValueError, match="eval-db"):
        require_eval_db("postgresql://qgate_migrate:x@postgres:5432/qgate")
    with pytest.raises(ValueError, match="eval-db"):
        require_eval_db("postgresql://qgate_migrate:x@localhost:5433/qgate")
