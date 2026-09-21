# Architecture Decision Records

One page per decision. Never edited after acceptance; a changed decision is a new ADR that supersedes the old one. Copy `0000-template.md`.

| ADR | Title | Status |
|---|---|---|
| [001](0001-synthetic-data-primary.md) | Synthetic data is the primary source; competition datasets are never committed | Accepted |
| [002](0002-topic-keys.md) | Topic keys: VIN for line events, station for alerts | Accepted |
| [003](0003-non-bypassable-gate.md) | The approval gate is non-bypassable | Accepted |
| [004](0004-sql-correlates-model-explains.md) | SQL correlates and bounds; the model orchestrates and explains | Accepted |
| [005](0005-monorepo-uv-workspace.md) | Monorepo with uv workspace | Accepted |
| [006](0006-provider-agnostic-llm-cassettes.md) | Provider-agnostic LLM with cassette record/replay | Accepted |
| 007 | Event-driven trigger, HTTP resume | Phase 3 |
| 008 | `api` owns containment state; agent is read-only on Postgres | Phase 3 |
| 009 | Two `detect` processes from one image | Phase 2 |
| [010](0010-dbmate-sql-migrations.md) | dbmate SQL migrations over an ORM | Accepted |
