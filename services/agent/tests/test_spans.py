"""Every node and every model call is a span with the attributes design §11 names."""

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from qgate_agent.graph import _timed
from qgate_agent.state import TriageState
from qgate_core import otel

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def spans() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    otel.configure("agent-test", exporter)
    return exporter


def test_a_node_runs_inside_a_span_named_after_it(spans: InMemorySpanExporter) -> None:
    spans.clear()
    state: TriageState = {"thread_id": "t-1", "golden_id": "drift-03", "timings_ms": {}}
    out = _timed("intake", lambda s: {"vin": "SYN1"})(state)
    assert out["vin"] == "SYN1" and "intake" in out["timings_ms"]
    (s,) = spans.get_finished_spans()
    assert s.name == "node.intake"
    assert s.attributes is not None
    assert s.attributes["thread_id"] == "t-1" and s.attributes["golden_id"] == "drift-03"
    assert s.attributes["node"] == "intake"
