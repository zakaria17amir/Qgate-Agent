import type { State } from "./api/types";

const LABEL: Record<State, string> = {
  PROPOSED: "Waiting for decision",
  APPROVED: "Approved",
  AMENDED: "Amended",
  REJECTED: "Rejected",
  EXPIRED: "Expired",
  COMMIT_PENDING: "Approved, plant system unavailable",
  COMMITTED: "Committed",
  ESCALATED: "Escalated",
};

export const StateBadge = ({ state }: { state: State }) => (
  <span className="state" data-state={state}>
    {LABEL[state]}
  </span>
);

export const Loading = () => <p className="muted">Loading…</p>;

export const Problem = ({ error }: { error: unknown }) => (
  <p className="error" role="alert">
    {error instanceof Error ? error.message : "Request failed"}
  </p>
);
