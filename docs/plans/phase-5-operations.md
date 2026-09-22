# Phase 5 — Operations Implementation Plan

> Execute with `executing-plans` (inline). TDD per task. Ponytail active.

**Goal:** The running system explains itself — spans per node and tool in Langfuse, the §11 metrics in Prometheus, one Grafana dashboard, a load test with published p50/p95/p99 and n — and the evaluation publishes itself: a Prefect flow runs the goldens live, a manual `nightly` run deploys the numbers to GitHub Pages, a version tag ships multi-arch images with SBOMs, and every image is pinned by digest.

**Architecture:** Instrumentation lives in `qgate_core` (`metrics.py`, `otel.py`, `logs.py`) and is wired at the three places that already know the timings: the agent's node wrapper and `_ask`, the api's decision path, and ingest's handler. Traces go OTLP/HTTP straight to Langfuse's `/api/public/otel` with basic auth (no Langfuse SDK). The nightly pipeline is three thin Prefect flows over code that already exists (`qgate-eval`'s runner, the `gen`/`line-sim` images); it runs against a dedicated `eval-db` so it never truncates the demo data. Pages publishes via `actions/deploy-pages`, so no bot commits.

**Tech Stack:** prometheus_client, opentelemetry-sdk + otlp-proto-http (already dependencies), Langfuse v3 self-hosted, Grafana 11 provisioning, k6 (`grafana/k6` image), Prefect 3 + docker SDK, GitHub Pages (Actions source), buildx SBOM/provenance.

**Spec:** design §11, §12 (supply chain), §13 (`release.yml`, `nightly.yml`), §14, §16; checklist §Phase 5.

## Global Constraints

- Metric names are the §11 contract verbatim; the dashboard may reference nothing else (a test enforces it).
- No Langfuse SDK: OTel SDK only, so a different trace sink is a URL change. The unused `langfuse` dependency is removed.
- Nightly stays `workflow_dispatch` only (owner's call); each run is real provider spend.
- Nothing the eval pipeline does may touch the core stack's fact tables.
- Every `image:` and `FROM` carries a digest by the end of the phase.
- Docstrings PEP 257; dashboards and flows are code, reviewed like code.

## Rulings taken while planning

- **Langfuse v3 stack (6 containers) in `obs`**, because the design's OTLP route needs it and the spec names Langfuse three times. Cost if wrong: `make up-all` is ~2 GB heavier; `make up` is untouched. `LANGFUSE_INIT_*` provisions the existing keys, so CI starts from an empty volume with the same credentials.
- **`eval-db` service** rather than testcontainers-in-worker for the flows: one more Postgres in the `eval` profile, migrated by the flow. Cost if wrong: two Postgres containers in `make up-all`.
- **`gate_pending` is a collector that counts on scrape**, not a gauge set on every transition: exact across processes for one `select count(*)`.
- **Consumer lag from Redpanda** (`enable_consumer_group_metrics`), not computed in ingest — the broker already knows.
- **Pages via `actions/deploy-pages`**; `publish_report` renders a static `eval/site/` (no Markdown library; the numbers are a table). README numbers are updated by hand in Phase 6 with a date; no nightly commits to `main`.
- **Load test measures the non-LLM path** (`LLM_MODE=replay`, one golden, repeated triggers) and says so; the live model's latency is quoted from the recorded run. Cost if wrong: p95 under load excludes the model; the eval report carries the model's own number.
- **Grafana screenshot by Playwright**, not the image renderer plugin (one more container for one PNG).
- **Air-gapped profile is wired, not exercised** — the owner installs Ollama later; README says "not exercised" until then.

## Review Focus

1. Tracing configured without Langfuse keys (the default `.env.example`) must be a silent no-op — no export errors in every service's log → Task 2 test.
2. A dashboard panel referencing a metric nobody emits shows "No data" forever; the contract test must fail on an unknown name → Task 3 test.
3. The nightly flow must not truncate the core stack's fact tables (it uses `eval-db`); a wrong `DATABASE_URL` would silently wipe the demo → Task 5 test asserts the flow refuses a URL that is not `eval-db`.
4. The k6 burst (50 VUs) must not leave `gate_pending` growing forever: every triggered triage reaches a terminal state or the gate → Task 4 assertion.
5. A tag like `v0.1.0-rc1` must produce a **pre-release**, never a "latest" release → Task 7 (`prerelease` from the tag).

---

### Task 1: Metrics with the §11 names
`qgate_core/metrics.py`: `TRIAGE_DURATION` (`triage_duration_seconds{phase}`, buckets 0.1…60), `TRIAGE_OUTCOMES`, `GATE_DECISION_SECONDS`, `GATE_DECISIONS`, `LLM_TOKENS{kind,prompt_id}`, `LLM_COST_USD`, `MES_REQUESTS{status}`, `MES_BREAKER_STATE{state}`, `INGEST_RECORDS{topic,result}`, `GENEALOGY_QUERY_SECONDS`; `gate_pending_collector(count: Callable[[], int])` registers a custom collector. Wire: agent `report` (durations, outcomes, tokens, cost), `tools/mes.py` (requests, breaker state on transitions), `tools/sql.py` genealogy timing; api `decide`/`sweep` (decision seconds, decisions incl. EXPIRED) and the pending collector over `store`; ingest `handle` (ok/dlq). Redpanda: `--set redpanda.enable_consumer_group_metrics=["group","partition","consumer_lag"]`. Tests: unit — scrape text after a fake run contains each name; api integration — `gate_pending` equals the PROPOSED count; ingest unit — a DLQ'd message increments `result="dlq"`.

### Task 2: Spans and JSON logs
`qgate_core/otel.py`: `configure(service: str) -> None` builds a `TracerProvider` with an OTLP/HTTP exporter to `OTEL_EXPORTER_OTLP_ENDPOINT` and `Authorization: Basic base64(pk:sk)` from `LANGFUSE_PUBLIC_KEY/SECRET_KEY`; **no keys → no exporter** (RF1); `span(name, **attrs)` context manager. Agent: `_timed` opens `node.<name>` with `thread_id`, `golden_id`; `_ask` opens `llm.<prompt_id>` with `prompt_version`, token counts; the five tools open `tool.<name>`. api: `api.decide` with `containment_id`, `decision`. `qgate_core/logs.py`: `configure_logging()` — one-line JSON records with `trace_id` from the current span; every `main()` calls it. Compose: Langfuse v3 (`langfuse-web`, `langfuse-worker`, `clickhouse`, `minio`, `redis`, existing `langfuse-db`) pinned, `LANGFUSE_INIT_*` from `.env`; `OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-web:3000/api/public/otel`. Drop `langfuse` from `services/agent/pyproject.toml`. Tests: unit with `InMemorySpanExporter` — a fake-triage run yields `node.intake` … `node.report` and `llm.hypothesise` spans with the attributes; without keys `configure` installs no exporter; a log line is valid JSON carrying the active span's `trace_id`. Manual: `make up-all`, one triage, `GET /api/public/traces` on Langfuse shows it (recorded in the commit).

### Task 3: The dashboard
`observability/grafana/dashboards/qgate.json` (uid `qgate`): throughput & lag (ingest rate, `redpanda_kafka_consumer_group_lag_max`), triage latency p50/p95/p99 by phase, gate queue depth & decision time, outcomes by kind, cost per triage, MES requests & breaker state, error rate, SLO burn (`triage_duration_seconds` p95 < 30 s non-LLM, gate durability = decisions / outcomes). Test (unit): every metric name in every panel `expr` is in `qgate_core.metrics.NAMES` or the allowed external set (`redpanda_`, `process_`, `up`) (RF2). Playwright snapshot of the loaded dashboard → `docs/img/dashboard.png`.

### Task 4: Load test
`loadtest/triage.js`: stage 5 VUs × 2 min, burst 50 VUs × 30 s, 5 VUs × 1 min; each iteration `POST /triage` for the loaded golden's VIN then polls `GET /containments?state=PROPOSED,ESCALATED` for its `thread_id` — custom Trend `triage_to_proposal_ms`; thresholds `p(95)<30000`. Compose `k6` service (`load` profile) writing `eval/load.json`; `make load` loads golden `drift-05` into the core stack, runs it against `api` with `LLM_MODE=replay`. After the run: `gate_pending` equals proposals awaiting decision and nothing is `RUNNING` (RF4) — asserted by the Make target. `docs/latency.md`: boundaries (what each phase measures), the method, the numbers with n and the consumer lag observed, the live-model figure from the recorded run, labelled.

### Task 5: Prefect flows
`pipelines/flows/replay_scenario.py`: tasks `export_manifest` (runs the `gen` image via docker SDK), `run_line_sim`, `wait_for_lag_zero` (Redpanda admin `/v1/consumer_groups`), `assert_counts`; Markdown artifact. `nightly_eval.py`: `prepare_eval_db` (refuses any URL whose host is not `eval-db` — RF3; applies migrations, seeds dims), one `run_case` task per golden (wraps `qgate_eval.runner.run_golden` on an in-process `Stack`), `score_and_write` (`eval/report.md`, `eval/metrics.json`). `publish_report.py`: renders `eval/site/index.html` (metrics table, per-family table, links to report/baseline/dashboard JSON) — pure function `render_site(metrics) -> str`. `qgate-pipelines` depends on `qgate-eval`; `eval-db` service; `prefect.yaml` deployments without schedules; a `prefect-deploy` one-shot registers them. Tests: unit for `render_site` and the `eval-db` guard; `make flows-local` runs `replay-scenario` and `nightly-eval` in replay mode end to end on the local stack (recorded).

### Task 6: `nightly.yml` and Pages
Jobs: `eval-live` — `up` the `eval` profile only, `prefect deploy --all`, run `nightly-eval` (mode live) with `--watch`, run `publish-report`, `actions/upload-pages-artifact` from `eval/site`, artifacts; `deploy` — `actions/deploy-pages` (`permissions: pages: write, id-token: write`). Triggered by hand once → the site is live at the Pages URL; `README` links it. `make down` always.

### Task 7: Release dry run
`release.yml`: matrix with `context`/`dockerfile`/`build-args` per service (shared `docker/python.Dockerfile` for the six Python images, `services/line-sim/Dockerfile`, `console/Dockerfile`), `prerelease: ${{ contains(github.ref_name, '-') }}` (RF5), release notes carry `eval/report.md` and `baseline.json`. Tag `v0.1.0-rc1` → eight multi-arch images with SBOM + provenance on GHCR, one pre-release. Note for the owner: flip packages to public.

### Task 8: Air-gapped profile, wired
`AgentSettings.ollama_base_url`; `LangChainModel` passes `base_url` when provider is `ollama`; compose `airgap` profile sets `LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:7b OLLAMA_BASE_URL=http://host.docker.internal:11434` (native Ollama uses the GPU; 7b fits 6 GB). Unit test: provider `ollama` builds a `ChatOllama` with that base URL, no network. README row: "wired; not exercised until Ollama is installed".

### Task 9: Pin images by digest
Every `image:` in compose and every `FROM` in the Dockerfiles → `name:tag@sha256:…` (`docker buildx imagetools inspect`). Test (unit): a scan of `docker-compose.yml` and `**/Dockerfile` finds no un-pinned reference. Dependabot's docker ecosystem keeps them current.

### Task 10: Gate 5
ADR-013 (traces to Langfuse over OTLP; the v3 stack is the price), checklist ticks, `observability/README.md` and RUNBOOK §6 (lag panel), CI green, `nightly` run once by hand and the page live, dashboard screenshot committed, merge.
