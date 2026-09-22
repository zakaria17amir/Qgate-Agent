import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { stats } from "../audit/stats";
import { Loading, Problem } from "../components";
import { fmtTime, money, pct } from "../format";

/** How the agent and the people are doing together: agreement, amendments, time, cost. */
export function Audit() {
  const q = useQuery({ queryKey: ["audit"], queryFn: api.audit });
  if (q.isPending) return <Loading />;
  if (q.error) return <Problem error={q.error} />;
  const s = stats(q.data);

  return (
    <>
      <header>
        <h1>Audit</h1>
        <span className="muted">last {q.data.length} triages</span>
      </header>
      <div className="stats">
        <div className="panel">
          <span>Approved as proposed</span>
          <strong data-testid="agreement-rate">{pct(s.agreement)}</strong>
          <span>{s.decided} decided</span>
        </div>
        <div className="panel">
          <span>Amended narrower</span>
          <strong data-testid="narrowed">{s.narrowed}</strong>
          <span>{s.widened} widened</span>
        </div>
        <div className="panel">
          <span>Triage time p50 / p95</span>
          <strong>
            {s.p50 === null ? "—" : `${(s.p50 / 1000).toFixed(1)} s`}
            {s.p95 === null ? "" : ` / ${(s.p95 / 1000).toFixed(1)} s`}
          </strong>
          <span>proposal ready, model included</span>
        </div>
        <div className="panel">
          <span>Model cost per triage</span>
          <strong>{money(s.costPerTriage)}</strong>
          <span>price table is an assumption</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Decision</th>
            <th>By</th>
            <th>Changed</th>
            <th className="num">Time</th>
            <th className="num">Cost</th>
          </tr>
        </thead>
        <tbody>
          {q.data.slice(0, 50).map((r) => (
            <tr key={r.audit_id}>
              <td>
                <Link to={`/case/${r.containment_id}`}>
                  {fmtTime(r.created_at)}
                </Link>
              </td>
              <td>{r.decision}</td>
              <td className="mono">{r.actor}</td>
              <td className="mono muted">
                {Object.keys(r.diff).join(", ") || "—"}
              </td>
              <td className="num">
                {r.latency_total_ms === null
                  ? "—"
                  : `${(r.latency_total_ms / 1000).toFixed(1)} s`}
              </td>
              <td className="num">{money(r.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
