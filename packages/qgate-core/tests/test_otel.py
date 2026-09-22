"""Spans and JSON logs: on when Langfuse keys exist, silent when they do not."""

import json
import logging

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from qgate_core import otel
from qgate_core.logs import JsonFormatter

pytestmark = pytest.mark.unit


def test_without_keys_configure_installs_no_exporter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review Focus 1: the default .env has no Langfuse keys; nothing may try to export."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert otel.exporter_from_env() is None


def test_keys_become_basic_auth_to_the_otlp_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-1")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-2")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://langfuse-web:3000/api/public/otel")
    exporter = otel.exporter_from_env()
    assert exporter is not None
    assert exporter._endpoint == "http://langfuse-web:3000/api/public/otel/v1/traces"
    assert exporter._headers["Authorization"] == "Basic cGstbGYtMTpzay1sZi0y"


def test_span_records_attributes(spans: InMemorySpanExporter) -> None:
    spans.clear()
    with otel.span("node.intake", thread_id="t-1", golden_id=None, n=3):
        pass
    (s,) = spans.get_finished_spans()
    assert s.name == "node.intake"
    assert dict(s.attributes or {}) == {"thread_id": "t-1", "n": 3}  # None is dropped


def test_log_lines_are_json_with_the_active_trace_id(spans: InMemorySpanExporter) -> None:
    record = logging.LogRecord("agent", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    with otel.span("node.report"):
        ctx = trace.get_current_span().get_span_context()
        line = json.loads(JsonFormatter().format(record))
    assert line["msg"] == "hello world" and line["level"] == "INFO" and line["logger"] == "agent"
    assert line["trace_id"] == format(ctx.trace_id, "032x")
    assert "trace_id" not in json.loads(JsonFormatter().format(record))  # outside a span: absent
