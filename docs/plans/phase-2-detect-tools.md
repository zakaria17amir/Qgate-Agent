# Phase 2 — Detect and Deterministic Tools Implementation Plan

> Execute with `executing-plans` (inline). TDD per task. Ponytail active.

**Goal:** With no language model anywhere, the deterministic parts of the triage — genealogy, correlation, drift onset, bench capability, window/lot bounding — return the correct answer for every one of the fifty goldens.

**Architecture:** `detect` gains three pure modules (`spc`, `changepoint`, `msa`) exposed over HTTP and, for rule violations, a Kafka worker. The agent's five read-only tools are plain typed functions over `agent_ro` SQL and `detect` HTTP — no LangGraph yet. `mock-mes` becomes a real server validated against its OpenAPI contract. A `slow` test loads each golden's run into Postgres with `COPY` and asserts the tool outputs.

**Tech Stack:** numpy, ruptures (PELT), FastAPI, httpx, aiosql, psycopg COPY, schemathesis.

**Spec:** `docs/design/2026-09-21-architecture.md` §6.4, §6.5, §8 (tools), §10; checklist §Phase 2.

## Global Constraints

- Everything in this phase is deterministic given the data. No randomness at inference time.
- Deviations are expressed in **half-tolerance units** (`(value − nominal) / half_tol`) so thresholds are unit-free and comparable across characteristics.
- Statistical claims stay honest: every verdict carries the evidence it was computed from (n, effect size), and thresholds are named constants with the assumption written next to them.
- Python docstrings PEP 257 / Google style; SQL one-line header per query.

## Rulings taken while planning

- **Bench verdict uses bias-vs-peers, not only %GRR.** A drifting bench keeps its repeatability; its *bias* moves. Benches rotate per vehicle, so the three EOL benches see the same population and a between-bench mean comparison is a valid bias estimate without a reference standard. `%GRR` is still computed from repeats and still gates capability. Cost if wrong: a plant with one bench needs a reference-part check instead — documented in `docs/metrology.md`.
- **Drift onset = earliest plausibly-defective point**, not the change point. For a ramp, PELT finds where the *mean* shifted; containment needs where parts *started failing*. Onset for `DRIFT` is where the fitted post-change ramp plus 2σ of residuals crosses the tolerance limit (clamped to the change point). For `STEP`, onset is the change point. Cost if wrong: goldens use ±15 takts; the Gate 2 test measures the actual error.
- **Worker emits `RULE_VIOLATION` only.** DRIFT/STEP with onset come from `/drift` on demand (the agent asks with a window). One algorithm, one place. Cost if wrong: alerts arrive later than a streaming change-point would give — acceptable, the agent is triggered by the EOL fail anyway.
- **`COPY`-based loader** (`qgate-gen load`) bypasses Kafka to fill Postgres in seconds; used by the Gate 2 test and useful for demos. Ingest stays the production path.
- **Tools live in `services/agent/src/qgate_agent/tools/`** as functions taking a connection/client, so Phase 3 wraps them as LangGraph tools without changing them.

## Review Focus

1. A `/drift` request over a window with fewer than ~30 points must return `NONE` with `n` in evidence, never a spurious change point → Task 2.
2. A bench with no repeat measurements in the window must report `grr_pct: null` and rely on bias-vs-peers, not crash or claim capability → Task 3.
3. `find_correlated_failures` must scope siblings to vehicles that **passed the suspect station**, not any vehicle with the code → Task 6.
4. `estimate_containment_window` by lot must return only carriers of that lot at that station, not every vehicle in the lot's time span → Task 6.
5. `mock-mes` must return `200` (not `201`) on an identical replay and `409` on a same-key different-body replay → Task 7.

---

### Task 1: SPC rules and EWMA (`qgate_detect/spc.py`)

Produces: `western_electric(z: ndarray) -> list[Violation]` (rules 1–4 on standardised deviations), `ewma(z, lam=0.2, L=3.0) -> ndarray[bool]` (breach mask). `Violation(rule: int, index: int)`.
Tests: rule 1 fires on a single |z|>3; rule 2 on 2 of 3 beyond 2σ; rule 3 on 4 of 5 beyond 1σ; rule 4 on 8 in a row same side; EWMA breaches on a 1σ step within ~10 points and stays quiet on white noise (seeded).

### Task 2: Change-point onset (`qgate_detect/changepoint.py`)

Produces: `DriftVerdict(verdict: NONE|DRIFT|STEP, change_index: int|None, onset_index: int|None, severity, method, confidence, evidence: dict)`; `detect_change(dev: ndarray, min_points=30) -> DriftVerdict`.
Method: PELT (`ruptures`, rbf, `pen = log(n) * 3`); CUSUM cross-check (`h = 4σ`); agreement within 20 points → confidence 0.9 else 0.6. Post-segment slope test decides DRIFT vs STEP. Severity from post-mean shift in half-tol units: <0.5 LOW, <1.0 MEDIUM, else HIGH.
Tests: white noise → NONE; step at 700 → STEP, change within ±10; ramp from 800 → DRIFT with onset within ±25 of the first index where ramp + 2σ > 1.0; n<30 → NONE with `evidence.n`.

### Task 3: Gauge capability (`qgate_detect/msa.py`)

Produces: `BenchCapability(bench_id, grr_pct: float|None, repeatability_sigma: float|None, bias_vs_peers: float|None, n_repeats, n_values, capable: bool, threshold_grr_pct=30.0, threshold_bias=0.5, method)`; `capability(repeats: dict[str, list[float]], own: ndarray, peers: ndarray, tol_width) -> BenchCapability`.
`%GRR = 6·σ_gauge / tol_width · 100` with `σ_gauge` pooled within-VIN std of repeats. `bias_vs_peers = mean(own_dev) − mean(peer_dev)` in half-tol units. `capable = (grr is None or grr < 30) and |bias| < 0.5`.
Tests: tight repeats → grr≈6, capable; biased own values → not capable with bias ≈ injected; no repeats → grr None, verdict still computed; `docs/metrology.md` written.

### Task 4: `detect` HTTP + worker

Produces: `GET /drift?station_id&characteristic_id&from&to`, `GET /bench/{bench_id}/capability?characteristic_id&from&to`, `GET /health`; `detect worker` consumes `line.measurements` with per-(station, char) ring buffers (500), emits `QualityAlert(kind=RULE_VIOLATION)` keyed by station.
SQL: `db/queries/detect.sql` — `deviation_series`, `bench_repeats`, `bench_values`.
Tests (integration): load `tool_wear` seed 1 with COPY → `/drift` on ST-19/CH-19-TORQUE returns DRIFT; `/bench/EOL-B2/capability` on `bench_drift` seed 1 → not capable; clean → capable; worker test: produce a 4σ point → one alert on `quality.alerts`.

### Task 5: COPY loader (`qgate_generator/load.py`, `qgate-gen load`)

Produces: `copy_run(conn, run) -> None` using `cursor.copy` into the four fact tables (respecting FK order). Test (integration): `clean_baseline` 200 vehicles loads in < 5 s; counts match; running twice raises on PK conflict — the loader is for empty tables and says so.

### Task 6: Agent tools (`services/agent/src/qgate_agent/tools/`)

Produces (all typed, all read-only):
- `genealogy.py`: `get_vehicle_genealogy(conn, vin) -> Genealogy` (`visits: list[StationVisit]`, `eol: EolSummary|None`, helpers `sequence_no`, `lots_at(station)`).
- `station.py`: `get_station_spec(conn, station_id) -> StationSpec`.
- `correlate.py`: `find_correlated_failures(conn, fault_code, station_id, start, end) -> CorrelationResult` (`vins`, `by_shift: dict`, `by_lot: dict`, `n`, `top_lot_share`).
- `drift.py`: `check_station_drift(client, station_id, characteristic_id, start, end) -> DriftVerdict`; `check_bench(client, bench_id, characteristic_id, start, end) -> BenchCapability`.
- `window.py`: `vins_in_window(conn, station_id, start, end) -> list[str]`, `vins_by_lot(conn, station_id, lot_id) -> list[str]`.
SQL: `db/queries/{station,correlate,window}.sql`.
Tests (integration on a loaded `bad_lot` run): correlation scoped to vehicles that passed the station (RF3); `vins_by_lot` returns only carriers (RF4); shift and lot breakdowns sum to `n`.

### Task 7: `mock-mes` server

Produces: FastAPI implementing `openapi.yaml`: `POST /v1/holds` (Idempotency-Key; 201 / 200 replay / 409 conflict / 401), `GET /v1/holds/{ref}`, `/_chaos` (403 unless `MES_CHAOS=1`), `/_stats`, `/health`. In-memory store (it is a mock; restart = empty plant).
Tests (unit, TestClient): the five status paths; contract test (`schemathesis` against the served schema, marked `contract`).

### Task 8: Gate 2 — tools alone on every golden

`eval/harness/tests/test_tools_on_goldens.py` (slow, integration): for each golden, fresh schema per scenario+seed (truncate facts), `copy_run`, then:
- isolated: `find_correlated_failures` n == 0 and `/drift` NONE at the fault's station.
- drift: `/drift` verdict DRIFT at ST-19 and `|onset_seq − expected.window_start_sequence| ≤ tolerance_takts`.
- lot: `top_lot_share ≥ 0.8` with top lot == expected `lot_ids[0]`; `vins_by_lot` ⊇ trigger.
- bench: `check_bench(trigger.bench)` not capable; the trigger VIN's genealogy shows no upstream OOT.
- contradictory: `/drift` STEP at ST-18 with onset within tolerance of the injected step; siblings n == 0 before the trigger.
- overlap: both the lot condition and the drift condition hold.
Publish the per-family pass table in the test's summary output.

### Task 9: Gate 2 close

ADR-009 (two detect processes), checklist §Phase 2 ticked, CI green, merge.
