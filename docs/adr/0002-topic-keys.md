# ADR-002: Topic keys — VIN for line events, station for alerts

**Status:** Accepted · **Date:** 2026-09-21

## Context

Kafka guarantees order only within a partition, and the partition is chosen by key. Two different consumers need two different orderings: `ingest` and the agent reason about one vehicle's history in order; `detect` and the alert consumers reason about one station's signal in order.

## Decision

`line.build.events`, `line.measurements` and `line.eol.results` are keyed by `vin`. `quality.alerts` is keyed by `station_id`. `quality.containment` is keyed by `containment_id`. `line.*` topics have 6 partitions, `quality.*` have 3.

## Alternatives considered

- **Key everything by station** — station-ordered measurements are convenient for SPC, but a vehicle's facts would arrive out of order across partitions, and genealogy assembly would need reordering logic in `ingest`.
- **No key (round-robin)** — maximal parallelism, no ordering; every consumer would need to sort.
- **Composite key (vin, station)** — no benefit over `vin` for ordering; spreads one vehicle across partitions.

## Consequences

- Per-vehicle ordering is free for `ingest` and the agent's consumer.
- `detect-worker` receives a station's measurements interleaved across partitions and must window by `measured_at`, not by arrival — which it should do anyway.
- Hot stations do not create hot partitions, because measurements are spread by VIN.
