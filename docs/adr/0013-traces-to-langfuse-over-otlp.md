# ADR-013: Traces go to Langfuse over OTLP; the v3 stack is the price

**Status:** Accepted · **Date:** 2026-09-23

## Context

Design §11 wants one span per graph node, per tool call and per model call, exported to Langfuse
with the thread, golden, node and prompt identifiers as attributes — so a triage can be read as a
trace and the model's share of time and tokens is visible per call. The compose file had pinned
Langfuse **2.93**, which only accepts its legacy ingestion API; the OTLP endpoint
(`/api/public/otel`) exists from Langfuse v3, whose self-hosted form needs ClickHouse, Redis and an
S3-compatible store besides Postgres. Two ways to instrument: the Langfuse Python SDK, or the
OpenTelemetry SDK straight to that endpoint.

## Decision

Instrument with the **OpenTelemetry SDK only** (`qgate_core/otel.py`): one `TracerProvider` per
process, an OTLP/HTTP exporter to `OTEL_EXPORTER_OTLP_ENDPOINT` with `Authorization: Basic
base64(public:secret)` built from the Langfuse keys, and a `span()` context manager. No keys, no
exporter, no error — the default `.env.example` runs silent. Spans open in the three places that
already know the timings: the agent's node wrapper (`node.<name>`, `thread_id`, `golden_id`), the
model call (`llm.<prompt_id>`, `prompt_version`, token counts) and the five tools (`tool.<name>`);
the api's decision path (`api.decide`). Logs are one JSON object per line carrying the active
`trace_id`, so a log and its span meet. The `obs` profile runs Langfuse v3/v4 (web, worker,
ClickHouse, MinIO, Redis, its own Postgres); `LANGFUSE_INIT_*` provisions the org, project and the
keys from `.env` on first start, so CI and a fresh laptop get the same credentials without a click.
The unused `langfuse` SDK dependency is removed.

## Alternatives considered

- **Langfuse Python SDK** — a second tracing API in the codebase for the same spans; its v4 is OTel
  underneath anyway. Rejected: the endpoint is the integration.
- **Stay on Langfuse v2 with its ingestion API** — no OTLP; the SDK path above, plus a data model
  Langfuse itself deprecates in November 2026.
- **Jaeger or Grafana Tempo** — one container, spans visible in Grafana Explore. Lighter, but the
  design and the spec name Langfuse three times for the LLM-specific views (tokens, cost, sessions).
  The exporter is a URL: switching later is a config change, which is the point of choosing OTel.

## Consequences

- `make up-all` gains five containers (~2 GB); `make up` is unchanged.
- Verified on the stack: one triage produced 16 observations across the nodes, tools and both
  model calls, `llm.compose` carrying `prompt_tokens=830 completion_tokens=185`,
  `service.name=agent`.
- Langfuse v4 answers `/api/public/v2/observations`; the v3 read endpoints return 404 in
  events-only mode. Tests and tooling use v2.
- The health check probes `http://$HOSTNAME:3000` because the app binds its container IP, not
  loopback.
- Metrics stay on Prometheus (`qgate_core/metrics.py`, the §11 names); traces and metrics are two
  signals, not one.
