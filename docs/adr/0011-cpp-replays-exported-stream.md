# ADR-011: The C++ line-sim replays a stream the Python generator exported

**Status:** Accepted · **Date:** 2026-09-22

## Context

The design gives `line-sim` (C++) the job of the plant's edge producer: publish build events, measurements and end-of-line results to Redpanda at takt. The scenarios that decide *what* happens — tool wear, a shift step, a bad lot, a drifting bench — are seeded stochastic models in the Python generator, and the fifty golden cases are authored from that generator's ground truth. A C++ re-implementation of those models would have to reproduce numpy's PCG64 stream bit-for-bit to keep the goldens honest, or accept two sources of truth that drift apart.

## Decision

`qgate-gen export` writes a scenario as a JSONL manifest — one line per event in takt order with `topic`, `key`, `ts_ms` and the schema-less Avro body as hex. `line-sim` reads the manifest and does what an edge producer does: schedules each event at its simulated time compressed by the replay speed (absolute schedule from replay start, so a late event never delays the next), registers each topic's schema, frames the body in Confluent wire format, produces with librdkafka (idempotent, keyed per ADR-002, message timestamp = simulated time), counts deliveries for `/metrics`, and on SIGTERM stops scheduling, flushes and exits 0. The checklist's "scenario reader" is therefore a manifest reader.

## Alternatives considered

- **Re-implement the scenario models in C++** — ~800 lines duplicating the generator; goldens and stream would diverge at the first bug fix on either side.
- **Have C++ read `scenarios/*.yaml` and call the Python generator as a subprocess** — one process pretending to be another; no simpler than a file between them.
- **A binary manifest** — smaller, but not greppable; hex decodes in six lines and a 138k-event scenario is 31 MB.
- **avro-cpp for encoding in C++** — unnecessary once the body is pre-encoded; the wire header is five bytes.

## Consequences

- Ground truth has exactly one implementation; `make demo` runs `gen export` then `line-sim`.
- The C++ surface is small and fully testable without a broker: schedule maths, manifest parsing, framing (Catch2). Transport is verified on the compose stack: scheduled == delivered, DLQ empty, topic watermarks equal the manifest counts, Postgres row counts equal the manifest counts.
- The runtime image is `debian:bookworm-slim` (librdkafka and cpp-httplib from apt) rather than distroless; non-root and read-only.
- The Python producer (`qgate-gen replay`) stays as the fallback.
