# ADR-010: Plain SQL migrations with dbmate, no ORM

**Status:** Accepted · **Date:** 2026-09-21

## Context

Three languages touch the database: Python services write and read it, the C++ producer's data lands in it, the evaluation harness benchmarks it. The schema uses Postgres features an ORM abstracts badly or not at all — generated columns, partial indexes, GIN on arrays, `on conflict do nothing`, per-role grants.

## Decision

Migrations are numbered `.sql` files in `db/migrations` with dbmate's `-- migrate:up` / `-- migrate:down` markers, applied by a one-shot `migrate` container before any service starts. Queries the agent depends on are named SQL in `db/queries` loaded with `aiosql`, so the exact statement that runs is the one in the repo and can be `EXPLAIN`ed in a test. Role passwords are applied by a second one-shot (`roles`) from the single `POSTGRES_PASSWORD`, so no secret is in a migration and no URL is copied six times into `.env`.

## Alternatives considered

- **SQLAlchemy + Alembic** — autogenerate cannot express generated columns or partial indexes without hand edits, and the ORM layer would hide the queries whose plans we assert on.
- **Postgres `docker-entrypoint-initdb.d`** — runs only on first volume init; not a migration story.
- **Schema created by the application at start-up** — five services would race, and the roles would need superuser.

## Consequences

- Integration tests apply the same files (split on the down marker) to a throwaway container; there is one schema definition.
- Reviewers read the DDL directly; the indexes are visible next to the tables they serve.
- Rollback is a written `down` section, exercised by hand, not automatically tested.
