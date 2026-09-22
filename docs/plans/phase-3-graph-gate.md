# Phase 3 — Graph, api, Gate, Eval Implementation Plan

> Execute with `executing-plans` (inline). TDD per task. Ponytail active.

**Goal:** A failure event produces a proposal a human can approve, amend or reject; the amendment is recorded with its diff; killing the agent mid-gate loses nothing; and the fifty goldens run end-to-end in `replay` mode as a CI gate with a committed baseline.

**Architecture:** The LangGraph triage graph (nine nodes, ADR-004) calls the Phase 2 tools; the model appears in exactly two places plus the escalation paragraph, always through a cassette layer (ADR-006). `api` owns containment state (ADR-008) and is the only writer; the agent talks to it over HTTP. The gate is `interrupt()` with a Postgres checkpointer (ADR-003). The eval harness wires api + agent + detect + mock-mes **in-process** with TestClients over a testcontainers Postgres, so `replay` needs no compose and no Kafka.

**Tech Stack:** langgraph 1.x, langgraph-checkpoint-postgres 3.x, langchain `init_chat_model`, FastAPI, PyJWT, psycopg pool, httpx.

**Spec:** design §6.2, §6.3, §8, §9.1–9.3; checklist §Phase 3.

## Global Constraints

- No configuration can skip the gate. The eval harness acts as the approver through the public endpoint with an `approver` token (ADR-003).
- Every model output is a Pydantic model validated against state: a station not in the fault map, or bounds that differ from `bound`'s, is rejected (one retry, then escalate).
- `replay` never calls a provider; a missing cassette is a test failure.
- Docstrings PEP 257 / Google; SQL one-line headers.

## Rulings taken while planning

- **In-process harness.** api, agent, detect and mock-mes are FastAPI apps; the harness builds them and connects them with TestClients. Kafka is optional in `api` (no producer → no `quality.containment` events) so replay runs on Postgres alone. Cost if wrong: the compose path is exercised manually at Gate 3 and by Phase 4 chaos tests, not by the eval gate.
- **Cassette layer at the `ask()` level**, not a LangChain Runnable: `ask(prompt_id, version, inputs, schema)` keyed by sha256 of those. Smaller, and the key is exactly what matters. Cost if wrong: streaming or tool-calling prompts later need a different wrapper.
- **Two candidate stations max** feed `correlate`/`drift_check`: the fault map has at most two; the model ranks them. Cost if wrong: none — the map is authored.
- **`bound` kinds by rule:** `top_lot_share ≥ 0.8 and n ≥ 3` → LOT; `drift.verdict in {DRIFT, STEP}` → WINDOW from onset to the trigger's station time; else SINGLE. Route: bench not capable → `bench_alert`; drift HIGH and `n ≤ 1` → `escalate`. Same thresholds Gate 2 proved.
- **Escapes scored against "affected so far":** VINs the correct containment should hold at trigger time — `by_inject` VINs with `seq ≤ trigger seq` (plus the trigger for SINGLE); NONE/ESCALATE expect an empty hold. Cost if wrong: it is a definition, written in `docs/eval.md`.
- **Expiry sweeper is a function** (`sweep_expired`) run by a thread in the api process and called directly by tests.
- **Pricing table** lives in `qgate_core/pricing.py` with one line per model and the date it was read; labelled assumption.

## Review Focus

1. A resume with an `amended` window whose start is *later* than the proposal's must still hold at least the trigger VIN → Task 6 test.
2. A second `approve` on an already-decided containment must be a 409, not a second commit → Task 4 test.
3. A cassette miss in `replay` must raise, never fall through to a live call → Task 3 test.
4. The model naming a station outside the fault map must be rejected and lead to escalation, not a containment → Task 5 test.
5. Killing the agent process between `gate` and `commit` must leave exactly one PROPOSED row and allow resume from a fresh process → Task 7 test.

---

### Task 1: JWT auth in qgate-core
`qgate_core/auth.py`: `Role` enum (viewer, approver, admin, service); `mint(sub, role, secret, ttl)`; FastAPI dependency `require(*roles)`; `make token` CLI in api. Tests: mint/verify; wrong role → 403; expired → 401.

### Task 2: api service — containment state
`services/api`: pool on `api_rw`; tables per migration 0003. Endpoints: `POST /internal/containments` (service role) → PROPOSED + audit row; `PATCH /internal/containments/{id}` (COMMITTED/ESCALATED/COMMIT_PENDING + timings/tokens/cost); `GET /containments?state=`, `GET /containments/{id}`, `GET /audit`. `sweep_expired(conn, now) -> list[id]`. Kafka producer optional. SQL in `db/queries/containment.sql`. Tests (integration): propose → get → list; PATCH records audit metrics; sweep flips PROPOSED past `expires_at` to EXPIRED.

### Task 3: LLM layer with cassettes
`qgate_agent/llm.py`: `Ask` class with `mode`, `dir`, `model`; `ask(prompt_id, version, inputs, schema) -> (schema instance, Usage)`; `record` writes `<key>.json` {inputs, output, usage, model}; `replay` reads or raises `CassetteMiss`. Prompts in `prompts/*.md` with front-matter `id`, `version`. `qgate_core/pricing.py`. Tests: replay hit/miss (RF3); record writes and replay returns equal; cost computed from usage.

### Task 4: api decision endpoints
`POST /containments/{id}/approve|amend|reject` (approver): update state, compute `diff` (proposal vs decision), write audit decision, call agent `POST /threads/{thread_id}/resume`. Second decision → 409 (RF2). Tests (integration, agent mocked with a TestClient stub): each path; 409.

### Task 5: graph — deterministic nodes, LLM nodes, gate, commit
`qgate_agent/state.py` (`TriageState`, `Bounds`, `HumanDecision`); `graph.py` `build_graph(deps, checkpointer)`; nodes as functions in `nodes.py` (one file; nine functions). `Deps`: `ro` (psycopg pool, agent_ro), `detect` (HttpGetter), `api` (client with service token), `mes` (client with API key), `ask` (Ask), `fault_map`. `hypothesise` → `Hypotheses(list[Hypothesis(station_id, characteristic_id, prior_reasoning)])` validated ⊆ fault map candidates (RF4). `compose` → `Order(text)` validated to contain the station id and VIN count. `gate`: submit → `interrupt(payload)` → `HumanDecision`. `commit`: MES `POST /v1/holds` with `Idempotency-Key = containment_id` then `PATCH … COMMITTED`. `report`: PATCH timings/usage. Tests (unit with fakes): route decisions; bound kinds; validator rejects an out-of-map station.

### Task 6: agent HTTP + consumer
`http.py`: `POST /triage`, `GET /threads/{id}`, `POST /threads/{id}/resume`; `consumer.py`: `line.eol.results` FAIL → `POST /triage`. Amend semantics: `amended.window_start` later than proposal → clamp to include the trigger (RF1). Tests (integration): full happy path in-process against mock-mes; amend path.

### Task 7: restart mid-gate
Test: run to `WAITING_GATE`, drop the graph object, build a fresh graph on the same checkpointer, resume APPROVE → exactly one containment row, one MES hold (RF5).

### Task 8: eval harness runner + scorers + baseline
`qgate_eval/runner.py`: per golden — COPY run, `POST /triage`, poll thread, act as the golden's human via api, collect audit + containment VINs; `scoring.py`: escapes, precision, recall, decision match, abstention correctness; `report.py`: markdown table; `cli run` compares to `eval/baseline.json` (escapes may not rise; non-LLM p95 ≤ 1.2×). `docs/eval.md` defines the metrics. Record cassettes with the live model once; commit `eval/cassettes/` and `eval/baseline.json`.

### Task 9: Gate 3
Compose: `api`, `agent` containers boot healthy; `curl` approve path once; ADR-007, ADR-008; checklist; CI green with the eval gate active; merge.
