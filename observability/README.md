# observability

| File | Purpose |
|---|---|
| `prometheus.yml` | Scrape every service's `/metrics` plus Redpanda's public metrics |
| `grafana/provisioning/` | Datasource + dashboard provider, so `make up-all` yields a working dashboard with no clicking |
| `grafana/dashboards/qgate.json` | The one dashboard: throughput & lag, triage latency by phase, gate queue, outcomes, cost, MES breaker, SLO burn (added Phase 5) |
| `toxiproxy.json` | Chaos profile: `agent -> mock-mes` routed through toxiproxy so outages can be injected |

Metric names are a contract; they are listed in `docs/design/2026-09-21-architecture.md` §11 and the dashboard depends on them.
