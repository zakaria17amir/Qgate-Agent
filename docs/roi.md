# ROI — for the plant manager, with every figure labelled

> **Everything on this page is an assumption unless the row says MEASURED.** The system runs on
> a synthetic line; no number here is a real plant figure. The point of the page is the *shape*
> of the argument and the break-even, not the totals. Regenerate the tables with
> `uv run qgate-eval roi`; the model is `eval/harness/qgate_eval/roi.py` and has tests.

## The argument in one paragraph

When a vehicle fails end-of-line test, a quality engineer decides how many vehicles to quarantine.
The agent does the correlation work (genealogy, siblings by shift and lot, gauge drift, bench
capability) and proposes a bounded containment; a person approves, amends or rejects it. Two
things change: the engineer reviews instead of investigates, and the window is bounded by the
drift onset instead of by caution. The second matters far more than the first — and it is the
part that rests on assumptions nobody has measured, so the sensitivity table is the honest
centre of this page.

## Assumptions and results

| Assumption | Value | Where it comes from |
|---|---|---|
| `manual_triage_min` | 25 | Minutes a quality engineer spends pulling genealogy, siblings and gauge history by hand before deciding. Assumed; interview any EOL engineer for theirs. |
| `review_min` | 4 | Minutes to read a proposal (order, window, siblings, bench) and decide. Assumed from the console's case page; the audit table records the real value. When the reviewer amends or rejects, the manual triage is assumed to happen as well (conservative). |
| `engineer_eur_per_h` | 70 | Loaded hourly cost of a quality engineer. Assumed; a round number. |
| `agreement_rate` | 0.66 | Share of proposals approved unamended. MEASURED on the fifty goldens (eval baseline, 2026-09-22): 0.66. The one number here that is not assumed. |
| `triages_per_day` | 12 | EOL failures needing a containment decision per day on one line. Assumed for a ~1 000-vehicle/day line at ~1 % first-pass fail. |
| `escape_rate_manual` | 0.02 | Probability a manual decision lets a defective vehicle escape (too-narrow window). Assumed; nobody publishes this. |
| `escape_rate_agent` | 0.01 | Same with the agent's proposal reviewed by a human. Assumed at half: the goldens show recall 0.96 on non-overlap families, but that is synthetic. |
| `escape_cost_eur` | 50000 | Cost of one escape reaching a customer: field action, warranty, reputation. The number nobody knows — see the sensitivity table. |
| `good_vehicles_held_manual` | 40 | Good vehicles quarantined per containment decided by hand (wide windows to be safe). Assumed. |
| `good_vehicles_held_agent` | 25 | Same with a bounded window from drift onset. Assumed from the goldens' precision 0.59 — it is not dramatically tighter, and says so. |
| `hold_cost_per_vehicle_eur` | 60 | Cost of holding and re-inspecting one good vehicle. Assumed. |
| `model_cost_per_triage_eur` | 0.0031 | MEASURED: mean model spend per triage from the live runs ($0.0031, price table is itself an assumption). |

| Result (per day, one line) | EUR |
|---|---|
| Engineer time saved (12.5 min per triage) | 175 |
| Escapes avoided (expected value) | 6,000 |
| Fewer good vehicles held | 10,800 |
| Model spend | -0.04 |
| **Net** | **16,975** |

Break-even agreement rate on engineer time alone: **0.16** (review / manual minutes); on the full net: **0.00** (0 = the escape and hold terms pay for it at any rate). Measured today: 0.66.

| Escape cost (EUR) | Escapes avoided / day | Net / day |
|---|---|---|
| 5,000 | 600 | 11,575 |
| 25,000 | 3,000 | 13,975 |
| 50,000 | 6,000 | 16,975 |
| 100,000 | 12,000 | 22,975 |
| 500,000 | 60,000 | 70,975 |

## Reading the numbers

- **Engineer time is the small term.** Even at the measured agreement rate of 0.66 the time saved
  is ~12 minutes per triage, ~175 EUR/day on one line.
  On time alone the agent pays for itself above an agreement rate of 0.16 (review minutes /
  manual minutes): a proposal only has to be right one time in six for the review to be cheaper
  than the investigation. The measured 0.66 clears that by a wide margin, on synthetic data.
- **Holds and escapes are the large terms, and both are assumed.** If the agent's window were no
  tighter than a manual one (`good_vehicles_held_agent = 40`), the net drops to
  ~6,175 EUR/day — almost entirely the expected value of avoided escapes, which
  rests on an escape probability that nobody publishes and an escape cost that varies by two orders
  of magnitude between "found at the dealer" and "field action". Hence the range 5 000 – 500 000.
- **The model is free at this scale.** ~0.003 EUR per triage; the whole day's spend rounds to
  zero against any other row. Cost is not the objection to this system; trust is.

## What would turn this page into a plant figure

Three numbers, all recorded by the system as built: the real review time per proposal (the audit
table stores `decided_at − proposed_at`), the real agreement and amendment rates (same table),
and the real width difference between manual and proposed windows (the audit `diff`). Run it in
shadow mode for a month next to the current process and replace the assumed rows with the
measured ones. The escape cost stays an assumption; that is why it is a range.
