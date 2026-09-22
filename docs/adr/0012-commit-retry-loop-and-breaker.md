# ADR-012: An approved containment survives a plant-system outage — retry loop and breaker

**Status:** Accepted · **Date:** 2026-09-22

## Context

After the human approves, the agent makes the one write to the plant: `POST /v1/holds` on the MES. The MES can be slow, down, or acknowledge and lose the reply. The approval must not be lost, the hold must be created exactly once, and nothing may bypass the gate on the way to recovery (ADR-003). Phase 3 ended the thread with `COMMIT_PENDING` on a 5xx and left recovery to a future sweeper.

## Decision

Three layers, each small:

1. **Retries with backoff** (`tools/mes.py`): five attempts, exponential jitter capped at 8 s, on a transport error or a 5xx. The hold is idempotent on the containment id (the MES replays the same key with 200), so every retry is safe; a lost acknowledgement is recovered on the next attempt without leaving the node. Connect-level blips on all three of the agent's HTTP clients are retried by the transport.
2. **A breaker** in front of the MES call: opens for 60 s after the attempts are exhausted, lets one probe through when half-open, closes on success. One per process, so every triage worker learns at once that the MES is down and parks instead of hammering it.
3. **A retry loop in the graph**: `commit → pending → retry_gate → commit`. `pending` PATCHes the api to `COMMIT_PENDING`; `retry_gate` only calls `interrupt()`. The api's sweeper, on its 30 s tick, resumes every `COMMIT_PENDING` thread with `RETRY`; resuming re-runs `commit` from its first line, which is exactly one more attempt. A 409 from the agent ("not waiting") means a worker already has it and is not an error.

The same rule as `submit`/`gate` applies: a node that interrupts has no side effects, because a resumed node re-runs from its first line.

## Alternatives considered

- **Keep the graph alive by interrupting inside `commit`** — the resume value is consumed on re-entry, so a second failure in the same run would not pause; each stale value causes an extra attempt. A separate side-effect-free node is the honest shape.
- **A breaker library** — the behaviour needed is fifteen lines; the sweeper cadence is already the retry clock.
- **Let the api commit to the MES instead of the agent** — moves the write into the state owner (ADR-008) but puts plant-system credentials and retry policy in the public api.

## Consequences

- Design §9.4 holds on the compose stack: cut `agent → mock-mes` with toxiproxy during a commit, wait, restore → `COMMITTED`, one hold. The in-process tests cover lost-ack (one hold, `duplicate_replays ≥ 1`) and outage-then-recovery, with the backoff patched to zero.
- A second human decision on a parked containment is a 409: it is already approved.
- `GET /threads/{id}` reports `WAITING_RETRY` for a parked thread, distinct from `WAITING_GATE`.
- Breaker state is per process; two agent replicas learn independently. The open period and sweeper cadence are constants, not settings, until someone needs them otherwise.
