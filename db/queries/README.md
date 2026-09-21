# queries

Named SQL loaded with `aiosql`; each backs exactly one agent tool. Tested against fixture data in `services/agent/tests`, with a latency budget asserted at 5 M measurements.

| File | Tool | Budget (p95) |
|---|---|---|
| `genealogy.sql` — `genealogy_by_vin` | `get_vehicle_genealogy` | 50 ms |
| `station.sql` — `station_spec` | `get_station_spec` | 5 ms |
| `correlate.sql` — `correlated_failures` | `find_correlated_failures` | 100 ms |
| `window.sql` — `vins_in_window`, `vins_by_lot` | `estimate_containment_window` | 50 ms |

The agent's connection uses role `agent_ro`. None of these statements can write.
