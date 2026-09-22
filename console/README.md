# console

Approval console for the human gate. Four routes, talks only to `api` (design §15, §6.6).

| Route | Purpose |
|---|---|
| `/queue` | PROPOSED and ESCALATED containments with time left to decide; polls every 5 s |
| `/case/:id` | Evidence tabs: draft order, window timeline (siblings, onset, trigger), siblings by shift/lot, build path, bench capability, VIN list |
| `/case/:id/decide` | Approve / Amend / Reject; amending previews the VIN count the new bounds would hold |
| `/audit` | Agreement rate, amended narrower vs wider, triage time p50/p95, model cost per triage |

Layout: `src/api/` hand-written types + fetch client · `src/auth/` JWT paste (sessionStorage) and
client-side role read · `src/pages/` one file per route · `src/audit/stats.ts` the audit maths ·
`src/tokens.css` the whole visual system · `e2e/` Playwright smoke.

## Run it

```sh
# against the compose stack (api on :8000, console on :8080)
make up            # then paste a token from `make token ROLE=approver SUB=alice`

# without compose: one golden waiting at the gate, real HTTP, throwaway Postgres
uv run qgate-eval serve --port 8010     # writes console/e2e/.tokens.json
cd console && VITE_API_BASE_URL=http://localhost:8010 npm run dev
```

## Test it

`make console-e2e` (or `cd console && npx playwright test`) starts `qgate-eval serve` and the
built console, then: a viewer sees the queue but cannot decide; an approver amends the window by
ten minutes, watches the preview shrink, submits, and sees the hold committed and the audit
counts one narrowed amendment. This is the CI `console` job.

Design notes: colour appears only on state (amber waiting, green committed, red rejected or
escalated); identifiers and timestamps are monospaced because scanning VIN columns is the job;
fonts are bundled because the plant network is offline.
