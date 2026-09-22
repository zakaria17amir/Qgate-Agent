"""The §11 metric names are a contract: the dashboard depends on them."""

import pytest
from prometheus_client import generate_latest

from qgate_core import metrics

pytestmark = pytest.mark.unit

CONTRACT = {
    "triage_duration_seconds",
    "triage_outcomes_total",
    "gate_pending",
    "gate_decision_seconds",
    "gate_decisions_total",
    "llm_tokens_total",
    "llm_cost_usd_total",
    "mes_requests_total",
    "mes_breaker_state",
    "ingest_records_total",
    "genealogy_query_seconds",
}


def test_every_contract_name_is_defined_and_scrapeable() -> None:
    metrics.TRIAGE_DURATION.labels(phase="total").observe(1.2)
    metrics.TRIAGE_OUTCOMES.labels(outcome="PROPOSED").inc()
    metrics.GATE_DECISION_SECONDS.observe(42)
    metrics.GATE_DECISIONS.labels(decision="APPROVE").inc()
    metrics.LLM_TOKENS.labels(kind="prompt", prompt_id="hypothesise").inc(100)
    metrics.LLM_COST_USD.inc(0.003)
    metrics.MES_REQUESTS.labels(status="201").inc()
    metrics.set_breaker_state("open")
    metrics.INGEST_RECORDS.labels(topic="line.measurements", result="ok").inc()
    metrics.GENEALOGY_QUERY_SECONDS.observe(0.02)
    metrics.gate_pending_collector(lambda: 3)
    text = generate_latest(metrics.REGISTRY).decode()
    for name in CONTRACT:
        assert name in text, name
    assert CONTRACT == set(metrics.NAMES)
    assert "gate_pending 3.0" in text


def test_breaker_state_is_one_hot() -> None:
    metrics.set_breaker_state("half_open")
    text = generate_latest(metrics.REGISTRY).decode()
    assert 'mes_breaker_state{state="half_open"} 1.0' in text
    assert 'mes_breaker_state{state="open"} 0.0' in text
    assert 'mes_breaker_state{state="closed"} 0.0' in text


def test_duration_buckets_span_a_tenth_of_a_second_to_a_minute() -> None:
    buckets = metrics.TRIAGE_DURATION._upper_bounds
    assert buckets[0] == 0.1 and 60.0 in buckets
