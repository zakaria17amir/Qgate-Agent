# ADR-008: The api owns containment state; the agent is read-only on Postgres

**Status:** Accepted · **Date:** 2026-09-22

## Context

The gate is the design (ADR-003). Its guarantee is only as strong as the weakest write path: if the process that *proposes* can also *record decisions*, a bug or a prompt injection in that process can approve its own work. The containment tables are also the audit trail the README's metrics come from.

## Decision

`api` is the single writer of `containment`, `containment_vin` and `containment_audit`, connected as `api_rw`. The agent reads facts as `agent_ro` and writes graph state as `checkpoint_rw`, a role scoped to the `checkpoint` schema. The agent's only way to create or change a containment is HTTP to `/internal/containments` with a `service` token; the only way to *decide* one is a human's `approver` token on the public endpoints. Kafka announcements of state changes are the api's job and are optional, so the eval harness runs the api in-process on Postgres alone.

## Alternatives considered

- **Agent writes containment tables directly** — fewer hops; but the agent then holds a write role and the "blast radius is one pending record" claim is a policy, not a property.
- **Event-sourced containment state** — elegant, but "list pending approvals" becomes a projection to build before the console can exist.

## Consequences

- Two extra HTTP hops per triage (propose, report) on the *proposal* path; the human path is unaffected.
- The proposal write is its own graph node: a node that interrupts re-runs from its first line on resume, so a side effect placed before `interrupt()` executes twice. The end-to-end test asserts exactly one row per thread.
- A second decision on the same containment is a `409`; expiry is a state change by `system`, never an approval.
