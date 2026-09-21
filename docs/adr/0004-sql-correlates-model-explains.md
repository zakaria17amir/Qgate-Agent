# ADR-004: SQL correlates and bounds; the model orchestrates and explains

**Status:** Accepted · **Date:** 2026-09-21

## Context

A containment window is a set of VINs derived from timestamps, station sequence and lot membership. That is arithmetic over the genealogy tables. Language models are non-deterministic, cannot be audited line by line, and are the most expensive and slowest component in the graph. The evaluation must be reproducible in CI.

## Decision

Sibling correlation (`correlate`), drift onset (`drift_check` via `detect`), and window/lot bounding (`bound`) are deterministic: SQL over Postgres and numeric change-point detection. The model is called in exactly two places — ranking candidate stations from a hand-authored fault map (`hypothesise`) and writing the human-readable order (`compose`) — plus the one-paragraph explanation on escalation. Every model output is a validated structured object; an output that names a station not in the fault map, or bounds that differ from `bound`'s result, is rejected and retried once, then escalated.

## Alternatives considered

- **Agent with free tool use decides everything** — flexible, but the containment set would vary between runs and the audit could not explain why 37 vehicles and not 41.
- **No model at all** — the fault map and templates could produce an order; but ranking hypotheses across shift/lot/drift evidence and writing an order a shift leader acts on is where the model earns its cost.
- **Model does the SQL (text-to-SQL)** — reproducibility and injection concerns; the queries are five known shapes, not an open-ended question.

## Consequences

- `replay` mode in CI is meaningful: with recorded model responses, the whole graph is byte-reproducible.
- The Phase 2 exit criterion can be met with no model in the loop — the deterministic tools alone must return correct siblings, onset and bench verdicts on every golden.
- Cost per triage is bounded by two calls; the "LLM-only" latency breakdown is honest.
