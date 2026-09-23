# Runbook — qgate-agent

Written for the person on shift, not for the developer. Each entry: what you see, what it means, what to do.

## Contents

0. Run the demo from the console (no terminal)
1. A containment is waiting for approval
2. A containment expired without a decision
3. The agent escalated without a proposal
4. The agent flagged a test bench instead of holding vehicles
5. "Approved, plant system unavailable" is shown
6. Kafka consumer lag is climbing
7. Restarting a service safely
8. Who to call
9. Is the system inside its targets? (SLOs)
10. Replaying a line (Prefect)
11. Seeing what the agent thought (Langfuse)

## 0. Run the demo from the console

Someone with a terminal does this once: `make up` then `make demo` (tool_wear at 100× takt), and
hands you a token (`make token ROLE=approver SUB=<your name>`).

1. Open `http://localhost:8080`. Click **Token** (bottom of the left rail), paste, **Use token**.
2. The **Queue** fills as vehicles fail end-of-line and the agent proposes containments. Each row
   shows the station, how many vehicles would be held, and a bar for the time left to decide.
3. Click a row. The case page shows what the agent saw: the draft order, the window with the
   failures marked on it, siblings by shift and lot, the vehicle's build path, the bench check,
   and the VIN list. Nothing has been sent to the plant yet.
4. **Decide** → Approve, Amend (move the window; the count on the right updates before you
   commit), or Reject (reason required). Submit.
5. The case shows **Committed** with the plant reference once the hold exists. **Audit** shows
   how often the proposals are accepted as-is, amended narrower or wider, and what each triage
   cost in time and model spend.

## 1. A containment is waiting for approval

**You see:** an amber *Waiting for decision* row in the Queue; the time-left bar is shrinking.
**It means:** a vehicle failed, the agent found a pattern and drafted a hold; nothing is held yet.
**Do:** open it, read the *Order* and *Window* tabs, decide. If you do nothing it expires (§2);
it never approves itself.

## 2. A containment expired without a decision

**You see:** red *Expired* on the case page, decided by `system`.
**It means:** nobody decided within the approval window (`APPROVAL_TIMEOUT_S`, default 30 min).
No hold was created.
**Do:** if the pattern is real, trigger it again from the api (`POST /triage` with the VIN) and
decide this time; raise the timeout if this keeps happening on a quiet shift.

## 3. The agent escalated without a proposal

**You see:** red *Escalated*, no vehicles, an explanation in the *Order* tab.
**It means:** the evidence contradicted itself (a gauge saw a change but no other vehicle failed),
so the agent asked for a person rather than guessing.
**Do:** read the explanation; check the station in person; if a hold is needed, place it in the
MES by hand and note it.

## 4. The agent flagged a test bench instead of holding vehicles

**You see:** *Escalated* with "Bench … is not capable" in the order.
**It means:** the end-of-line bench that failed the vehicle disagrees with its peers or repeats
badly; the vehicle's readings cannot be trusted, so holding upstream vehicles would be wrong.
**Do:** take the bench out of rotation and recalibrate; retest the vehicle on another bench.

## 5. "Approved, plant system unavailable" is shown

**You see:** a steel-blue *Approved, plant system unavailable* badge on a case you approved.
**It means:** your approval is recorded; the plant system (MES) did not answer. The agent retries
on its own: five attempts with backoff, then every 30 s once the connection is back. Nothing
is lost and the hold is never duplicated (the request carries the containment id as its
idempotency key).
**Do:** nothing for the first few minutes. If it persists, check the MES itself (§8). Do not
approve again — the api will refuse with 409 because the decision is already taken.

## 6. Kafka consumer lag is climbing

**You see:** the *Consumer lag* panel on the Grafana dashboard climbs (`kafka_consumer_lag`,
group `ingest`); `/ready` on `ingest` is fine but rows arrive late.
**It means:** the line is producing faster than ingest commits (~1 300 messages/s on one laptop:
one commit per message). A full 2 000-vehicle replay at full speed takes about two minutes to
drain.
**Do:** it drains on its own after a burst — watch the panel. If it never catches up, restart
`ingest` (§7); batching commits is the planned fix.

## 7. Restarting a service safely

Every service is safe to restart at any moment:

- `agent`: a proposal waiting at the gate lives in Postgres, not in the process. Kill it,
  start it, approve — one hold. (This is a chaos test: `make chaos-test`.)
- `api`: state is in Postgres; the console reconnects on its own.
- `ingest`, `detect-worker`: at-least-once with idempotent writes; duplicates are harmless.
- `line-sim`: stops scheduling on SIGTERM, flushes what it has produced, exits 0.

`docker compose --profile core restart <service>`; watch `/ready` (not `/health`) go green.

## 8. Who to call

- Plant system (MES) unreachable: the MES owner. The agent will finish the commit when it is back.
- Bench flagged not capable: metrology.
- Anything else: the on-call engineer; give them the containment id from the case page URL.

## 9. Is the system inside its targets? (SLOs)

Open Grafana (`make up-all`, `http://localhost:3000`, dashboard *qgate*). Four targets:

| Target | Where you see it | Over budget looks like |
|---|---|---|
| Proposal ready p95 ≤ 30 s (non-model part) | *SLO: non-LLM triage p95 < 30 s* | burn above 0.05: more than 1 in 20 triages in the last hour took longer |
| No event lost | *Ingest throughput* (DLQ line) and *Error rate* | DLQ line above zero: a message was rejected and parked; nothing silently dropped |
| Gate durability | *SLO: gate durability* | below 1.0: a decision was taken but no outcome (committed / rejected) followed |
| Exactly one hold per approval | *Plant system (MES): requests by status*, MES `/_stats` | `duplicate_replays` is expected after retries; a second hold for one containment is not |

**You see:** a burn panel turns red. **It means:** the target was missed in the last hour, not
right now. **Do:** check *Consumer lag* and *MES breaker state* first (§5, §6); if neither
explains it, call the on-call engineer (§8) with the panel screenshot.

## 10. Replaying a line (Prefect)

To rerun a scenario and check it landed, use the flow rather than a terminal command:
`make flows` once registers the three flows; then in Prefect (`http://localhost:4200`) open
*Deployments › replay-scenario › Run*, pick a scenario (e.g. `tool_wear`).

**You see:** the flow run ends *Completed* with a table of counts (manifest vs Postgres).
**It means:** every event the line produced is in the database. *Failed* on the count step means
ingest is behind or dropped something — see §6.
**Do:** nothing on success; the queue fills as in §1. On failure, attach the flow run link when
you call (§8).

## 11. Seeing what the agent thought (Langfuse)

Every triage is one trace: each step, each database/tool call and each model call with its
prompt, answer, tokens and time. Open Langfuse (`make up-all`, `http://localhost:3001`) and
search for the containment's `thread_id` (the case page URL has the containment id;
`GET /containments/{id}` at `http://localhost:8000/docs` returns its `thread_id`).

**You see:** a trace with `node.*`, `tool.*`, `llm.*` spans. **It means:** this is the evidence
behind the proposal, step by step. **Do:** use it when a proposal looks wrong — the `tool.*`
spans show what the data said, the `llm.*` spans what the model made of it.
