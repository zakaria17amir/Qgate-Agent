// Hand-written mirror of the api's rows (design §6.2). The api serves dict bodies, so a generated
// client would type everything as `object`; this file is smaller and says what matters.

export type State =
  | "PROPOSED"
  | "APPROVED"
  | "AMENDED"
  | "REJECTED"
  | "EXPIRED"
  | "COMMIT_PENDING"
  | "COMMITTED"
  | "ESCALATED";

export type Kind = "WINDOW" | "LOT" | "SINGLE" | "NONE";

export interface Visit {
  station_id: string;
  entered_at: string;
  shift_id: string;
  parts_lots: string[];
  out_of_tolerance: string[];
}

export interface Evidence {
  genealogy?: Visit[];
  hypotheses?: {
    station_id: string;
    characteristic_id: string;
    reasoning: string;
  }[];
  siblings?: {
    fault_code: string;
    station_id: string;
    vins: string[];
    entered_at: string[];
    by_shift: Record<string, number>;
    by_lot: Record<string, number>;
  };
  drift?: {
    verdict: "NONE" | "DRIFT" | "STEP";
    onset: string | null;
    changed_at: string | null;
    severity: string;
    confidence: number;
    evidence: Record<string, number>;
  };
  bench?: {
    bench_id: string;
    capable: boolean;
    grr_pct: number | null;
    bias_vs_peers: number | null;
    n_repeats: number;
    n_values: number;
    method: string;
  };
}

export interface Containment {
  containment_id: string;
  thread_id: string;
  state: State;
  kind: Kind;
  station_id: string | null;
  window_start: string | null;
  window_end: string | null;
  lot_ids: string[];
  vin_count: number;
  confidence: number | null;
  reason: string;
  draft_order: string | null;
  proposed_at: string;
  expires_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  mes_ref: string | null;
  trigger_vin: string | null;
  evidence: Evidence;
  vins: string[];
}

export interface Preview {
  vin_count: number;
  vins: string[];
}

export interface AuditRow {
  audit_id: number;
  containment_id: string;
  golden_id: string | null;
  decision: string; // PENDING | APPROVE | AMEND | REJECT | EXPIRED | ESCALATED
  actor: string;
  diff: Record<string, { from: unknown; to: unknown }>;
  latency_total_ms: number | null;
  latency_llm_ms: number | null;
  cost_usd: number | string | null;
  created_at: string;
}

export interface Amendment {
  window_start?: string;
  window_end?: string;
  lot_ids?: string[];
  station_id?: string;
  reason: string;
}
