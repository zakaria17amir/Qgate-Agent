# goldens

Fifty golden cases, **written before the agent exists** and frozen with the tag `goldens-v1`. Six families:

| Family | Count | Expected decision |
|---|---|---|
| `isolated` | 12 | `SINGLE` — the one vehicle |
| `drift` | 12 | `WINDOW` back to estimated onset |
| `lot` | 8 | `LOT` — by parts lot, not time |
| `bench` | 8 | `NONE` — flag the bench |
| `contradictory` | 6 | `ESCALATE` — no proposal |
| `overlap` | 4 | two containments |

One YAML per case, named `<family>-<nn>.yaml`:

```yaml
id: drift-03
family: drift
scenario: tool_wear
seed: 4203
trigger:
  vin: WVW-000000000871
  fault_codes: [F042]
expected:
  decision: WINDOW                 # SINGLE | WINDOW | LOT | NONE | ESCALATE | MULTI
  station_id: ST-42
  window_start_sequence: 800       # ± tolerance below
  tolerance_takts: 15
  lot_ids: []
  defective_vins_from: ground_truth  # scored against the scenario's ground truth
human:                             # what the nightly harness does at the gate, standing in for a person
  action: APPROVE                  # APPROVE | AMEND | REJECT
  amend: null
notes: "Onset is gradual; window boundary judged by change-point, tolerance is generous on purpose."
```

Scoring: escapes = defective VINs not in the held set; precision/recall over VIN sets; decision-type match; window bound within tolerance; abstention correctness for `bench` and `contradictory`.
