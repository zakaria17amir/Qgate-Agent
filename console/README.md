# console

Approval console for the human gate. Four routes, talks only to `api`.

| Route | Purpose |
|---|---|
| `/queue` | PROPOSED and ESCALATED containments |
| `/case/:id` | Evidence: genealogy, siblings, drift chart, bench capability, draft order, VIN list |
| `/case/:id/decide` | Approve / Amend / Reject with reason |
| `/audit` | Agreement rate, widened vs narrowed, latency, cost per triage |

`src/api/` — typed client over `api`'s OpenAPI · `src/auth/` — JWT paste + role gate · `src/pages/` — one file per route · `src/components/` — shared widgets · `e2e/` — Playwright smoke (approve one case end to end).
