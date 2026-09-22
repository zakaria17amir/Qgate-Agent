# line-sim

C++20 edge producer. Replays a scenario manifest onto Redpanda **at takt**: each event is
published at its simulated time since the first event, compressed by `--speed` (10 = ten times
faster than the line; 0 = as fast as possible). The manifest comes from `qgate-gen export`
(ADR-011): the Python generator stays the single source of ground truth; C++ owns timing,
framing, transport and a clean stop.

| File | Responsibility |
|---|---|
| `src/scheduler.{hpp,cpp}` | `emit_offset` / `due_at`: absolute schedule from replay start, so a late event never delays the next one |
| `src/manifest.{hpp,cpp}` | JSONL reader (`topic, key, ts_ms, avro_hex`), hex decoding, bad lines named by number |
| `src/wire.hpp` | Confluent wire format: `0x00` + big-endian schema id + Avro body |
| `src/main.cpp` | Registers each topic's `.avsc` with the schema registry (idempotent), librdkafka idempotent producer keyed per ADR-002 with the message timestamp set to the simulated time, delivery-report counters, `/metrics` + `/health` on `--metrics-port`, SIGTERM/SIGINT → stop scheduling, flush, exit 0 |
| `tests/` | Catch2 v2: schedule maths (speed 0, absolute due times), manifest parsing, hex, framing |

```
line-sim --file /data/tool_wear.jsonl --brokers redpanda:9092 --registry http://redpanda:8081 \
         --schemas /schemas --speed 10 --metrics-port 8010
```

Build only inside Docker (`make unit` runs the test stage; dependencies are Debian packages:
Catch2, nlohmann-json, librdkafka, cpp-httplib). `make demo SCENARIO=tool_wear SPEED=10` exports the
manifest with the `gen` service and replays it. The Python producer (`qgate-gen replay`) remains
the fallback.

Verified on the compose stack: 138,624 events scheduled = delivered, 0 errors, DLQ empty, topic
high-watermarks equal to the manifest's per-topic counts; SIGTERM mid-run exits 0 with
scheduled == delivered.
