# Implementation plans

One plan per phase, written from `docs/design/2026-09-21-architecture.md` before that phase starts. Each plan is a list of bite-sized, test-first tasks with exact files, interfaces and commands.

| Plan | Phase | Exit criterion |
|---|---|---|
| `phase-0-skeleton.md` | Repo, compose infra, ADRs, golden schema | `make up` brings up infra; CI green on an empty project |
| `phase-1-data-spine.md` | Generator, schemas, ingest, migrations, 50 goldens | Any VIN's full build path from the DB; goldens tagged |
| `phase-2-detect-tools.md` | detect, read-only tools, mock-mes | Tools alone are correct on every golden, no model |
| `phase-3-graph-gate.md` | Graph, api, audit, cassettes, eval replay | Approve/amend via curl; restart mid-gate loses nothing |
| `phase-4-console-cpp-reliability.md` | console, line-sim C++, retries, chaos | Demo without a terminal; chaos suite passes |
| `phase-5-operations.md` | Prefect, dashboard, load test, CI complete | Nightly publishes without a human |
| `phase-6-ship.md` | README, RUNBOOK, ROI, fresh clone, v1.0.0 | Stranger clones, one command, it works |
