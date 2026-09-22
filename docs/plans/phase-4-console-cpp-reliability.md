# Phase 4 — Console, C++ line-sim, Reliability Implementation Plan

> Execute with `executing-plans` (inline). TDD per task. Ponytail active.

**Goal:** A shift leader approves, amends or rejects a containment in a browser with no terminal; the line is replayed by a C++ producer at takt; a plant-system outage mid-commit produces exactly one hold and no lost approval; every service's `/ready` tells the truth.

**Architecture:** Three independent tracks that meet at Gate 4. *Reliability* adds a `commit → pending → retry_gate → commit` loop to the graph (the same "side effects and `interrupt()` never share a node" rule as `submit`/`gate`), a tiny breaker in front of the MES client, and an api sweeper that re-resumes `COMMIT_PENDING` threads. *Console* is four routes over the existing api plus two small api additions (evidence on the row, server-side VIN scoping/preview). *line-sim* is a C++ program that replays a stream **exported by the Python generator** at takt with a drift-free schedule, frames it in Confluent wire format and produces via librdkafka — C++ owns timing and transport, never the data model.

**Tech Stack:** tenacity (already a dependency), LangGraph cycles, FastAPI CORS; React 18 + react-router 7 + TanStack Query + `@fontsource/ibm-plex-*`, Playwright; C++20, librdkafka, nlohmann-json, cpp-httplib, Catch2 v2 (all from Debian bookworm).

**Spec:** design §6.2, §6.5, §9.3–9.4, §15; checklist §Phase 4; ADR-003, ADR-008.

## Global Constraints

- The gate is never bypassed: `COMMIT_PENDING` re-resume is a `RETRY` on an *already approved* containment; the sweeper still never approves (ADR-003).
- The api stays the only writer of containment tables (ADR-008); the agent's new nodes only PATCH through `/internal`.
- Ground truth has one source: the Python generator. C++ never interprets a scenario.
- Console: four routes, one CSS token file, no design system, no chart library, JWT pasted into a drawer and held in `sessionStorage` (§6.6). Fonts bundled — the plant network is offline.
- Docstrings PEP 257; C++ comments only where the *why* is not obvious; SQL one-line headers.

## Rulings taken while planning

- **C++ replays an exported stream** (`qgate-gen export` → JSONL of `{topic, key, ts_ms, avro_hex}`) rather than reading `scenarios/*.yaml`. Re-implementing the seeded stochastic model in C++ would give two sources of ground truth and ~800 duplicated lines for a weight-1 skill. The C++ does what an edge producer does: schedule, frame, produce, count, shut down cleanly. Recorded as ADR-011; the checklist item "scenario_reader" becomes "manifest reader". Cost if wrong: a scenario needs the Python step before the C++ one (`make demo` does both).
- **Hex, not base64 or a binary format**, for the Avro bytes: decodes in six lines of C++, stays greppable; ~2× file size (≈40 MB for 138k events) is fine.
- **Hand-written `api.ts` types.** The api serves `dict[str, Any]` bodies, so `openapi-typescript` would emit `object`. A 60-line typed client is smaller than a codegen step. Cost if wrong: a field rename in the api is caught by Playwright, not `tsc`.
- **Server-side VIN scoping.** `store.scope_vins` runs `db/queries/window.sql`; AMEND with changed bounds and no `vins` recomputes; `GET /containments/{id}/preview` reuses it for the console's live count. Fixes the Phase 3 gap where an amended window kept the old VIN list.
- **Evidence travels with the proposal** (`containment.evidence jsonb`, migration 0005). One column; the agent already holds the objects.
- **Breaker is a 15-line class**, not a library: open on failure for `open_s`, half-open lets one call through. The sweeper cadence (30 s) is the retry clock. Cost if wrong: per-process state — two agent replicas learn independently.
- **`/ready` is a callable passed to `health_app`**; each service names its real dependencies. Compose healthchecks move to `/ready`. `mock-mes` keeps `/health` only (no dependencies, ADR-005 forbids importing core).
- **Playwright runs against `qgate-eval serve`** — the in-process stack served by uvicorn on a port with one golden loaded to the gate — plus `vite preview`. Real HTTP, real build, no image builds in CI. Cost if wrong: the compose path is exercised by `make demo` and the chaos suite, not by CI.
- **Chaos suite is two pytest files under `tests/chaos/`** that talk to a running `make chaos` stack over HTTP (toxiproxy admin API + docker compose CLI). Not in the push CI; `make chaos-test` locally and in the nightly, per spec §11.

## Console design (frontend-design pass)

Subject: a shift leader deciding on a pending hold at end-of-line, on a shop-floor PC, under an expiry clock. Primary job: decide fast and correctly.

- **Palette** — `--paper #E9ECEE` (cool grey, bright-hall friendly), `--panel #FFFFFF`, `--ink #14181C`, `--ink-2 #4B5560`, `--rule #C9CFD5`; andon colours carry *state only*: `--amber #C98A00` pending, `--green #1E7F4D` committed, `--red #B3261E` rejected/escalated, `--steel #2A5A86` actions.
- **Type** — IBM Plex Sans for UI, IBM Plex Mono for identifiers (VIN, station, thread) and timestamps: fixed-width aids scanning columns of VINs, which is the job. Scale 13 / 15 / 18 / 24 / 40.
- **Layout** — left rail (Queue, Audit, token drawer) + content column ≤ 1100 px, left-aligned. Queue is a dense table with a time-to-expiry bar per row. Case: header (kind, station, VIN count, decide button), tabs below. Decide: form left, live preview right.
- **The one memorable element** — the case page's *window timeline*: an inline SVG of the proposed window with sibling entry ticks and the drift onset marked. Everything else is quiet tables. No page-load motion; TanStack's refetch is the only "live" behaviour.
- Reviewed against defaults: no cream/serif/terracotta, no dark+acid, no card grid, no all-caps eyebrows, no `→` on buttons. Plex is chosen for its engineering heritage, not as a default.

## Review Focus

1. MES acknowledges the hold but the response is lost (`drop_ack`) — the retry must replay the same idempotency key and end with **one** hold and `duplicate_replays ≥ 1` → Task 3 test.
2. The sweeper resuming a `COMMIT_PENDING` thread while a triage worker is *already* retrying it must not create a second hold — the api resume returns 409 when the thread is not waiting → Task 3 test.
3. Amending the window to a range that excludes the trigger VIN must still hold the trigger (Phase 3 RF1 now through the console's preview path) → Task 6 test.
4. A JWT with `viewer` role must see the queue but get a visible "not allowed" on decide, not a silent failure → Task 9 test.
5. `line-sim` killed by SIGTERM mid-replay must flush in-flight messages and exit 0 with the counter equal to messages acknowledged → Task 14 test.

---

### Task 1: `/ready` on every service
`qgate_core.health.health_app(service, ready: Callable[[], dict[str, bool]] | None = None)`; `GET /ready` → `200 {checks}` if all true, else `503 {checks}`. api: `db` (`select 1`), `agent` (GET `/health`). agent: `db_ro`, `db_checkpoint`, `detect`, `api`. detect: `db`. ingest: `kafka` (`list_topics(timeout=2)`), `db`. Compose healthchecks for api/agent/detect/ingest → `/ready`. Tests (unit): all-true → 200; one false → 503 with the failing name.

### Task 2: retries and breaker on the MES path
`qgate_agent/tools/mes.py`: `Breaker(open_s=60.0)` with `allow()`, `succeeded()`, `failed()`; `post_hold(client, breaker, containment_id, body) -> httpx.Response | None` — `None` when the breaker is open or five tenacity attempts (exponential jitter, cap 8 s, on `TransportError` or 5xx) fail. Module constants `ATTEMPTS`, `WAIT` so tests monkeypatch `WAIT = wait_none()`. Transport retries (`httpx.HTTPTransport(retries=3)`) on the agent's three clients in `main.py`. Tests (unit, fake client): 5xx×2 then 201 → 201 and breaker closed; 5xx×5 → `None`, breaker open; open breaker → `None` without a call; after `open_s` one call is allowed.

### Task 3: `COMMIT_PENDING` loop and sweeper
Graph: `commit` uses `post_hold`; `None` → outcome `COMMIT_PENDING`. New nodes `pending` (PATCH api `state=COMMIT_PENDING, reason`) and `retry_gate` (`interrupt({"containment_id", "waiting": "mes"})`, returns `{}`); edges `commit →(COMMIT_PENDING)→ pending → retry_gate → commit`. `ResumeRequest.decision` gains `RETRY`. api sweeper: every tick, for `state = 'COMMIT_PENDING'` rows POST resume `{decision: RETRY, actor: system}`; a 409 (worker already retrying) is logged, not an error (RF2). `GET /threads/{id}` reports `WAITING_RETRY` when `next == ["commit"]`-after-interrupt. Tests (in-process stack, `WAIT` patched): `drop_ack` for the first call → COMMIT_PENDING → sweep → COMMITTED, `holds == 1`, `duplicate_replays == 1` (RF1); `error 503` outage → pending → clear → sweep → COMMITTED; second sweep while thread already resumed → 409 handled.

### Task 4: chaos profile and suite
Compose: `agent.environment.MES_BASE_URL` overridable (`${MES_BASE_URL:-http://mock-mes:8003}`), chaos profile sets it to `http://toxiproxy:8003` via `.env`-free override file `docker-compose.chaos.yml` (already referenced by `$(CHAOS)`). `tests/chaos/test_mes_outage.py`: trigger triage via api, approve, disable the toxiproxy proxy for 20 s, re-enable, wait for the sweeper → `COMMITTED`, `/_stats.holds == 1`. `tests/chaos/test_kill_agent.py`: triage to gate, `docker compose kill agent`, `up -d agent`, approve → COMMITTED, one row. `make chaos-test` runs them with `-m chaos`; marker registered; skipped when `CHAOS_API_URL` unset.

### Task 5: evidence on the proposal
Migration `0005_evidence.sql`: `alter table qgate.containment add column evidence jsonb not null default '{}'`. `store.Proposal.evidence: dict[str, Any] = {}`; `propose` writes it; `get` returns it. Agent `submit` sends `{genealogy: [{station_id, entered_at, shift_id, parts_lots, out_of_tolerance}], hypotheses, siblings: {vins, entered_at, by_shift, by_lot}, drift, bench}`. Tests: api integration round-trips evidence; agent e2e asserts `evidence.siblings.vins` present on a drift golden.

### Task 6: VIN scoping, preview, CORS, multi-state list
`store.scope_vins(conn, kind, station_id, window_start, window_end, lot_ids, trigger_vin) -> list[str]` via aiosql `window.sql`; always includes the trigger (RF3). `decide`: on AMEND with changed bounds and `vins is None` → recompute. `GET /containments/{id}/preview?window_start&window_end&lot_ids` (viewer) → `{vin_count, vins}`. `GET /containments?state=PROPOSED,ESCALATED` accepts a comma list. `CORSMiddleware` with `ApiSettings.cors_origins: list[str] = ["http://localhost:8080", "http://localhost:4173"]`. Tests (integration): preview count equals a direct SQL count; amend −10 min shrinks `vin_count` and keeps the trigger; comma list returns both states; CORS preflight from the console origin succeeds.

### Task 7: console scaffold
`console/src/`: `main.tsx` (router + QueryClient), `App.tsx` (rail layout), `tokens.css` (palette/type/spacing from the design section), `auth/token.ts` (`getToken/setToken` on `sessionStorage`, `TokenDrawer`), `api/client.ts` (fetch wrapper adding `Authorization`, throws `ApiError{status}`), `api/types.ts` (`Containment`, `AuditRow`, `Preview`). Deps added: `@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono`. Test: `tsc -b` + `vite build` green; Playwright `smoke.spec.ts` step 1 — open `/`, paste token in drawer, see the queue heading (rest of the spec grows per task).

### Task 8: `/queue`
Table of PROPOSED + ESCALATED: age, expiry bar (`proposed_at → expires_at`), kind, station, VIN count, confidence; poll 5 s (`refetchInterval`); row → `/case/:id`. Empty state: "Nothing waiting. Failures that need a decision appear here." Playwright: the seeded golden's row is visible with its station id.

### Task 9: `/case/:id`
Header: kind, station, big VIN count, state badge, "Decide" (disabled with the reason when role is `viewer` — RF4, role read from the JWT payload client-side; the api still enforces). Tabs: **Order** (draft text), **Window** (SVG timeline: window, sibling ticks, onset), **Siblings** (by shift / by lot tables), **Path** (genealogy visits, OOT rows marked), **Bench**, **Vehicles** (VIN list, mono). Playwright: tabs render; viewer token shows the disabled decide.

### Task 10: `/case/:id/decide`
Form: action radio (Approve / Amend / Reject), window pickers + lot multiselect (enabled on Amend), reason (required for Amend/Reject). Right: live preview — `GET …/preview` on bound change (debounced 300 ms), big VIN count with "was N". Submit → `POST approve|amend|reject` → navigate to case; 409 → "Already decided by X" from the row. Playwright (the checklist smoke): amend window −10 min → submit → case shows `COMMITTED` and the smaller count.

### Task 11: `/audit`
From `GET /audit`: agreement rate (APPROVE / decided), widened vs narrowed (from `diff.window_*`), latency p50/p95 (`latency_total_ms`), cost per triage; table of the last 50 rows. Pure functions in `audit/stats.ts`; one Playwright assertion checks the numbers after the seeded run's decision (weight 1 — no unit-test runner added to the console).

### Task 12: `qgate-eval serve` + CI console job
`qgate_eval serve --golden drift-05 --port 8000`: throwaway Postgres, load golden, run triage to the gate, `uvicorn` the api app; prints the approver and viewer tokens. Playwright `webServer`: `[qgate-eval serve, vite preview --port 4173]`, `VITE_API_BASE_URL=http://localhost:8000`. CI `console` job: `npm ci`, `npm run build`, `npx playwright install --with-deps chromium`, `npm run test:e2e`. `make console-e2e` locally.

### Task 13: `qgate-gen export`
`export --scenario --out path.jsonl`: one line per event in takt order `{"topic","key","ts_ms","avro_hex"}` using `avro.to_avro` and `kafka.TOPIC/key_of`. Test (unit): round-trip — every line decodes with `from_avro` to the original record; lines are non-decreasing in `ts_ms`.

### Task 14: line-sim core (C++, Catch2)
`scheduler.hpp`: `emit_offset(sim_ms_since_first, speed)`; `speed == 0` → 0 ms; schedule is absolute (offset of event *n* does not depend on earlier sleeps). `manifest.hpp`: `Event{topic, key, ts_ms, value}`; `read_manifest(std::istream&) -> std::vector<Event>` with `from_hex`; malformed line → `std::runtime_error` naming the line number. `wire.hpp`: `frame(schema_id, avro) -> std::string` (`0x00` + big-endian id + bytes). Tests: offset math incl. speed 0 and monotonicity; manifest parses a two-line sample and rejects odd-length hex; frame bytes exact. Dockerfile build stage adds `librdkafka-dev nlohmann-json3-dev libcpp-httplib-dev`.

### Task 15: line-sim producer + metrics + compose
`registry.hpp`: `register_schema(base_url, subject, avsc_text) -> int` (POST `/subjects/{s}/versions`, cpp-httplib client; idempotent by registry semantics). `main.cpp`: args `--file --brokers --registry --schemas --speed --metrics-port`; per-topic schema id; `rd_kafka_producev` with key + framed value; delivery-report callback increments `line_sim_events_total{topic}`/`line_sim_errors_total`; metrics served by a cpp-httplib server thread; SIGTERM/SIGINT → stop scheduling, `rd_kafka_flush(30 s)`, exit 0 (RF5). Compose: `gen` one-shot service (python image, `PACKAGE=qgate-generator`, `ENTRYPOINT=qgate-gen`) shares volume `sim-data` with `line-sim`; `make demo` = `gen export` → `line-sim` at `REPLAY_SPEED`. Verification (manual, recorded in the commit): `make up-infra && make demo SPEED=0` → Postgres fact counts equal the export's line counts per topic; `docker kill -s TERM` mid-run → clean exit, counter == acked.

### Task 16: Gate 4
ADR-011 (C++ replays an exported stream), ADR-012 (commit retry loop and breaker), checklist ticks, RUNBOOK "run the demo from the console" section, `README` gate screenshot placeholder replaced by the real one, CI green (incl. the new `console` job), `make chaos-test` passing on a local `make chaos` stack, merge to `main`.
