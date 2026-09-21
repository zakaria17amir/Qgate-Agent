# qgate-agent

> **Status: skeleton.** Architecture is fixed; services are not yet implemented. See [`docs/design/2026-09-21-architecture.md`](docs/design/2026-09-21-architecture.md).

When a vehicle fails end-of-line test, someone has to decide within minutes how many vehicles to quarantine — too narrow and a defect escapes to a customer, too wide and hundreds of good cars are held. `qgate-agent` correlates the failure against build genealogy and station drift, proposes a containment window, and **requires a human to approve it before anything is written**. It runs on a simulated line and is measured on fifty golden scenarios — including the ones where the right answer is to propose nothing.

## Metrics

_Published after the first nightly evaluation run. Until then this table is intentionally empty._

| Metric | Value | n |
|---|---|---|
| Escapes | — | — |
| Containment precision / recall | — | — |
| Agreement rate (approved unamended) | — | — |
| Abstention rate (correct / total) | — | — |
| Proposal latency p50 / p95 / p99 | — | — |
| Cost per triage (USD, assumptions labelled) | — | — |

## Run it

```bash
cp .env.example .env
make up          # core stack
make demo        # replay the tool-wear scenario, open http://localhost:8080
```

`make help` lists every target. Each maps to one CI job.

## How it works

```
line-sim (C++) ──Kafka──▶ ingest ──▶ Postgres ◀── agent tools (read-only)
                  │                                   │
                  ├──────▶ detect ◀── HTTP ───────────┤  LangGraph triage graph
                  │                                   │  … → compose → GATE → commit
                  └──────▶ agent ◀── eol failures     │
                                                      ▼
                        console ──▶ api ◀── approve / amend / reject ──▶ mock-mes
```

The agent's blast radius is one pending record awaiting a human. Every tool is read-only except `submit_for_approval`, and the database role it uses cannot write.

## Repository map

| Path | What |
|---|---|
| `packages/qgate-core` | Shared domain models, Avro, Kafka, OTel, auth |
| `packages/qgate-generator` | Synthetic line, seven defect scenarios with ground truth, Python replay producer |
| `services/line-sim` | C++ event producer at takt |
| `services/ingest` `detect` `agent` `api` `mock-mes` | See architecture doc §4–§6 |
| `console` | React approval console |
| `pipelines` | Prefect flows: replay, nightly eval, publish |
| `schemas` | Avro contracts for the five topics |
| `knowledge/fault_map.yaml` | Hand-authored fault code → candidate stations |
| `eval/goldens` | Fifty golden cases, frozen before the agent existed |
| `docs/adr` | Architecture decision records |

## Data and licence

All committed data is synthetic. Competition datasets (e.g. Bosch Production Line Performance) are never committed; an optional adapter reads them from a local path you supply. Code is MIT.
