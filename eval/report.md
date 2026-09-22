# Evaluation — 50 goldens (replay, claude-haiku-4-5, 2026-09-22)

| Metric | Value |
|---|---|
| Escapes | **260** |
| Containment precision / recall | 0.59 / 0.96 |
| Decision match | 0.96 |
| Agreement rate (approved unamended) | 0.66 |
| Abstention correct rate | 1.00 |
| Latency p50 / p95 (total) | 106 / 113 ms |
| Latency p95 (LLM only / non-LLM) | 1 / 113 ms |
| Cost per triage | 0.003289 USD (assumption) |

| Family | Cases | Escapes | Precision | Recall | Decision match |
|---|---|---|---|---|---|
| bench | 8 | 0 | 1.00 | 1.00 | 1.00 |
| contradictory | 6 | 0 | 1.00 | 1.00 | 1.00 |
| drift | 12 | 0 | 0.09 | 1.00 | 1.00 |
| isolated | 12 | 0 | 1.00 | 1.00 | 1.00 |
| lot | 8 | 0 | 0.16 | 1.00 | 1.00 |
| overlap | 4 | 260 | 0.33 | 0.51 | 0.50 |
