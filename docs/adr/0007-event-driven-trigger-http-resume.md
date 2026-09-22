# ADR-007: Event-driven trigger, HTTP resume

**Status:** Accepted · **Date:** 2026-09-22

## Context

A triage has two very different entry points in time. It *starts* when the line produces an end-of-line failure — an event that arrives on a stream, possibly in bursts. It *resumes* when a person decides at the gate — a single, deliberate action minutes later that must land on exactly the thread that is waiting.

## Decision

The agent consumes `line.eol.results` (consumer group `agent-triage`, starting at *latest* so a fresh deployment does not re-triage history) and starts a graph thread per `FAIL` through its own `POST /triage` handler — the same handler a manual trigger uses. Human decisions reach the agent as `POST /threads/{id}/resume` from the api, which is the only caller. Triages run on a bounded worker pool so a burst on the line cannot starve the health endpoint or the resume path.

## Alternatives considered

- **API-triggered only** (ingest posts failures to the api) — simpler, but the agent never touches the stream, and "APIs to plant systems" would be the only integration claim left standing.
- **Fully event-driven** (decisions on a topic the agent consumes) — the gate's "blocks until decided" becomes eventually consistent, and a decision could be consumed by a process that does not hold the waiting thread. The checkpointer makes this workable, but debugging a lost decision across two topics is not worth the purity.

## Consequences

- One code path per triage regardless of how it started; `eol_ts` is carried from the event, or taken from the vehicle's own EOL record when a manual trigger omits it.
- The api must know the agent's address; the agent must not need the api's beyond `/internal/*`.
- A backlog on the topic after an outage is triaged in order at worker-pool pace; nothing is dropped, nothing is parallelised beyond `WORKERS`.
