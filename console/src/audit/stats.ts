// Pure functions over audit rows; the Audit page renders what these return.
import type { AuditRow } from "../api/types";

const DECIDED = new Set(["APPROVE", "AMEND", "REJECT"]);

export interface Stats {
  decided: number;
  agreement: number | null; // approved unamended / decided
  widened: number;
  narrowed: number;
  p50: number | null;
  p95: number | null;
  costPerTriage: number | null;
}

export function stats(rows: AuditRow[]): Stats {
  const decided = rows.filter((r) => DECIDED.has(r.decision));
  const approved = decided.filter((r) => r.decision === "APPROVE").length;
  let widened = 0;
  let narrowed = 0;
  for (const r of decided.filter((r) => r.decision === "AMEND")) {
    const dir = direction(r.diff);
    if (dir === "widened") widened++;
    else if (dir === "narrowed") narrowed++;
  }
  const latencies = rows
    .map((r) => r.latency_total_ms)
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b);
  const costs = rows
    .map((r) => r.cost_usd)
    .filter((v) => v !== null && v !== undefined)
    .map(Number);
  return {
    decided: decided.length,
    agreement: decided.length ? approved / decided.length : null,
    widened,
    narrowed,
    p50: quantile(latencies, 0.5),
    p95: quantile(latencies, 0.95),
    costPerTriage: costs.length
      ? costs.reduce((a, b) => a + b, 0) / costs.length
      : null,
  };
}

/** From the recorded diff: did the human's window get bigger or smaller than the proposal's? */
export function direction(
  diff: AuditRow["diff"],
): "widened" | "narrowed" | "other" {
  const ws = diff.window_start;
  const we = diff.window_end;
  const startLater = ws
    ? new Date(String(ws.to)) > new Date(String(ws.from))
    : false;
  const startEarlier = ws
    ? new Date(String(ws.to)) < new Date(String(ws.from))
    : false;
  const endEarlier = we
    ? new Date(String(we.to)) < new Date(String(we.from))
    : false;
  const endLater = we
    ? new Date(String(we.to)) > new Date(String(we.from))
    : false;
  if ((startLater || endEarlier) && !startEarlier && !endLater)
    return "narrowed";
  if ((startEarlier || endLater) && !startLater && !endEarlier)
    return "widened";
  return "other";
}

export function quantile(sorted: number[], q: number): number | null {
  if (sorted.length === 0) return null;
  const i = Math.min(
    sorted.length - 1,
    Math.max(0, Math.ceil(q * sorted.length) - 1),
  );
  return sorted[i];
}
