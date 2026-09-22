# Build checklist — dependency-ordered

Work top to bottom. Every item lists what it unblocks (`→`) or what it needs (`needs`). Nothing below an unchecked item should be started if it names that item. Tick the box in the commit that completes it.

Legend: **[P]** prerequisite · **[B]** currently a CI/`make` blocker · **[F]** feature · **[G]** phase gate (exit criterion)

---

## 0. Prerequisites — machine and accounts

### 0.1 Local tooling (Windows host; everything else runs in Docker)

- [x] **[P]** Git ≥ 2.40 — present (2.55)
- [x] **[P]** Docker Desktop with Compose v2 and BuildKit — present (29.7)
- [x] **[P]** Node 20 LTS + npm — present (24.14; fine)
- [x] **[P]** `uv` — `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` → `uv --version` → needed by `make install`, `uv lock`, every Dockerfile's `--frozen` — present (0.12.17)
- [x] **[P]** `pre-commit` — `uv tool install pre-commit` then `pre-commit install` in the repo → hooks (ruff, gitleaks) run on every commit — present (4.6.2), hooks installed
- [x] **[P]** `gitleaks`, `trivy` CLIs (optional locally; CI has them) — `winget install Gitleaks.Gitleaks` / `winget install AquaSecurity.Trivy` → `make scan` — present (8.30.1 / 0.74.0)
- [x] **[P]** `make` — Git Bash lacks it by default: `winget install ezwinports.make` → every `make` target — present (4.4.1)
- [x] **[P]** `cp .env.example .env` and set `POSTGRES_PASSWORD` → `make up`

### 0.2 Accounts and secrets

- [x] **[P]** LLM provider account and API key (OpenAI or Anthropic; you chose provider-agnostic, so pick the one cassettes will be recorded against) → Phase 3 `LLM_MODE=record`
- [x] **[P]** GitHub → repo *Settings › Actions › General*: allow Actions; *Workflow permissions* = read+write → `release.yml` can push to GHCR, `nightly.yml` can push `gh-pages`
- [x] **[P]** GitHub → *Settings › Secrets and variables › Actions*: secrets `LLM_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`; variables `LLM_PROVIDER`, `LLM_MODEL` → `nightly.yml`
- [ ] **[P]** GitHub → *Settings › Pages*: source = `gh-pages` branch → published metrics page (Phase 5)
- [x] **[P]** GitHub → Dependabot enabled (already configured by `.github/dependabot.yml`; confirm in *Security*)
- [x] **[P]** Langfuse: self-hosted via compose `obs` profile → create project on first `make up-all`, copy keys to `.env`
- [x] **[P]** *(optional)* Devin CLI `devin auth login` → `devin plugins install obra/superpowers` → planning/TDD skills in-session

### 0.3 Read before Phase 0

- [x] **[P]** `docs/design/2026-09-21-architecture.md` — the contract every task below implements
- [x] **[P]** `docs/adr/0001`–`0004` — the four decisions no task may violate

---

## Phase 0 — CI green on an empty project

Today `ci.yml` fails on the first push because several `make` targets have nothing to run against. Fix these first so every later commit has a working red/green signal.

- [x] **[B]** `uv lock` at repo root → commits `uv.lock` → every Dockerfile (`uv sync --frozen`), `make install`, `unit`, `typecheck`
- [x] **[B]** `cd console && npm install` → commits `package-lock.json` → `console/Dockerfile` (`npm ci`), `lint` job
- [x] **[B]** `console/src/main.tsx` + `App.tsx` rendering "qgate console" → `npm run build` succeeds → `console` image builds
- [x] **[B]** One `@pytest.mark.unit` smoke test per package (imports the package) → `make unit` no longer exits 5 ("no tests collected")
- [x] **[B]** `make contract` / `make integration` tolerate zero tests: append `|| [ $? -eq 5 ]` in the Makefile or add a skipped placeholder test → `contract`, `integration` jobs
- [x] **[B]** `services/line-sim/src/{main,scheduler,producer,scenario_reader}.cpp` + headers and `tests/test_{scheduler,scenario_reader}.cpp` as compiling stubs (one trivial Catch2 assertion) → `line-sim` image builds, `ctest` passes; **needs** nothing but takes the longest (vcpkg first build ≈ 15–25 min) — start it early
- [x] **[B]** `eval/harness/qgate_eval/cli.py` with `run --mode --baseline` that exits 0 when `eval/goldens` has no case files → `eval-replay` job
- [x] **[B]** Console-script entrypoints exist so images start: `qgate_ingest.main:main`, `qgate_detect.cli:app`, `qgate_agent.main:main`, `qgate_api.main:main`, `qgate_mock_mes.main:main` — each serves `/health` and `/metrics` only → `make up` health checks pass
- [x] **[B]** `db/migrations/0001_dims.sql` (even if just `CREATE SCHEMA qgate`) → `migrate` container completes → everything `depends_on: migrate`
- [x] **[F]** `make up-infra` target (redpanda, postgres, migrate only) → lets Phase 1 run without product images
- [x] **[F]** `Makefile`: `unit` target skips `line-sim-test` when `SKIP_CPP=1` → fast local loop while C++ is stubbed
- [x] **[F]** ADR-005 monorepo/uv, ADR-006 provider-agnostic LLM + cassettes → index in `docs/adr/README.md`
- [x] **[F]** `pre-commit run --all-files` clean → hooks enforce style from here on
- [x] **[G]** **Gate 0:** `make up-infra` brings up infra; `make lint typecheck unit` pass locally; CI green on `main` (run 8aaa74a, 7/7 jobs)

---

## Phase 1 — Data spine

Order matters: station ids come from `line.yaml`; everything else references them.

### 1.1 Line model and generator

- [x] **[F]** `scenarios/line.yaml`: 30 stations with sequence, takt seconds, 1–3 characteristics each (nominal, limits, unit), 3 shifts, 3 benches (repeatability σ, bias) → station/characteristic ids used by fault map, goldens, migrations seed
- [x] **[F]** `qgate_core/models/`: `Vin`, `Station`, `Characteristic`, `Shift`, `Bench`, `BuildEvent`, `Measurement`, `EolResult`, `Containment*` Pydantic models mirroring the Avro schemas → shared by generator, ingest, agent, api
- [x] **[F]** `qgate_generator/line.py` `LineModel.from_yaml` + VIN sequence generator (deterministic from seed) → all scenarios
- [x] **[F]** `qgate_generator/stream.py`: ordered event stream at takt (build event → measurements → EOL result per vehicle), `repeat_no > 1` on a 5 % sample → producers, ground truth
- [x] **[F]** Scenarios, each with ground truth (`defective_vins`, `bench_fault`): `clean_baseline` → `tool_wear` → `shift_step` → `bad_lot` → `correlated_noise` → `bench_drift` → `overlap` (in this order; `overlap` composes `bad_lot` + `tool_wear`) → goldens, eval scoring
- [x] **[F]** `hypothesis` tests: same seed → identical stream; ground truth ⊆ emitted VINs; bench_drift has zero truly defective VINs → `make unit`
- [x] **[F]** `qgate-gen replay --scenario --speed --seed --bootstrap` Python producer using `qgate_core.avro` + `qgate_core.kafka` → **the** producer until Phase 4 replaces it with C++

### 1.2 Contracts live

- [x] **[F]** `qgate_core/avro.py`: load `schemas/*.avsc`, register on start (`BACKWARD`), Confluent wire-format (de)serialisers → producer, ingest, detect-worker, agent consumer
- [x] **[F]** Topic creation with partitions 6/3 on first start (rpk in `migrate`-style one-shot or producer startup) → ordering guarantees per ADR-002
- [x] **[F]** Contract test: register `line.measurements.v2` with one added defaulted field; v1 consumer still decodes → `make contract`

### 1.3 Storage

- [x] **[F]** `0001_dims.sql` full, `0002_facts.sql` (partitioned `fact_measurement`, generated `deviation`/`out_of_tolerance`, all indexes), `0003_containment.sql`, `0004_roles.sql` (five roles + GRANTs) → ingest, tools, api; **needs** `line.yaml` ids for the dim seed
- [x] **[F]** Dim seed loader (`qgate-gen seed-dims --db`) from `line.yaml` → ingest FKs resolve
- [x] **[F]** `qgate_ingest`: consumer group `ingest` on three topics, Avro decode, Pydantic validate, idempotent upsert (`ON CONFLICT DO NOTHING` on natural keys), DLQ on failure, commit after write, `/health` `/metrics` → Postgres has genealogy
- [x] **[F]** Integration test (testcontainers): produce 100 vehicles → rows match; replay same stream → no duplicates; poison message → one DLQ record → `make integration`
- [x] **[F]** `db/queries/genealogy.sql` + `EXPLAIN ANALYZE` benchmark test at 5 M rows (`pytest -m integration --benchmark`) asserting p95 < 50 ms → `get_vehicle_genealogy`
- [x] **[F]** ADR-010 dbmate over ORM

### 1.4 Goldens — before any agent code

- [x] **[F]** `knowledge/fault_map.yaml`: ~10 fault codes → candidate stations, all ids from `line.yaml` → `hypothesise`; **needs** 1.1 line.yaml
- [x] **[F]** `qgate-gen goldens-candidates --scenario` prints failing VINs with ground-truth context so you can pick trigger VINs → authoring
- [x] **[F]** 50 golden YAMLs (`isolated` 12, `drift` 12, `lot` 8, `bench` 8, `contradictory` 6, `overlap` 4) with expected decision, bounds, tolerance, human action → eval harness
- [x] **[F]** Golden schema validator test (`pytest -m unit`): every file parses, families count to 50, referenced scenario/station ids exist → protects the set
- [x] **[G]** **Gate 1:** any VIN's full build path from the DB in < 50 ms p95; `git tag goldens-v1` pushed; CI green

---

## Phase 2 — Detect and deterministic tools (no LLM)

- [x] **[F]** `qgate_detect/spc.py`: Western Electric rules 1–4, EWMA λ=0.2, unit-tested on synthetic series → worker
- [x] **[F]** `qgate_detect/changepoint.py`: PELT (`ruptures`, rbf, BIC penalty) + CUSUM cross-check → `estimated_onset`; deterministic test on `tool_wear` and `shift_step` ground truth (onset within ±15 takts) → `/drift`, `bound`
- [x] **[F]** `qgate_detect/msa.py`: `%GRR` from `repeat_no > 1`, bias, `capable = grr < 30`; test: `bench_drift` → incapable, `clean_baseline` → capable → `/bench/{id}/capability`; `docs/metrology.md` with formula + assumption label
- [x] **[F]** `detect api`: `/drift`, `/bench/{id}/capability`, `/stations/{id}/alerts` over `DETECT_RO` → agent tool `check_station_drift`
- [x] **[F]** `detect worker`: consumer on `line.measurements`, ring buffers rebuilt from Postgres on start, emits `quality.alerts` keyed by station → dashboard, console alerts tab
- [x] **[F]** ADR-009 two processes from one image
- [x] **[F]** `db/queries/{station,correlate,window}.sql` + tests against fixture DB (each under budget) → tools
- [x] **[F]** `qgate_agent/tools/`: `get_vehicle_genealogy`, `get_station_spec`, `find_correlated_failures`, `check_station_drift`, `estimate_containment_window` as plain typed functions on `AGENT_RO` + `DETECT_BASE_URL`; no LangGraph yet → graph nodes
- [x] **[F]** `qgate_mock_mes`: server validated against `openapi.yaml` (idempotent `POST /v1/holds`, 409 on conflicting body, API key, `/_chaos`, `/_stats`) → `commit` node; **needs** nothing else — can be built in parallel with detect
- [x] **[F]** Contract tests: `schemathesis` against `mock-mes` OpenAPI → `make contract`
- [x] **[G]** **Gate 2** (CI f9cccf1 7/7, goldens-v1.1)**:** `pytest -m eval_tools` — for every golden, tools alone return the correct siblings, onset (± tolerance) and bench verdict, with no model in the loop; CI green

---

## Phase 3 — Graph, api, gate, eval

Order is strict here: api endpoints before the gate, gate before commit, cassettes before the CI gate.

### 3.1 api first (the agent depends on it)

- [x] **[F]** `qgate_core/auth.py`: HS256 JWT, `Role` enum, FastAPI dependency; `make token` CLI → api, console, harness
- [x] **[F]** `qgate_api`: `/internal/containments` POST/PATCH (agent-facing, `service` role), containment + audit writes on `API_RW`, `quality.containment` producer → `submit_for_approval`, `report`
- [x] **[F]** `qgate_api`: `GET /containments`, `GET /containments/{id}`, `GET /audit` → console, harness
- [x] **[F]** Contract tests: `schemathesis` against api OpenAPI → `make contract`

### 3.2 Graph, deterministic nodes first

- [x] **[F]** `qgate_agent/state.py` `TriageState`, `Bounds`, `HumanDecision` → all nodes
- [x] **[F]** Nodes with no LLM: `intake`, `genealogy`, `correlate`, `drift_check`, `route`, `bound`, `bench_alert`, `report` — unit-tested with fixture state → graph
- [x] **[F]** `qgate_agent/llm.py`: `init_chat_model` + `CassetteRunnable` (`live|record|replay`; replay-miss = hard failure) → LLM nodes, CI determinism
- [x] **[F]** `prompts/hypothesise.v1.md`, `prompts/compose.v1.md`, `prompts/escalate.v1.md` with front-matter `id`/`version` → cassette keys
- [x] **[F]** LLM nodes: `hypothesise` (structured `list[Hypothesis]`, validator rejects stations not in fault map), `compose` (validator: bounds quoted verbatim), `escalate` → graph
- [x] **[F]** `graph.py`: nodes + conditional edges + `PostgresSaver` on `CHECKPOINT_RW`; `.setup()` on start → gate

### 3.3 Gate and commit

- [x] **[F]** `gate` node: `submit_for_approval` → `api POST /internal/containments` → `interrupt(payload)` → the design's one sentence
- [x] **[F]** `commit` node: `mock-mes POST /v1/holds` with `Idempotency-Key = containment_id` → `api PATCH … COMMITTED` → audit
- [x] **[F]** `qgate_agent/http.py`: `POST /triage`, `GET /threads/{id}`, `POST /threads/{id}/resume` → api decision endpoints
- [x] **[F]** `qgate_agent/consumer.py`: group `agent-triage` on `line.eol.results`, `FAIL` only, starts a thread with `eol_ts` → event-driven trigger (ADR-007)
- [x] **[F]** `qgate_api`: `POST /containments/{id}/approve|amend|reject` → update row, compute diff, emit event, call agent resume → human path
- [x] **[F]** `qgate_api`: expiry sweeper (`expires_at`, `APPROVAL_TIMEOUT_S`) → `EXPIRED` + `ESCALATED` event + resume with REJECT → no auto-approve, ever
- [x] **[F]** `report` node fills `latency_total/llm/non_llm`, tokens, `cost_usd` (`qgate_core/pricing.py`, labelled assumptions) → metrics table
- [x] **[F]** ADR-007 event-driven + HTTP resume, ADR-008 api owns containment state
- [x] **[F]** Restart-mid-gate integration test: run to `WAITING_GATE`, restart agent container, resume, assert one row + one hold → **the** HITL claim

### 3.4 Evaluation harness

- [x] **[F]** `qgate_eval`: runner (replay scenario → trigger → poll → act as human per golden → collect audit), scorers (escapes, precision, recall, decision match, bound tolerance, abstention correctness), Rich table + `report.md` → numbers
- [x] **[F]** `LLM_MODE=record` over all 50 goldens → commits `eval/cassettes/` (synthetic VINs only) → deterministic CI
- [x] **[F]** First `replay` run → writes `eval/baseline.json` (with `goldens_tag`, `cassette_set`) → CI gate has a reference
- [x] **[F]** `make eval-replay` compares to baseline; fails on escapes ↑ or non-LLM p95 ↑ > 20 % → `eval-replay` job is a real gate
- [x] **[G]** **Gate 3** (curl approve on compose → HOLD-000001; restart mid-gate test; replay baseline; CI 302132b 7/7 with eval gate active)**:** failure event → proposal; approve/amend via `curl`; amendment recorded with diff; kill agent mid-gate loses nothing; CI green with eval gate active

---

## Phase 4 — Console, C++, reliability

Console and C++ are independent of each other; reliability items need Phase 3 commit path.

### 4.1 Console (React weight 1 — keep it to four routes)

- [x] **[F]** `src/api/` typed client (hand-written: the api serves `dict` bodies, so `openapi-typescript` would emit `object`) + `src/auth/` JWT drawer → pages
- [x] **[F]** `/queue` → `/case/:id` (evidence tabs) → `/case/:id/decide` (approve/amend/reject, VIN-count preview via `GET …/preview`; amend re-scopes VINs server-side and keeps the trigger) → `/audit` (agreement, widened/narrowed, latency, cost) — in that order
- [x] **[F]** Playwright smoke: seed one golden (`qgate-eval serve`), amend window −10 min, assert `COMMITTED` → `console` job

### 4.2 line-sim in C++ (C++ weight 1 — Python fallback stays)

- [x] **[F]** `manifest` reader (ADR-011: replays `qgate-gen export`, not `scenarios/*.yaml` — one source of ground truth); Catch2 tests → scheduler
- [x] **[F]** `scheduler`: simulated offset → emit time ÷ speed; absolute schedule from replay start (no cumulative drift); Catch2 timing invariants → producer
- [x] **[F]** `producer`: librdkafka, Confluent wire-format Avro (body pre-encoded by the generator; C++ frames it) → replaces Python producer in compose (`gen` + `line-sim`, `make demo`); `qgate-gen replay` retained. Verified: 138,624 scheduled = delivered, DLQ empty, Postgres counts = manifest counts; SIGTERM exits 0
- [x] **[F]** `/metrics` counters (`line_sim_events_total{topic}`, `line_sim_scheduled_total`, `line_sim_errors_total`) → dashboard

### 4.3 Reliability

- [x] **[F]** `tenacity` retries + timeouts on the MES commit (5 attempts, jitter, cap 8 s); transport-level connect retries on every `agent → detect/api/mock-mes` client → survives blips
- [x] **[F]** Circuit breaker on `mock-mes`; `COMMIT_PENDING` via `api PATCH` from a `pending` node; `retry_gate` interrupts; api sweeper re-resumes every 30 s (one cadence for expiry and retry) → outage without data loss (ADR-012)
- [x] **[F]** Chaos profile wired (`agent → toxiproxy → mock-mes`, `make chaos`); in-process: lost ack → one hold, `duplicate_replays ≥ 1`; outage → parked → swept → committed; `tests/chaos`: 20 s outage mid-commit, kill agent mid-gate → `make chaos-test`
- [x] **[F]** `/ready` checks real dependencies on every service (api: db+agent; agent: both dbs, detect, api; detect: db; ingest/worker: broker) → compose probes `/ready`
- [x] **[G]** **Gate 4** (RUNBOOK §0 walks the demo from the console; `make chaos-test` 2/2 on real containers, twice; PR #25 CI 8/8 incl. the new `console` job)**:** shift leader runs the demo without a terminal; chaos suite passes; CI green

---

## Phase 5 — Operations

- [x] **[F]** `qgate_core/otel.py`: spans per node/tool/model call → Langfuse OTLP (ADR-013; Langfuse v3 stack, `LANGFUSE_INIT_*` provisions the keys); `qgate_core/metrics.py`: the §11 names, emitted by agent/api/ingest; `kafka_consumer_lag` as a recording rule; JSON logs with `trace_id` → latency methodology
- [x] **[F]** `observability/grafana/dashboards/qgate.json`: 15 panels — throughput/lag, triage latency by phase, gate queue/decision time/decisions, outcomes, cost, MES breaker, error shares, SLO burn; contract test on metric names → README screenshot (`docs/img/dashboard.png`)
- [x] **[F]** Load test (`k6`, `make load`): 5 concurrent / 50 burst, agent in replay mode; n = 1 090, 0 failures: trigger→proposal p50 518 ms / p95 3.6 s / p99 4.3 s; live-model share from 264 real triages p50 3.9 s / p95 5.7 s → `docs/latency.md`
- [x] **[F]** Prefect flows: `replay_scenario` (gen + line-sim over the Docker socket, exact lag wait, count assertion) → `nightly_eval` (fifty goldens over `eval-db`, one task per case) → `publish_report` (`eval/site`); `prefect.yaml` deploys, pool `qgate`, all three ran locally → orchestration row
- [x] **[F]** `nightly.yml` on demand (owner's call: each run is provider spend) → `actions/deploy-pages` from `eval/site`; Pages source = GitHub Actions
- [x] **[F]** `release.yml` dry run on tag `v0.1.0-rc1`: nine multi-arch images with SBOM + provenance on GHCR, pre-release → Docker/CI rows
- [x] **[F]** Air-gapped profile **wired, not exercised**: `agent-airgap` on a native Ollama (`qwen2.5:7b` fits the 6 GB GPU), `LLM_BASE_URL`; README says so until Ollama is installed
- [x] **[F]** Every `image:` and `FROM` pinned by digest (unit test); Dependabot `docker-compose` ecosystem bumps them → supply-chain claim
- [ ] **[G]** **Gate 5:** nightly publishes without a human; dashboard shows the load test

---

## Phase 6 — Ship

- [ ] **[F]** `README.md` per design §14: problem → metrics table (dated) → diagram → one command → gate screenshot → artefact links → ROI → runbook/ADR index
- [ ] **[F]** `RUNBOOK.md` sections 1–8 written for the shift leader
- [ ] **[F]** `docs/roi.md`: assumptions table, break-even agreement rate, sensitivity on escape cost — every figure labelled
- [ ] **[F]** `infra/k3s/` kustomize, exercised once on a single-node VM; README says exactly that
- [ ] **[F]** Fresh clone on a different machine: `git clone && make up && make demo` → the README is true
- [ ] **[F]** Skill-coverage table ticked against real artefacts; anything unticked removed from CV claims
- [ ] **[F]** Tag `v1.0.0`; release notes carry `eval/report.md`
- [ ] **[G]** **Gate 6:** a stranger clones, runs one command, sees it work — and every claimed skill has a link

---

## Standing rules (apply to every item)

- Tests first where a test is possible; a deterministic component has no excuse.
- One item per commit where practical; conventional commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
- If an item slips, slip the date, not the gate. Permitted cuts: C++ → Python, console → queue + approve only, Ollama profile. **Never cut:** goldens, checkpointer, chaos test, audit table.
- Nothing in the repo names an employer. `private/` stays local.
