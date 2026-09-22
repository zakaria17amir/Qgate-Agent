"""The §11 metrics, defined once so every service and the dashboard agree on the names.

All on the default registry that ``health_app`` already serves at ``/metrics``. Services
import the objects they update; nothing here talks to a database or a broker.
"""

from collections.abc import Callable, Iterator

from prometheus_client import REGISTRY as REGISTRY  # re-exported: tests scrape it
from prometheus_client import Counter, Gauge, Histogram
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

BUCKETS = (0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60)  # 0.1 .. 60 s: a triage, model included

TRIAGE_DURATION = Histogram(
    "triage_duration_seconds", "Wall time of one triage", ["phase"], buckets=BUCKETS
)
TRIAGE_OUTCOMES = Counter("triage_outcomes_total", "How triages ended", ["outcome"])
GATE_DECISION_SECONDS = Histogram(
    "gate_decision_seconds",
    "Proposal to human decision",
    buckets=(10, 30, 60, 120, 300, 600, 1200, 1800, 3600),
)
GATE_DECISIONS = Counter("gate_decisions_total", "Human decisions and expiries", ["decision"])
LLM_TOKENS = Counter("llm_tokens_total", "Model tokens", ["kind", "prompt_id"])
LLM_COST_USD = Counter("llm_cost_usd_total", "Estimated model spend (price table is an assumption)")
MES_REQUESTS = Counter("mes_requests_total", "Calls to the plant system", ["status"])
MES_BREAKER_STATE = Gauge("mes_breaker_state", "1 for the current breaker state", ["state"])
INGEST_RECORDS = Counter("ingest_records_total", "Records consumed", ["topic", "result"])
GENEALOGY_QUERY_SECONDS = Histogram(
    "genealogy_query_seconds", "genealogy_by_vin", buckets=(0.005, 0.01, 0.02, 0.05, 0.1, 0.5, 1)
)

BREAKER_STATES = ("closed", "open", "half_open")
for _s in BREAKER_STATES:
    MES_BREAKER_STATE.labels(state=_s).set(1.0 if _s == "closed" else 0.0)

NAMES = (
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
)


def set_breaker_state(state: str) -> None:
    """One-hot: exactly one of closed/open/half_open is 1."""
    for s in BREAKER_STATES:
        MES_BREAKER_STATE.labels(state=s).set(1.0 if s == state else 0.0)


class _Pending(Collector):
    def __init__(self, count: Callable[[], int]) -> None:
        self.count = count

    def collect(self) -> Iterator[Metric]:
        try:
            n = self.count()
        except Exception:  # a scrape must not fail because the database is unreachable
            return
        yield GaugeMetricFamily("gate_pending", "Proposals awaiting a decision", n)


_pending: _Pending | None = None


def gate_pending_collector(count: Callable[[], int]) -> None:
    """``gate_pending`` is counted on scrape (one query), so it is exact across processes.
    Registering again rebinds the counter (tests build several apps per process)."""
    global _pending
    if _pending is None:
        _pending = _Pending(count)
        REGISTRY.register(_pending)
    else:
        _pending.count = count
