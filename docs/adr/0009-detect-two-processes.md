# ADR-009: `detect` is one image running as two processes

**Status:** Accepted · **Date:** 2026-09-22

## Context

`detect` has two jobs with opposite shapes. One is a stream consumer that must keep up with every measurement the line produces and raise rule violations as they happen. The other answers the agent's questions on demand — *was this station drifting, and since when? can this bench be trusted?* — with a latency budget, over a time window the agent chooses.

## Decision

One package, one image, two compose services: `detect` (`detect api`, HTTP) and `detect-worker` (`detect worker`, Kafka consumer group `detect-worker`). They share the SPC, change-point and metrology modules and nothing at runtime. The worker emits only `RULE_VIOLATION` alerts from Western Electric rules on in-memory windows kept in *measurement* order. Change-point onset and bench capability are computed by the API from Postgres when asked.

## Alternatives considered

- **One process with a background consumer task** — a burst on the line would starve the HTTP loop exactly when the agent is asking; and a crash in either half takes down both.
- **Streaming change-point in the worker** — PELT over a rolling window per characteristic on every message is O(n²) work for an answer nobody has asked for yet; the agent always asks with a window, so on-demand is both cheaper and exact.
- **Two packages** — the algorithms are the shared part; splitting them would duplicate the tests that matter most.

## Consequences

- Alerts are timely; onsets are exact. The two never disagree because they use different questions, not different code.
- Topics are keyed by VIN (ADR-002), so a characteristic's readings arrive interleaved across partitions; the worker orders by `measured_at`, not by arrival.
- Scaling is independent: more worker partitions do not touch API latency.
