# Evaluation — how the numbers in the README are computed

> Synthetic data throughout. Every metric here is over the fifty golden cases (tag `goldens-v1.1`),
> not a plant. Definitions are chosen so that the failure mode that costs money — an escape —
> is counted first and cannot be hidden by averaging.

## Per case

A golden names a scenario, a seed and the vehicle whose end-of-line failure starts the triage.
The run is regenerated, loaded, and the agent is triggered at that vehicle's EOL time. The
harness then acts as the golden's *human*: it approves, amends or rejects through the same
public api endpoint a shift leader would use (ADR-003: no bypass exists).

| Term | Definition |
|---|---|
| **affected** | Vehicles the correct containment should hold *at trigger time*: the scenario's injected defectives (`truth.by_inject`) built up to and including the trigger, plus the trigger itself for `SINGLE`. Empty for `NONE` and `ESCALATE`. Base-rate random defects elsewhere on the line are not "affected" — no containment of this station could reach them. |
| **held** | Vehicles in the containment as committed to the plant system (after any amendment). Empty when the agent abstained or the human rejected. When the golden's human **rejects**, escapes and recall are computed on what the agent *proposed*: the rejection is the human's decision and the agent is judged on its offer. |
| **escapes** | `|affected − held|` — affected vehicles that would leave the plant. |
| **precision** | `|affected ∩ held| / |held|`; 1.0 when both are empty. |
| **recall** | `|affected ∩ held| / |affected|`; 1.0 when both are empty. |
| **decision match** | The agent's containment kind equals the golden's expected decision (`MULTI` counts as matched when a lot containment is proposed and the drift is also reported). |
| **abstention correct** | The agent proposed nothing **and** nothing should have been held. |
| **approved unamended** | The human's action was `APPROVE`. Amend and reject both count against agreement. |
| **latency** | `latency_total_ms` from the audit row: first node start to `report`, wall clock, one host. `latency_llm_ms` is the share inside model calls. |
| **cost** | From token usage × the price table in `qgate_core/pricing.py` (an assumption, dated). In `replay` mode the usage is the recorded one. |

## Across cases

| Metric | Aggregation |
|---|---|
| Escapes | **sum** — never averaged |
| Precision / recall | mean over cases |
| Decision match | share of cases |
| Agreement rate | share of cases approved unamended |
| Abstention correct rate | correct abstentions / cases where the expected decision is `NONE` or `ESCALATE` |
| Latency p50 / p95 | percentiles over cases, total and LLM-only |
| Cost per triage | mean |

## The CI gate

`make eval-replay` runs the fifty cases with recorded model answers and compares to
`eval/baseline.json`. The build fails if **escapes rise** or **non-LLM p95 latency** grows more
than 20 %. Bumping the baseline is a deliberate commit with a reason in its message.

## What this does not measure

Real operator behaviour (the "human" is scripted), model drift over time (the nightly `live`
run does that), and anything about detection — the agent starts after a failure is known.
