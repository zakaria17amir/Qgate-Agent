"""Traces: one OpenTelemetry provider per process, exported over OTLP/HTTP to Langfuse.

No Langfuse SDK — the endpoint and a basic-auth header are the whole integration, so any OTLP
sink is a URL change. Without keys nothing is exported and ``span()`` costs a context manager.
"""

import base64
import functools
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def exporter_from_env() -> OTLPSpanExporter | None:
    """Langfuse's OTLP endpoint with ``Basic pk:sk``; ``None`` when no keys are configured."""
    pk, sk = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if not (pk and sk):
        return None
    base = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://langfuse-web:3000/api/public/otel")
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    return OTLPSpanExporter(
        endpoint=f"{base.rstrip('/')}/v1/traces", headers={"Authorization": f"Basic {token}"}
    )


def configure(service: str, exporter: SpanExporter | None = None) -> None:
    """Install the process tracer; call once from ``main()`` (tests pass an in-memory exporter)."""
    exporter = exporter or exporter_from_env()
    if exporter is None:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    processor = (  # in-memory exporters are read synchronously by tests
        SimpleSpanProcessor(exporter)
        if isinstance(exporter, InMemorySpanExporter)
        else BatchSpanProcessor(exporter)
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[trace.Span]:
    """A span with the given attributes; ``None`` values are dropped (OTel rejects them)."""
    tracer = trace.get_tracer("qgate")
    with tracer.start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v)
        yield s


def traced[**P, R](name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator: run the function inside a span called ``name`` (used on the agent's tools)."""

    def deco(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            with span(name):
                return fn(*args, **kwargs)

        return wrapped

    return deco
