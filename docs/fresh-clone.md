# Fresh clone — is the README true?

The Phase 6 test: clone, default `.env`, the README's commands, nothing else. **Run on
2026-09-23 on the author's laptop** (Windows 11, Docker Desktop 29.7 with 16 vCPU / 12 GB, Git
Bash + `make`), in a second checkout next to the working one, with the stack's volumes dropped
first (`make down`). It is the same machine that built the images before, so it is not a
stranger's machine — be the different one and open an issue if a step below does not hold.

## What was run

```bash
git clone <repo> fresh && cd fresh
cp .env.example .env                      # untouched: LLM_MODE=template, no API key
docker compose --profile core --profile demo build --no-cache   # measure a cold image build
make up
make demo                                 # tool_wear at 100x takt
make token ROLE=approver SUB=alice
curl -X POST -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
     -d '{"reason":"fresh-clone check"}' localhost:8000/containments/<id>/approve
```

## What happened

| Step | Result | Time |
|---|---|---|
| Cold build of all core + demo images (no layer cache; uv's download cache may have been warm) | 8 images, exit 0 | 8 min 22 s |
| `make up` (waits for every health check) | exit 0 | 28–56 s |
| `make demo` | `line-sim: scheduled 138624, delivered 138624, errors 0`; consumer lag 0 throughout | 20 min 34 s for the whole line |
| First failure (vehicle 992, ~11 min in) | **ESCALATED** — drift seen, no siblings yet (RUNBOOK §3) | |
| Next failures | 4 **PROPOSED** `WINDOW` at ST-19 within a minute of it, e.g. 79 vehicles | |
| Approve one through the api | `COMMITTED`, plant reference `HOLD-000001` | < 8 s |
| Console `http://localhost:8080` | served (200); the sign-in → decide path is the Playwright smoke in CI | |
| **Final run after the fixes below**, plain `make demo` | 892 EOL failures → 892 triages: 890 PROPOSED, 2 ESCALATED, **0 failed** | `make up` 59 s, demo 20 min 35 s |

## What needed a hand (and is now fixed)

Each of these was found by this test and fixed in the commit named, so the next clone does not
hit it:

1. **Postgres host port 5432 taken** by a local Postgres → default host port is now 15432
   (`fix(compose): Postgres host port defaults to 15432`).
2. **Empty queue without an API key** — the agent needed a model → template mode is the
   default (`feat(agent): template mode`).
3. **Agent crash-looped on the missing key** and `make up` returned 0 anyway → the provider
   client is built only when the mode calls it; `make up` waits for health
   (`fix(agent): start without a provider client…`).
4. **Dimensions never seeded outside the tests** → a `seed` one-shot in compose (and in the k3s
   Job).
5. **Every triage failed with "no end-of-line result"** when the line was replayed flat out: the
   agent's consumer read each failure before ingest had written it → the `genealogy` node waits
   up to 30 s for the row (`fix(agent): genealogy waits for ingest…`), and `make demo` defaults
   to 100× takt, where ingest keeps up. At `SPEED=0` ingest is minutes behind and the agent
   would triage on half-written genealogy — don't use it with the event trigger.
6. **6 of ~200 triages failed in `drift_check`** at 100× takt: the EOL row had landed, the EOL
   station's measurements (another topic) had not → the same wait also requires the last
   station's measurements (`fix(agent): genealogy also waits for the final station's…`).
