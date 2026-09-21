# schemas

Avro contracts for every Kafka topic. Registered in Redpanda's schema registry on service start under subject `<topic>-value`, compatibility `BACKWARD`.

| File | Topic | Key | Producer | Consumers |
|---|---|---|---|---|
| `line.build.events.v1.avsc` | `line.build.events` | `vin` | line-sim | ingest |
| `line.measurements.v1.avsc` | `line.measurements` | `vin` | line-sim | ingest, detect-worker |
| `line.eol.results.v1.avsc` | `line.eol.results` | `vin` | line-sim | ingest, agent |
| `quality.alerts.v1.avsc` | `quality.alerts` | `station_id` | detect-worker | api (materialise), console via api |
| `quality.containment.v1.avsc` | `quality.containment` | `containment_id` | api | pipelines, external |

`line.dlq` carries JSON, not Avro: `{topic, partition, offset, error, raw_b64, failed_at}`.

**Evolution rule:** a new version is a new file (`*.v2.avsc`); fields may only be added with defaults. The contract test registers v2 and asserts a v1 consumer still reads it.

**Why these keys:** keying by `vin` orders every fact about one vehicle within a partition; keying alerts by `station_id` orders every signal about one station. See ADR-002.
