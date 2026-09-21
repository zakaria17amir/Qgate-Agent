# migrations

Plain SQL applied by [dbmate](https://github.com/amacneil/dbmate) (`make migrate`; also runs as the `migrate` one-shot container before any service starts). Language-agnostic on purpose: Python, C++ and the eval harness all share one schema without an ORM in the middle (ADR-010).

Planned files (Phase 1):

| File | Contents |
|---|---|
| `0001_dims.sql` | `dim_station`, `dim_characteristic`, `dim_shift`, `dim_bench` |
| `0002_facts.sql` | `fact_build_event`, `fact_measurement` (range-partitioned), `fact_eol_result`, `fact_eol_fault`, indexes |
| `0003_containment.sql` | `containment`, `containment_vin`, `containment_audit`, enums |
| `0004_roles.sql` | `ingest_rw`, `api_rw`, `agent_ro`, `detect_ro`, `checkpoint_rw` with GRANTs |

LangGraph's checkpoint tables are created by `langgraph-checkpoint-postgres` `.setup()` under `checkpoint_rw`, not here.

Each file uses dbmate's `-- migrate:up` / `-- migrate:down` markers.
