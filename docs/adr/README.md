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
| [007](0007-event-driven-trigger-http-resume.md) | Event-driven trigger, HTTP resume | Accepted |
| [008](0008-api-owns-containment-state.md) | `api` owns containment state; agent is read-only on Postgres | Accepted |
| [009](0009-detect-two-processes.md) | Two `detect` processes from one image | Accepted |
| [010](0010-dbmate-sql-migrations.md) | dbmate SQL migrations over an ORM | Accepted |
| [011](0011-cpp-replays-exported-stream.md) | The C++ line-sim replays a stream the Python generator exported | Accepted |
| [012](0012-commit-retry-loop-and-breaker.md) | Commit retry loop and breaker: approvals survive a plant-system outage | Accepted |
