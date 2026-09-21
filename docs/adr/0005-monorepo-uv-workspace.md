# ADR-005: Monorepo with a uv workspace

**Status:** Accepted · **Date:** 2026-09-21

## Context

Eight deployable units (six services, a console, a pipelines package) plus two shared libraries, built by one person and read by reviewers who have thirty seconds. Contracts between units (Avro schemas, OpenAPI, SQL) change together with the code on both sides.

## Decision

One repository. Python members are a `uv` workspace (`packages/*`, `services/*`, `pipelines`, `eval/harness`) sharing one `uv.lock`; the console is an npm project under `console/`; the C++ producer is a CMake project under `services/line-sim`. One compose file, one CI workflow, one `Makefile` whose targets are the CI jobs. Every Python image is built from the single `docker/python.Dockerfile` with `PACKAGE` and `ENTRYPOINT` build args.

## Alternatives considered

- **Polyrepo, one per service** — eight CI configs, eight dependabot streams, cross-repo contract changes need coordinated PRs; a reviewer has to open eight tabs.
- **Monorepo, one `pyproject.toml`** — all services would share one dependency set and one image; LangGraph in the ingest image, librdkafka in the agent image. Loses the per-service boundary that makes the microservices claim true.

## Consequences

- One lockfile means one resolution: a dependency conflict between two services surfaces at `uv lock`, not in production.
- `uv sync --frozen --package X` needs every member's `pyproject.toml` in the build context, so the shared Dockerfile copies the whole repo; layer caching for dependencies is traded for one recipe instead of six.
- `mock-mes` is a workspace member for tooling only; it must not import `qgate-core` (it plays a foreign system). A test enforces this from Phase 2.
