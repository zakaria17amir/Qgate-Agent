# Metrology notes — how `detect` judges a test bench

> Every figure below is an **assumption chosen for this synthetic line**, not a plant value.

## Why a bench needs judging at all

The agent's worst outcome is proposing a containment for a fault that lives in the test
equipment. A drifting end-of-line bench fails good cars; holding them is pure cost and hides
the real problem. So before any window is proposed, `detect` answers: *can this bench's
readings be trusted in this time window?*

## Two independent checks

| Check | Question | Statistic | Threshold (assumption) |
|---|---|---|---|
| Repeatability | Does the gauge agree with itself? | `%GRR = 6·σ_gauge / tolerance · 100`, σ_gauge pooled within-vehicle std of repeat readings (`repeat_no > 1`) | `< 30 %` acceptable (AIAG MSA convention: <10 good, 10–30 marginal, >30 unacceptable) |
| Bias vs peers | Does the gauge agree with any sibling *now*? | mean(own) − mean(**closest** peer bench) over the **most recent 100** readings each, half-tolerance units | `|bias| < 0.5` half-tolerance |

`capable = repeatable AND unbiased`. With fewer than 30 own readings the verdict is
`insufficient-data` and **not** capable — absence of evidence is not capability.

## Why bias-vs-peers rather than a reference standard

Proper MSA bias studies measure a certified reference part. This line has none; what it has
is three EOL benches that vehicles rotate through, so over any window of a few hundred cars
the three benches see statistically the same population. A bench whose mean reading departs
from its peers by half the tolerance band is therefore measuring *itself*, not the cars.

Limits of this reasoning, stated plainly:

- With a **single bench** there are no peers; only a reference-part check would work.
- The bias is taken against the *closest* peer, so one drifted bench cannot make a good bench
  look biased. The price: if two of three benches drifted **together**, the honest one would
  be blamed. The scenario set does not exercise this; a real plant adds a master-part check.
- With only **two** benches the rule cannot say which one moved; it only says they disagree.
- Peer comparison detects **bias**, not **linearity** or **stability** — the other MSA
  properties are out of scope here.

## What the generator does that makes this testable

- Every EOL bench has a `repeatability_sigma` (2–3 % of half-tolerance) and re-measures a
  5 % sample of vehicles twice more (`repeat_no = 2, 3`), so `%GRR` has data.
- The `bench_drift` scenario ramps **bias** on one bench only, leaving repeatability intact —
  exactly the failure that `%GRR` alone would miss and bias-vs-peers catches.
- Ground truth is defined on *true* values, so the eight `bench` goldens can assert that the
  right answer is to hold nothing.
