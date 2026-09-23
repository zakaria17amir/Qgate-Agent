# Phase 6 — Ship Implementation Plan

> Execute with `executing-plans` (inline). TDD where a test is possible. Ponytail active.

**Goal:** A stranger clones the repo, runs one command, sees it work — and every skill the README claims has a link to a real artefact.

**Architecture:** Nothing new is built; what exists is made legible to three audiences. The README follows the design's fixed order (problem → dated numbers → diagram → one command → the gate → artefact links → ROI → runbook/ADRs/licence). The ROI is a small pure function with a test, so its figures are reproducible and every input is a labelled assumption. The k3s path is kustomize manifests generated from the same images and probes compose uses, exercised once on a local single-node cluster (k3d) and described as exactly that.

**Tech Stack:** Markdown, one Python module (`qgate_eval/roi.py`), kustomize, k3d/kubectl, Playwright for two screenshots, GitHub release.

**Spec:** design §12 (not-done list), §14 (README order, ROI), §16 (deployment story); checklist §Phase 6.

## Global Constraints

- Every ROI figure is an assumption and says so; no number is presented as a real plant figure (synthetic data throughout).
- No employer name, branding or private planning artefacts anywhere in public files.
- A skill is claimed only if a reviewer can open the artefact; PySpark is out of scope and is not claimed.
- The README says exactly how far each deployment target was exercised.

## Rulings taken while planning

- **ROI as code**: `roi.py` (≈40 lines) + `qgate-eval roi` prints the table the page quotes. Cost if wrong: one more CLI command. Gain: break-even and sensitivity cannot drift from the prose.
- **k3s exercised on k3d** (k3s inside Docker on this laptop), not a separate VM; the README says "single-node k3d on a laptop, once; not part of CI". If k3d cannot run here, the manifests are validated with `kubectl kustomize` + `kubeconform` and the README says *that*.
- **Fresh-clone test on a second checkout of this machine** with a default `.env`; the README says so and invites the reader to be the different machine.
- **Skill table is public and employer-neutral** (`docs/skills.md`): skill → artefact links → exercised how. No personal ratings.
- **Gate screenshots by Playwright** from `qgate-eval serve` (the same path the console e2e uses): case page with the pending proposal, decide page with the amend form.

## Review Focus

1. A README command that does not work on a clean checkout with `.env.example` — the fresh-clone run is the test (Task 5).
2. An ROI break-even that changes sign when the escape cost is halved must be visible in the sensitivity table, not hidden → Task 1 test spans the range.
3. k3s manifests that reference an image tag that does not exist on GHCR → Task 3 pulls them for real.
4. A skill row whose link 404s → Task 6 checks every relative link resolves.
5. `v1.0.0` release notes must carry the live evaluation report, not the replay baseline → Task 7 attaches `eval/report.md` from the last nightly (downloaded artifact).

---

### Task 1: ROI as a pure function
`qgate_eval/roi.py`: `Assumptions` (engineer minutes per manual triage, engineer hourly rate, minutes to review a proposal, agreement rate, escape probability without the agent vs with, escape cost, good vehicles held per over-wide containment × hold cost, triages per day, model cost per triage) → `roi(a) -> Result` (saving per triage, net per day, break-even agreement rate where review time equals time saved) and `sensitivity(a, escape_costs) -> list[Result]`. Tests: break-even is the agreement rate at which net = 0 (solved and checked numerically); halving the escape cost moves net monotonically; every field of `Assumptions` has a `note`. `qgate-eval roi` prints the tables; `docs/roi.md` quotes them with the assumptions table first, the plant-manager paragraph, and the sensitivity range.

### Task 2: README per §14
Rewrite top to bottom in the fixed order. Metrics table dated from the live nightly (`metrics.json` on Pages, 2026-09-23) with n; SLO table (design §12 spec) with measured values; the diagram; `make up && make demo`; two gate screenshots; "What a reviewer can open" — artefact links grouped by concern (not a skill list); ROI summary line linking `docs/roi.md`; deployment targets with how far each was exercised; explicitly-not-done security list; runbook, ADR index, licence. Checked: every relative link resolves (Task 6's script).

### Task 3: `infra/k3s/`
`kustomization.yaml`, `namespace.yaml`, `secrets.example.yaml` (SealedSecret placeholders + a plain `Secret` for the demo), `redpanda.yaml` + `postgres.yaml` (StatefulSets with PVCs), `migrate-job.yaml` (dbmate + roles), one `Deployment`+`Service` per service (`ingest`, `detect`, `detect-worker`, `agent`, `api`, `mock-mes`, `console`), probes from `/health`/`/ready`, images `ghcr.io/zakaria17amir/qgate-*:0.1.0-rc1`, `kustomize edit set image` documented for versions. Exercise: `k3d cluster create qgate`, `kubectl apply -k infra/k3s`, wait for rollouts, `kubectl port-forward` api, one `POST /triage` → proposal. `infra/k3s/README.md` records the exact commands and outcome.

### Task 4: RUNBOOK completeness
Sections 0–8 exist from Phase 4; add the SLO table's operator view (what "over budget" looks like on the dashboard), the Prefect flows as "how to replay a line" (§14 says flows are the documented way), and Langfuse ("where to see what the agent thought"). Every section keeps the you-see / it-means / do shape.

### Task 5: Fresh-clone test
`git clone` into a temp directory, `cp .env.example .env`, `make up`, `make demo SCENARIO=tool_wear SPEED=0`, `make token`, one triage through the api, open the console. Record the transcript's key lines in `docs/fresh-clone.md` (date, machine, elapsed, first-run image build time, anything that needed a hand). Fix whatever broke.

### Task 6: `docs/skills.md` + link check
Table: concern → artefacts (relative links) → how it was exercised (test / CI job / manual run with date). Out of scope stated (PySpark). `scripts/check_links.py` walks `README.md`, `docs/**/*.md`, `RUNBOOK.md` and fails on a relative link that does not resolve; wired into `make lint`.

### Task 7: `v1.0.0`
Update `CHANGELOG`? No — release notes are generated + `eval/report.md`. Tag on `main` after CI is green, watch `release.yml`, confirm nine images and the release with the live report attached (`gh release download`). Tick Gate 6.
