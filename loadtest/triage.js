// Load: 5 shift leaders' worth of failures, then a burst of 50, against the api of a running stack.
// Each iteration is one failure end to end: POST /triage -> proposal appears -> approve -> COMMITTED.
// The agent runs in replay mode (cassettes), so the model's own latency is excluded and no provider
// is billed; docs/latency.md says what each number covers.
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Counter } from "k6/metrics";

const CASE = JSON.parse(open("./case.json")); // written by loadtest/prepare.py
const API = __ENV.API_URL || "http://api:8000";
const H = {
  headers: {
    Authorization: `Bearer ${CASE.token}`,
    "Content-Type": "application/json",
  },
};

export const triageToProposal = new Trend("triage_to_proposal_ms", true);
export const approveToCommitted = new Trend("approve_to_committed_ms", true);
export const failures = new Counter("iteration_failures");

export const options = {
  summaryTrendStats: ["med", "p(90)", "p(95)", "p(99)", "max"],
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      startTime: "0s",
    },
    burst: {
      executor: "constant-vus",
      vus: 50,
      duration: "30s",
      startTime: "2m",
    },
    tail: {
      executor: "constant-vus",
      vus: 5,
      duration: "1m",
      startTime: "2m30s",
    },
  },
  thresholds: {
    triage_to_proposal_ms: ["p(95)<30000"],
    approve_to_committed_ms: ["p(95)<10000"],
    iteration_failures: ["count<5"],
  },
};

function pollUntil(pred, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const v = pred();
    if (v) return v;
    sleep(0.5);
  }
  return null;
}

export default function () {
  const t0 = Date.now();
  const started = http.post(
    `${API}/triage`,
    JSON.stringify({ vin: CASE.vin, fault_codes: CASE.fault_codes }),
    H,
  );
  if (!check(started, { "triage accepted": (r) => r.status === 202 })) {
    failures.add(1);
    return;
  }
  const tid = started.json("thread_id");

  const proposal = pollUntil(() => {
    const rows = http.get(`${API}/containments?thread_id=${tid}`, H).json();
    return rows.length ? rows[0] : null;
  }, 120000);
  if (!proposal) {
    failures.add(1);
    return;
  }
  triageToProposal.add(Date.now() - t0);
  if (proposal.state !== "PROPOSED") return; // an escalation has nothing to approve

  const t1 = Date.now();
  const ok = http.post(
    `${API}/containments/${proposal.containment_id}/approve`,
    JSON.stringify({}),
    H,
  );
  if (!check(ok, { "approve 200": (r) => r.status === 200 })) {
    failures.add(1);
    return;
  }
  const done = pollUntil(() => {
    const row = http
      .get(`${API}/containments/${proposal.containment_id}`, H)
      .json();
    return row.state === "COMMITTED" ? row : null;
  }, 60000);
  if (!done) {
    failures.add(1);
    return;
  }
  approveToCommitted.add(Date.now() - t1);
}
