# scenarios

Parameter files the generator (`qgate-gen`) and `line-sim` read. `line.yaml` describes the line itself; each other file is one defect scenario with its ground truth declared, so the evaluation can compute escapes, precision and recall.

| File | Mechanism | Trap it sets |
|---|---|---|
| `line.yaml` | 30 stations, takt, shifts, benches, characteristics | — |
| `clean_baseline.yaml` | Nothing wrong; sporadic isolated failures | Agent must not manufacture patterns |
| `tool_wear.yaml` | Linear drift in one characteristic at one station over ~400 takts | Onset is fuzzy |
| `shift_step.yaml` | Mean shift coinciding with a shift boundary | Crew or shift? Confounded on purpose |
| `bad_lot.yaml` | Elevated failure rate for VINs carrying one parts lot; non-contiguous | Time-window containment is wrong |
| `correlated_noise.yaml` | Shared noise across characteristics on one station | One cause, many alerts |
| `bench_drift.yaml` | Bench bias drifts; cars are good; %GRR degrades | Any containment is the wrong answer |
| `overlap.yaml` | Bad lot plus station drift in the same window | Two containments, not one |

Every scenario file has the same top-level shape:

```yaml
id: tool_wear
seed: 42
vehicles: 2000
injects:
  - kind: drift            # drift | step | lot | noise | bench_bias
    station_id: ST-42
    characteristic_id: CH-42-TORQUE
    start_sequence: 800
    slope_per_takt: 0.004
ground_truth:
  defective_vins: generated   # resolved by the generator and written next to the stream
  bench_fault: false
```

Files are added in Phase 1.
