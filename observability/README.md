# observability

| File | Purpose |
|---|---|
| `prometheus.yml` | Scrape every service's `/metrics` plus Redpanda's public metrics |
| `prometheus-rules.yml` | Recording rule `kafka_consumer_lag{group,topic}` from Redpanda's committed offsets and log ends |
| `grafana/provisioning/` | Datasource + dashboard provider, so `make up-all` yields a working dashboard with no clicking |
| `grafana/dashboards/qgate.json` | The one dashboard (uid `qgate`): throughput & lag, triage latency by phase, gate queue and decision time, outcomes, cost per triage, MES requests and breaker state, error shares, two SLO panels, genealogy p95, line-sim throughput |
| `toxiproxy.json` | Chaos profile: `agent -> mock-mes` routed through toxiproxy so outages can be injected |

Metric names are a contract: defined once in `packages/qgate-core/src/qgate_core/metrics.py`
(the §11 list of `docs/design/2026-09-21-architecture.md`), and a unit test fails if a dashboard
panel names a metric nobody emits.

Traces go to Langfuse (`obs` profile, `http://localhost:3001`) over OTLP — ADR-013. Every graph
node, tool call and model call is a span; log lines are JSON with the trace id.

![dashboard](../docs/img/dashboard.png)
