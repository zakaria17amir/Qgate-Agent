# ADR-003: The approval gate is non-bypassable

**Status:** Accepted · **Date:** 2026-09-21

## Context

The agent proposes containments that, if committed, hold real vehicles in a real plant system. The cost asymmetry (one escape versus hundreds of held cars) and the accountability question (who decided?) both require a human decision on every commit. A gate that can be switched off in configuration will, eventually, be switched off.

## Decision

The `gate` node calls LangGraph `interrupt()` and the graph state is checkpointed to Postgres. The `commit` node is reachable only through a resume carrying a `HumanDecision`. There is no configuration flag, environment variable, or test hook that skips the gate. The evaluation harness stands in for the human by calling the same public approval endpoints with a token of role `approver`. Expiry rejects; nothing auto-approves.

Defence in depth: the agent's Postgres role for tools is `agent_ro`; its only write path is the checkpointer connection (`checkpoint_rw`), scoped to checkpoint tables. The agent's only write to a plant system is behind the gate.

## Alternatives considered

- **`AUTO_APPROVE=1` for tests and demos** — the harness can act as the approver through the real endpoint; a flag would exist in production images.
- **Confidence-threshold auto-commit** — tempting for the "isolated fault" family; rejected because the audit trail would then contain decisions no human made.
- **Gate in `api` only, agent unaware** — the agent would then "complete" before a human decided, and restart-safety of the pending decision would depend on `api`, not on the graph's checkpoint.

## Consequences

- Every triage costs a human decision; the agreement rate and gate decision time become first-class metrics.
- Pending decisions must survive process restarts; this is a chaos test, not an assumption.
- Any future request to bypass the gate requires a new ADR that supersedes this one.
