import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Loading, Problem, StateBadge } from "../components";
import { age, pct, timeLeft } from "../format";

/** What needs a person: proposals waiting at the gate and escalations. Polls every 5 s. */
export function Queue() {
  const nav = useNavigate();
  const q = useQuery({
    queryKey: ["queue"],
    queryFn: api.queue,
    refetchInterval: 5000,
  });

  return (
    <>
      <header>
        <h1>Queue</h1>
        <span className="muted">
          {q.data ? `${q.data.length} waiting` : ""}
        </span>
      </header>
      {q.isPending && <Loading />}
      {q.error && <Problem error={q.error} />}
      {q.data && q.data.length === 0 && (
        <p className="empty">
          Nothing waiting. Failures that need a decision appear here.
        </p>
      )}
      {q.data && q.data.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Station</th>
              <th>Scope</th>
              <th className="num">Vehicles</th>
              <th className="num">Confidence</th>
              <th>Age</th>
              <th>Time left</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((c) => {
              const left = timeLeft(c.proposed_at, c.expires_at);
              return (
                <tr
                  key={c.containment_id}
                  data-href
                  tabIndex={0}
                  onClick={() => nav(`/case/${c.containment_id}`)}
                  onKeyDown={(e) =>
                    e.key === "Enter" && nav(`/case/${c.containment_id}`)
                  }
                >
                  <td className="mono">{c.station_id ?? "—"}</td>
                  <td>{scope(c.kind, c.lot_ids)}</td>
                  <td className="num">{c.vin_count}</td>
                  <td className="num">{pct(c.confidence)}</td>
                  <td>{age(c.proposed_at)}</td>
                  <td>
                    {left === null ? (
                      <span className="muted">—</span>
                    ) : (
                      <div
                        className="expiry"
                        data-late={left < 0.2}
                        role="meter"
                        aria-valuenow={Math.round(left * 100)}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label="Time left to decide"
                      >
                        <span style={{ width: `${left * 100}%` }} />
                      </div>
                    )}
                  </td>
                  <td>
                    <StateBadge state={c.state} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}

export function scope(kind: string, lots: string[]): string {
  switch (kind) {
    case "WINDOW":
      return "Time window";
    case "LOT":
      return `Parts lot ${lots.join(", ")}`;
    case "SINGLE":
      return "This vehicle only";
    default:
      return "No hold proposed";
  }
}
