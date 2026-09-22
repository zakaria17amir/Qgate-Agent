# Latency — what is measured, how, and the numbers

Every number below names its boundary, its method and its *n*. Numbers without those three are
not in this file.

## Boundaries

| Name | From | To | Where it is measured |
|---|---|---|---|
| **triage total** | first node starts (`intake`) | `report` writes the audit row | agent, per thread: sum of node wall times (`timings_ms`); metric `triage_duration_seconds{phase="total"}` |
| **triage llm** | a model call starts | its structured answer is validated | agent `_ask`; `phase="llm"`; span `llm.<prompt_id>` |
| **triage non-LLM** | total − llm | | `phase="non_llm"`; this is the part the eval gate guards |
| **triage → proposal** | `POST /triage` accepted by the api | the PROPOSED row is visible on `GET /containments?thread_id=` | k6, from the client, over HTTP; includes queueing behind the agent's 4 triage workers |
| **approve → committed** | `POST /containments/{id}/approve` | `GET /containments/{id}` says `COMMITTED` | k6, from the client; includes the agent resume, the plant-system (mock MES) write and the report |
| **gate decision** | proposal written | human decision recorded | api; `gate_decision_seconds` — a human's time, not the system's |
| **genealogy query** | SQL start | rows returned | agent tool; `genealogy_query_seconds` |

Node-level detail is in the spans (Langfuse): `node.*`, `tool.*`, `llm.*` per thread.

## Method

Two instruments, deliberately different:

1. **Evaluation run** (`make eval-replay`, CI): 50 golden cases one at a time through the
   in-process stack; `latency_total_ms` / `latency_llm_ms` from the audit rows. In replay mode the
   model answers from cassettes, so the LLM share is ~0 and the number is the deterministic path
   alone. This is the regression gate (fails on p95 non-LLM > 2× baseline + 500 ms).
2. **Load test** (`make load`): k6 against the compose stack on one laptop — 5 virtual users for
   2 min, a burst of 50 for 30 s, 5 for 1 min. Each iteration is one failure end to end (trigger →
   proposal → approve → committed). The agent runs in **replay mode**: the model's own latency is
   excluded and no provider is billed, so the numbers are the system under load, not the model.
   The same golden (`drift-05`) is triggered every time, so the work per triage is identical.

The live model's share is measured separately, from real calls (below).

## Numbers (2026-09-23, one laptop: 16 vCPU Docker Desktop, 12 GB; all services on it)

**Load test** — `eval/load.json`, n = 1 090 end-to-end iterations, 0 failures, 9 500 HTTP requests,
0 non-2xx; `gate_pending` back to 0 afterwards; consumer lag stayed at 0.

| Measure | p50 | p95 | p99 | max |
|---|---|---|---|---|
| triage → proposal | 518 ms | 3.6 s | 4.3 s | 5.1 s |
| approve → committed | 526 ms | 3.6 s | 14.4 s | 29.1 s |
| api request (any) | 6 ms | 73 ms | — | 611 ms |

Reading it: at 5 concurrent failures the system answers in half a second; the burst of 50 queues
behind the agent's four triage workers (by design — a burst on the line must not starve the
health checks), which is the p95. The p99/max of approve → committed is one iteration in ~1 000
that hit the api's sweeper path (an approval arriving in the beat between the proposal row
appearing and the triage worker releasing the thread is re-sent 30 s later) — recorded, not
hidden.

**Deterministic path** (eval baseline, n = 50 cases, replay): total p50 106 ms, p95 128 ms;
non-LLM p95 127 ms. `eval/baseline.json`.

**Live model** (claude-haiku-4-5 via the Anthropic API, n = 264 real triages from a replayed
line on 2026-09-22, two model calls per triage): LLM share p50 **3.9 s**, p95 **5.7 s**,
p99 **8.7 s**; whole triage p50 3.9 s, p95 5.8 s; mean cost **$0.0031** per triage (price table
is an assumption, `qgate_core/pricing.py`). So in production the model is ~90 % of a triage's
wall time and the deterministic part is ~100 ms.

## What is not measured here

- Human decision time (`gate_decision_seconds`) — reported on the dashboard, not benchmarked.
- The real plant system: `mock-mes` answers in milliseconds; a real MES will not.
- Network: everything ran on one host. Add your RTTs.
