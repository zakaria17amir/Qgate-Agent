# Phase 1 — Data Spine Implementation Plan

> **For agentic workers:** Execute with `executing-plans` (inline). Steps use checkbox syntax. TDD per task: test first, watch it fail, minimal code, watch it pass, commit.

**Goal:** From `make up-infra` and one command, a simulated line streams through Kafka into Postgres so that any VIN's full build path is queryable in < 50 ms — and fifty golden cases exist before any agent code.

**Architecture:** `scenarios/line.yaml` is the single source of station/characteristic ids. `qgate_generator` turns a line + a scenario YAML into an ordered event stream with declared ground truth. `qgate_core` owns the Pydantic models mirroring the Avro schemas and the Kafka/registry plumbing. `ingest` consumes, validates, upserts idempotently, DLQs the rest. Migrations are plain SQL; roles are least-privilege.

**Tech Stack:** Python 3.12, Pydantic 2, confluent-kafka (schema registry + Avro), psycopg 3, dbmate, testcontainers, hypothesis, Typer.

**Spec:** `docs/design/2026-09-21-architecture.md` §4–§7, §9, §10; checklist `docs/plans/checklist.md` §Phase 1.

## Global Constraints

- Python 3.12; `ruff` + `mypy --strict` clean; every test marked `unit` or `integration`.
- Avro schemas in `schemas/*.avsc` are the contract; Pydantic models mirror them field-for-field (ADR-002 keys).
- Only synthetic data; no competition datasets (ADR-001).
- Comments: Python docstrings in PEP 257 / Google style; SQL gets a one-line header per object; explain *why*, not *what*.
- Ponytail: stdlib and existing deps first; no abstraction with one implementation.
- Postgres: `text` not `varchar`, `timestamptz`, `bigint generated always as identity`, index every FK, no partitioning below 100M rows.

## Rulings taken while planning

- **No partitioning** of `fact_measurement` (design §7.1 said monthly partitions "to show intent") — Postgres guidance: partition above 100M rows; we hold ~5M. Cost if wrong: one migration later.
- **Scenarios are data, not code.** Design §4 listed `scenarios/` as one module per scenario; instead one `injects.py` interprets five inject kinds from YAML. Seven YAML files, zero scenario modules. Cost if wrong: an inject kind that needs bespoke code gets its own function.
- **Role passwords** are set by a one-shot `roles` compose service (`postgres` image, `psql -v pw=`) from `POSTGRES_PASSWORD`; per-role URLs are composed in `docker-compose.yml`, not `.env`. Removes six copies of a secret from `.env`.
- **Goldens are generated from ground truth** by `qgate-gen goldens` and committed as static YAML. They encode the generator's truth, not the agent's behaviour, so the spec's "write before the agent" intent holds. Regeneration is a deliberate, reviewed commit.
- **Genealogy benchmark** runs at 1M synthetic rows via `generate_series` (≈10 s) and asserts *index scan* + < 50 ms; a 5M-row run is a manual `make bench` target, not CI.
- **Plan granularity:** the executor is the author in the same session; tasks carry interfaces, test intents and DDL/model shapes rather than full code listings.

## Review Focus

1. A scenario YAML referencing a station or characteristic id absent from `line.yaml` must fail loudly at load, not produce a silent stream → Task 3 test.
2. Replaying the same stream twice must not duplicate facts (Kafka at-least-once) → Task 8 test.
3. A message that fails Avro decoding or validation must land in `line.dlq` with the reason and must not stop the consumer → Task 8 test.
4. `bench_drift` ground truth must contain **zero** defective VINs while producing EOL FAILs — otherwise the abstention family is untestable → Task 4 test.
5. `bad_lot` affected VINs must be non-contiguous in sequence — otherwise a window containment would wrongly score as correct → Task 4 test.

---

## File map

| Path | Responsibility |
|---|---|
| `scenarios/line.yaml` | 30 stations, characteristics, shifts, benches, takt |
| `scenarios/{clean_baseline,tool_wear,shift_step,bad_lot,correlated_noise,bench_drift,overlap}.yaml` | Scenario parameters |
| `packages/qgate-core/src/qgate_core/models.py` | Pydantic mirrors of the five Avro records + `Result`, `AlertKind`, `Severity`, `State` enums |
| `packages/qgate-core/src/qgate_core/avro.py` | Load `.avsc`, registry client, `serializer(topic)`, `deserializer(topic)` |
| `packages/qgate-core/src/qgate_core/kafka.py` | `producer()`, `consumer(group, topics)`, `ensure_topics()`, `send_to_dlq()` |
| `packages/qgate-generator/src/qgate_generator/line.py` | `Line` model, `Line.load(path)` |
| `packages/qgate-generator/src/qgate_generator/scenario.py` | `Scenario`, `Inject` models, `Scenario.load(path, line)` with id validation |
| `packages/qgate-generator/src/qgate_generator/stream.py` | `generate(line, scenario) -> Run` (events in takt order + ground truth) |
| `packages/qgate-generator/src/qgate_generator/cli.py` | `qgate-gen replay | truth | seed-dims | goldens` |
| `db/migrations/0001_dims.sql … 0004_roles.sql`, `db/set_role_passwords.sql` | Schema and roles |
| `db/queries/genealogy.sql` | `genealogy_by_vin` |
| `services/ingest/src/qgate_ingest/{main,upsert}.py` | Consumer loop; SQL upserts |
| `knowledge/fault_map.yaml` | Real ids from `line.yaml` |
| `eval/goldens/*.yaml` | 50 cases |

---

### Task 1: Line model

**Files:** create `scenarios/line.yaml`, `packages/qgate-generator/src/qgate_generator/line.py`; test `packages/qgate-generator/tests/test_line.py`.

**Produces:** `Line` (pydantic): `takt_s: int`, `stations: list[Station]`, `shifts: list[Shift]`, `eol_benches: list[Bench]`; `Station(id, name, sequence_pos, characteristics: list[Characteristic], fits_lot: bool)`; `Characteristic(id, name, unit, nominal, lower_limit, upper_limit, station_id)`; `Shift(id, label, starts_at: time, ends_at: time, crew)`; `Bench(id, station_id, repeatability_sigma, bias)`; `Line.load(path) -> Line`; `Line.characteristic(id) -> Characteristic`; `Line.eol_station -> Station`.

- [ ] Test: `line.yaml` loads; 30 stations; sequence positions 1..30 unique; every characteristic has `lower < nominal < upper`; last station is the EOL station with ≥ 1 bench.
- [ ] Test: unknown characteristic id raises `KeyError`.
- [ ] Author `line.yaml` — body (ST-01…10: gap/flush mm, weld current kA), paint (ST-11…15: thickness µm, viscosity), assembly (ST-16…29: torque Nm, pressure bar, voltage V; `fits_lot: true` on 6 stations), EOL (ST-30: 3 functional characteristics, benches EOL-B1..B3). Three shifts 06–14, 14–22, 22–06.
- [ ] Implement `line.py`; run; commit `feat(generator): line model`.

### Task 2: Core models mirroring Avro

**Files:** create `packages/qgate-core/src/qgate_core/models.py`; test `packages/qgate-core/tests/test_models.py`.

**Produces:** `BuildEvent`, `Measurement`, `EolResult`, `QualityAlert`, `ContainmentEvent` (Pydantic, field names identical to the `.avsc`), enums `Result`, `AlertKind`, `Severity`, `State`; `TOPIC: dict[type, str]` mapping model → topic; `key_of(record) -> str` returning the ADR-002 key.

- [ ] Test (parametrised over the five schemas): `set(model.model_fields) == {f["name"] for f in avsc["fields"]}` — a schema/model drift fails the build.
- [ ] Test: `key_of(Measurement(...)) == vin`, `key_of(QualityAlert(...)) == station_id`.
- [ ] Implement; commit `feat(core): models mirror avro contracts`.

### Task 3: Scenario model with id validation

**Files:** create `packages/qgate-generator/src/qgate_generator/scenario.py`, seven `scenarios/*.yaml`; test `packages/qgate-generator/tests/test_scenario.py`.

**Produces:** `Inject(kind: Literal["drift","step","lot","noise","bench_bias"], station_id, characteristic_id | None, start_sequence: int, end_sequence: int | None, magnitude: float, lot_id: str | None, bench_id: str | None)`; `Scenario(id, seed, vehicles, base_defect_rate, injects: list[Inject])`; `Scenario.load(path, line) -> Scenario` raising `ValueError` naming the bad id.

Scenario shapes (all `vehicles: 2000`, `base_defect_rate: 0.004`):

| id | injects |
|---|---|
| clean_baseline | none |
| tool_wear | drift ST-22 CH-22-TORQUE from seq 800, magnitude = slope per takt so limit is crossed ≈ seq 1100 |
| shift_step | step ST-18 CH-18-PRESSURE from seq 700 (a shift boundary), magnitude 0.8 × half-tolerance |
| bad_lot | lot L-24-0004 at ST-24: magnitude 1.2 × half-tolerance on CH-24-TORQUE for carriers only |
| correlated_noise | noise ST-17 (all chars), magnitude 0.5 × half-tolerance shared term, seq 900–1300 |
| bench_drift | bench_bias EOL-B2 from seq 600, magnitude reaches 1.5 × half-tolerance by seq 1400; no true defects beyond base rate |
| overlap | bad_lot + tool_wear injects together |

- [ ] Test: all seven load against `line.yaml`.
- [ ] Test (Review Focus 1): a scenario with `station_id: ST-99` raises `ValueError` containing `ST-99`.
- [ ] Implement; commit `feat(generator): scenarios as validated data`.

### Task 4: Stream generator with ground truth

**Files:** create `packages/qgate-generator/src/qgate_generator/stream.py`; test `packages/qgate-generator/tests/test_stream.py`.

**Produces:** `Run(events: list[BuildEvent | Measurement | EolResult], truth: GroundTruth)`; `GroundTruth(defective_vins: set[str], by_inject: dict[int, set[str]], bench_fault: bool)`; `generate(line, scenario, start: datetime = EPOCH) -> Run`. Events are in emission order: takt tick `t` emits, for each station `k`, vehicle `n = t - k`'s `BuildEvent`, its `Measurement`s (plus repeats `repeat_no 2,3` on a 5 % sample at EOL), and at the EOL station its `EolResult`. True value = nominal + N(0, tol/6) + injects; **reported** value adds bench bias (EOL only) and repeat noise. Ground-truth defective ⇔ any *true* value out of tolerance. EOL FAIL ⇔ any *reported* EOL value OOT **or** any upstream true OOT (defect manifests). Fault code = `F-<station_no>`. VIN format `SYN` + 14 digits from sequence. Lots: `L-<station_no>-<seq // 200 :04d>` at `fits_lot` stations. Shift from timestamp.

- [ ] Test (hypothesis): same `(line, scenario)` → identical event list (`seed` fixes everything).
- [ ] Test: events are non-decreasing in timestamp; every VIN has exactly 30 `BuildEvent`s and one `EolResult`.
- [ ] Test (Review Focus 4): `bench_drift` → `truth.defective_vins` ⊆ base-rate defects only (≤ 1.5 % of vehicles) **and** EOL FAILs > 5 % after seq 1000; `truth.bench_fault is True`.
- [ ] Test (Review Focus 5): `bad_lot` affected VINs are not one contiguous sequence range.
- [ ] Test: `tool_wear` first true-OOT sequence for CH-22-TORQUE is within [1000, 1200].
- [ ] Implement (numpy RNG, `Generator(PCG64(seed))`); commit `feat(generator): takt-ordered stream with ground truth`.

### Task 5: Avro + Kafka plumbing and the replay producer

**Files:** create `packages/qgate-core/src/qgate_core/avro.py`, `kafka.py`, `settings.py`; `packages/qgate-generator/src/qgate_generator/cli.py`; test `packages/qgate-core/tests/test_avro.py` (unit, no broker), `packages/qgate-core/tests/test_kafka_integration.py` (integration).

**Produces:** `Settings(kafka_bootstrap, schema_registry_url)` from env; `load_schema(topic) -> dict`; `serializer(topic, registry) -> AvroSerializer`, `deserializer(topic, registry) -> AvroDeserializer`; `ensure_topics(admin, {"line.*": 6, "quality.*": 3, "line.dlq": 1})`; `producer()`, `consumer(group, topics)`; `send_to_dlq(producer, msg, error)`; CLI `qgate-gen replay --scenario tool_wear --speed 0` (0 = as fast as possible) and `--speed 10`.

- [ ] Unit test: round-trip each model through `fastavro` with its schema (no registry) — `dict → bytes → dict` equal.
- [ ] Integration test (testcontainers `RedpandaContainer`): `ensure_topics` creates 6 partitions for `line.measurements`; produce one `Measurement` with the registry serializer, consume it back, equal.
- [ ] Implement; `replay` produces `Run.events` keyed per ADR-002, sleeping `emit_offset` when `speed > 0`; commit `feat(core): avro registry + kafka helpers; feat(generator): replay producer`.

### Task 6: Migrations and roles

**Files:** create `db/migrations/0001_dims.sql`, `0002_facts.sql`, `0003_containment.sql`, `0004_roles.sql`, `db/set_role_passwords.sql`; modify `docker-compose.yml` (add `roles` one-shot; compose per-role `DATABASE_URL_*` from `POSTGRES_PASSWORD`), `.env.example` (drop the six URLs); test `packages/qgate-core/tests/test_migrations_integration.py` (integration, `PostgresContainer` + dbmate via `subprocess` … no: dbmate is not on the runner — apply the SQL files in order with psycopg, splitting on `-- migrate:down`).

DDL shape (schema `qgate`, `search_path` set per role):

```sql
-- 0001: dims. text ids because they are human-authored in line.yaml.
create table qgate.dim_station (station_id text primary key, name text not null, sequence_pos int not null unique, takt_s int not null, fits_lot boolean not null default false);
create table qgate.dim_characteristic (characteristic_id text primary key, station_id text not null references qgate.dim_station, name text not null, unit text not null, nominal double precision not null, lower_limit double precision not null, upper_limit double precision not null, check (lower_limit < nominal and nominal < upper_limit));
create index on qgate.dim_characteristic (station_id);
create table qgate.dim_shift (shift_id text primary key, label text not null, starts_at time not null, ends_at time not null, crew text not null);
create table qgate.dim_bench (bench_id text primary key, station_id text not null references qgate.dim_station, repeatability_sigma double precision not null, bias double precision not null, calibrated_at timestamptz);
-- 0002: facts. Natural keys; ingest upserts with ON CONFLICT DO NOTHING (idempotent replay).
create table qgate.fact_build_event (vin text not null, station_id text not null references qgate.dim_station, sequence_no bigint not null, entered_at timestamptz not null, shift_id text not null references qgate.dim_shift, operator_id text not null, parts_lots text[] not null default '{}', primary key (vin, station_id));
create index on qgate.fact_build_event (station_id, entered_at);
create index on qgate.fact_build_event using gin (parts_lots);
create table qgate.fact_measurement (id bigint generated always as identity primary key, vin text not null, station_id text not null, characteristic_id text not null references qgate.dim_characteristic, bench_id text not null references qgate.dim_bench, measured_at timestamptz not null, value double precision not null, nominal double precision not null, lower_limit double precision not null, upper_limit double precision not null, repeat_no int not null default 1, deviation double precision generated always as (value - nominal) stored, out_of_tolerance boolean generated always as (value < lower_limit or value > upper_limit) stored, unique (vin, characteristic_id, repeat_no));
create index on qgate.fact_measurement (station_id, characteristic_id, measured_at);
create index on qgate.fact_measurement (bench_id, measured_at) where repeat_no > 1;
create table qgate.fact_eol_result (vin text not null, tested_at timestamptz not null, bench_id text not null references qgate.dim_bench, result text not null check (result in ('PASS','FAIL')), primary key (vin, tested_at));
create table qgate.fact_eol_fault (vin text not null, tested_at timestamptz not null, fault_code text not null, primary key (vin, tested_at, fault_code), foreign key (vin, tested_at) references qgate.fact_eol_result);
create index on qgate.fact_eol_fault (fault_code, tested_at);
-- 0003: decisions (design §7.1), kind/state as text + check.
-- 0004: roles nologin; grants per design §7.2; set_role_passwords.sql: alter role … password :'pw'.
```

- [ ] Integration test: apply all migrations to a fresh Postgres; `select count(*) from information_schema.tables where table_schema='qgate'` = 10; `ingest_rw` cannot `insert into qgate.containment`; `agent_ro` cannot `insert` anywhere.
- [ ] Implement; `make up-infra` applies them; commit `feat(db): schema, indexes, least-privilege roles`.

### Task 7: Dim seeding

**Files:** modify `packages/qgate-generator/src/qgate_generator/cli.py` (`seed-dims`); test `packages/qgate-generator/tests/test_seed_integration.py`.

- [ ] Integration test: `seed-dims` against a migrated container → 30 stations, 3 shifts, 3 benches; running twice leaves counts unchanged.
- [ ] Implement with `psycopg` `executemany … on conflict do nothing`; commit `feat(generator): seed dims from line.yaml`.

### Task 8: Ingest

**Files:** create `services/ingest/src/qgate_ingest/upsert.py`, modify `main.py`; test `services/ingest/tests/test_ingest_integration.py`.

**Consumes:** `consumer`, `deserializer`, `send_to_dlq` from Task 5; models from Task 2.
**Produces:** `upsert(conn, record) -> None` (one `INSERT … ON CONFLICT DO NOTHING` per record type; `EolResult` also inserts fault rows); `run_forever(settings) -> None` (poll → decode → validate → upsert → commit offset; on any exception → DLQ, commit, continue); `/health` and `/metrics` served in a thread from Task 0's `health_app("ingest")`.

- [ ] Integration test (Redpanda + Postgres containers): replay `clean_baseline` with `vehicles: 100` → `count(fact_build_event) = 3000`, `count(fact_eol_result) = 100`; **replay again** → counts unchanged (Review Focus 2).
- [ ] Integration test (Review Focus 3): produce one non-Avro byte string to `line.measurements` → one record in `line.dlq` whose value contains `error`, and a subsequent valid message is still ingested.
- [ ] Implement; commit `feat(ingest): idempotent upsert with DLQ`.

### Task 9: Genealogy query and benchmark

**Files:** create `db/queries/genealogy.sql`; test `services/ingest/tests/test_genealogy_integration.py`.

**Produces:** named query `genealogy_by_vin(vin)` returning rows ordered by `sequence_pos`: station, entered_at, shift, operator, parts_lots, and a JSON array of measurements `{characteristic_id, bench_id, value, deviation, out_of_tolerance, repeat_no}`.

- [ ] Integration test: seed 1M `fact_measurement` rows via `generate_series` for 20 000 VINs; `EXPLAIN (ANALYZE, FORMAT JSON)` shows no `Seq Scan` on fact tables; median of 20 runs < 50 ms.
- [ ] Implement (`aiosql`-style `-- name: genealogy_by_vin` header); commit `feat(db): genealogy query under 50 ms`.

### Task 10: Fault map with real ids

**Files:** rewrite `knowledge/fault_map.yaml`; test `packages/qgate-generator/tests/test_fault_map.py`.

- [ ] Test: every `station_id`/`characteristic_id` in the map exists in `line.yaml`; every station that can be OOT (all 30) has a fault code `F-<nn>`; `bench_sensitive: true` on the EOL codes.
- [ ] Author: 30 codes `F-01…F-30`, each with its own station as prior 0.7 and the upstream neighbour at 0.3 with a one-line rationale; commit `feat(knowledge): fault map for 30 stations`.

### Task 11: Golden cases

**Files:** modify `cli.py` (`goldens --out eval/goldens`), create `eval/goldens/*.yaml` (50), `eval/goldens/schema.py` (Pydantic `Golden`); test `eval/harness/tests/test_goldens.py`.

**Produces:** `Golden(id, family, scenario, seed, trigger: Trigger(vin, fault_codes), expected: Expected(decision, station_id, window_start_sequence, tolerance_takts, lot_ids, defective_vins_from), human: Human(action, amend), notes)`.

Family → selection rule from ground truth:

| family | scenario | trigger VIN | expected |
|---|---|---|---|
| isolated ×12 | clean_baseline (seeds 1..12) | a base-rate defect | `SINGLE` |
| drift ×12 | tool_wear (seeds 1..12) | first FAIL after true onset | `WINDOW`, station ST-22, `window_start_sequence` = first true-OOT seq, tolerance 15 |
| lot ×8 | bad_lot (seeds 1..8) | a lot-carrier FAIL | `LOT`, `lot_ids: [L-24-0004]` |
| bench ×8 | bench_drift (seeds 1..8) | a false FAIL (not in truth) | `NONE` |
| contradictory ×6 | shift_step (seeds 1..6) | the *first* vehicle of the step (no siblings yet) | `ESCALATE` |
| overlap ×4 | overlap (seeds 1..4) | a lot-carrier FAIL inside the drift window | `MULTI` |

Human action: `APPROVE` for all except two `drift` cases (`AMEND` window −10 takts) and one `lot` case (`REJECT`, reason "lot already quarantined") so the audit diff path is exercised.

- [ ] Test: 50 files parse as `Golden`; family counts match; every scenario/station id exists; every trigger VIN is a FAIL in its scenario's run; every `NONE` trigger is **not** in `truth.defective_vins`.
- [ ] Implement `goldens` command; run it; commit `feat(eval): fifty golden cases from ground truth`; tag `goldens-v1`.

### Task 12: Gate 1

- [ ] `make up-infra && uv run qgate-gen seed-dims && uv run qgate-gen replay --scenario tool_wear --speed 0` then `docker compose up -d ingest`; `psql`-equivalent query for one VIN returns 30 rows with measurements.
- [ ] `make lint typecheck unit integration` green locally; CI green; ADR-010 written; checklist §Phase 1 ticked; `git tag goldens-v1 && git push --tags`.
