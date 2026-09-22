import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Containment, Evidence } from "../api/types";
import { canDecide, claims } from "../auth/token";
import { Loading, Problem, StateBadge } from "../components";
import { fmtTime } from "../format";
import { scope } from "./Queue";

const TABS = [
  "Order",
  "Window",
  "Siblings",
  "Path",
  "Bench",
  "Vehicles",
] as const;

/** Everything the agent saw, arranged for a person who has to decide in a minute. */
export function Case() {
  const { id = "" } = useParams();
  const q = useQuery({
    queryKey: ["case", id],
    queryFn: () => api.containment(id),
    refetchInterval: (query) =>
      query.state.data?.state === "COMMIT_PENDING" ||
      query.state.data?.state === "APPROVED"
        ? 3000
        : false,
  });
  const [tab, setTab] = useState<(typeof TABS)[number]>("Order");
  const allowed = canDecide(claims());

  if (q.isPending) return <Loading />;
  if (q.error) return <Problem error={q.error} />;
  const c = q.data;
  const decidable = c.state === "PROPOSED";

  return (
    <>
      <header>
        <div>
          <h1>
            <span className="mono">{c.station_id ?? "No station"}</span> ·{" "}
            {scope(c.kind, c.lot_ids)}
          </h1>
          <p className="muted" style={{ margin: "var(--s-1) 0 0" }}>
            Triggered by <span className="mono">{c.trigger_vin ?? "—"}</span> ·
            proposed {fmtTime(c.proposed_at)}
            {c.decided_by && (
              <>
                {" "}
                · decided by <span className="mono">{c.decided_by}</span>{" "}
                {fmtTime(c.decided_at)}
              </>
            )}
            {c.mes_ref && (
              <>
                {" "}
                · plant ref <span className="mono">{c.mes_ref}</span>
              </>
            )}
          </p>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="big" data-testid="vin-count">
            {c.vin_count}
          </div>
          <div className="muted">vehicles held</div>
        </div>
      </header>

      <div
        style={{
          display: "flex",
          gap: "var(--s-3)",
          alignItems: "center",
          marginBottom: "var(--s-4)",
        }}
      >
        <StateBadge state={c.state} />
        {decidable && (
          <Link
            to={`/case/${id}/decide`}
            className="btn"
            aria-disabled={!allowed}
            tabIndex={allowed ? 0 : -1}
          >
            Decide
          </Link>
        )}
        {decidable && !allowed && (
          <span className="muted">
            Your token can view, not decide. Ask an approver.
          </span>
        )}
      </div>

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "Order" && <Order c={c} />}
        {tab === "Window" && <Window c={c} />}
        {tab === "Siblings" && <Siblings ev={c.evidence} />}
        {tab === "Path" && <Path ev={c.evidence} />}
        {tab === "Bench" && <Bench ev={c.evidence} />}
        {tab === "Vehicles" && <Vehicles vins={c.vins} />}
      </div>
    </>
  );
}

const Order = ({ c }: { c: Containment }) => (
  <div className="panel">
    <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>
      {c.draft_order ?? c.reason}
    </p>
    {c.draft_order && (
      <p className="muted" style={{ marginBottom: 0 }}>
        Evidence summary: {c.reason}
      </p>
    )}
  </div>
);

/** The one chart: the proposed window with every sibling's station entry and the drift onset. */
function Window({ c }: { c: Containment }) {
  const d = c.evidence.drift;
  const sib = c.evidence.siblings;
  const trigger = c.evidence.genealogy?.find(
    (v) => v.station_id === c.station_id,
  )?.entered_at;
  const times = [
    c.window_start,
    c.window_end,
    d?.onset,
    trigger,
    ...(sib?.entered_at ?? []),
  ].filter((t): t is string => !!t);
  if (times.length < 2)
    return (
      <p className="empty">
        No time window for this proposal ({scope(c.kind, c.lot_ids)}).
      </p>
    );
  const ms = times.map((t) => new Date(t).getTime());
  const lo = Math.min(...ms);
  const hi = Math.max(...ms);
  const pad = (hi - lo) * 0.05 || 60_000;
  const x = (t: string) =>
    20 + ((new Date(t).getTime() - (lo - pad)) / (hi - lo + 2 * pad)) * 760;

  return (
    <>
      <svg
        className="timeline"
        viewBox="0 0 800 96"
        role="img"
        aria-label="Containment window"
      >
        {c.window_start && c.window_end && (
          <rect
            className="window"
            x={x(c.window_start)}
            y={20}
            width={Math.max(2, x(c.window_end) - x(c.window_start))}
            height={40}
          />
        )}
        <line x1={20} x2={780} y1={60} y2={60} className="tick" />
        {sib?.entered_at.map((t, i) => (
          <line key={i} className="tick" x1={x(t)} x2={x(t)} y1={44} y2={60} />
        ))}
        {d?.onset && (
          <line
            className="onset"
            x1={x(d.onset)}
            x2={x(d.onset)}
            y1={12}
            y2={68}
          />
        )}
        {trigger && (
          <line
            className="trigger"
            x1={x(trigger)}
            x2={x(trigger)}
            y1={12}
            y2={68}
          />
        )}
        <text x={x(c.window_start ?? times[0])} y={86}>
          {fmtTime(c.window_start ?? times[0])}
        </text>
        <text
          x={x(c.window_end ?? times[times.length - 1])}
          y={86}
          textAnchor="end"
        >
          {fmtTime(c.window_end ?? times[times.length - 1])}
        </text>
      </svg>
      <table style={{ marginTop: "var(--s-3)" }}>
        <tbody>
          <tr>
            <th>Window</th>
            <td>
              {fmtTime(c.window_start)} → {fmtTime(c.window_end)}
            </td>
          </tr>
          <tr>
            <th>Drift verdict</th>
            <td>
              {d
                ? `${d.verdict} · ${d.severity} · confidence ${Math.round(
                    d.confidence * 100,
                  )}%`
                : "—"}
            </td>
          </tr>
          <tr>
            <th>Estimated onset</th>
            <td>{fmtTime(d?.onset)} (red line)</td>
          </tr>
          <tr>
            <th>Sibling failures</th>
            <td>{sib?.vins.length ?? 0} (ticks) · trigger in black</td>
          </tr>
        </tbody>
      </table>
    </>
  );
}

function Siblings({ ev }: { ev: Evidence }) {
  const s = ev.siblings;
  if (!s || s.vins.length === 0)
    return (
      <p className="empty">
        No other vehicle failed with this code in the window.
      </p>
    );
  const counts = (m: Record<string, number>) =>
    Object.entries(m)
      .sort((a, b) => b[1] - a[1])
      .map(([k, n]) => (
        <tr key={k}>
          <td className="mono">{k}</td>
          <td className="num">{n}</td>
        </tr>
      ));
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "var(--s-3)",
      }}
    >
      <table>
        <thead>
          <tr>
            <th>By shift</th>
            <th className="num">Failures</th>
          </tr>
        </thead>
        <tbody>{counts(s.by_shift)}</tbody>
      </table>
      <table>
        <thead>
          <tr>
            <th>By parts lot</th>
            <th className="num">Failures</th>
          </tr>
        </thead>
        <tbody>{counts(s.by_lot)}</tbody>
      </table>
    </div>
  );
}

function Path({ ev }: { ev: Evidence }) {
  const g = ev.genealogy ?? [];
  if (g.length === 0) return <p className="empty">No build path recorded.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>Station</th>
          <th>Entered</th>
          <th>Shift</th>
          <th>Parts lots</th>
          <th>Out of tolerance</th>
        </tr>
      </thead>
      <tbody>
        {g.map((v) => (
          <tr key={v.station_id}>
            <td className="mono">{v.station_id}</td>
            <td>{fmtTime(v.entered_at)}</td>
            <td className="mono">{v.shift_id}</td>
            <td className="mono">{v.parts_lots.join(", ") || "—"}</td>
            <td className={v.out_of_tolerance.length ? "error mono" : "muted"}>
              {v.out_of_tolerance.join(", ") || "in tolerance"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Bench({ ev }: { ev: Evidence }) {
  const b = ev.bench;
  if (!b) return <p className="empty">No bench assessment.</p>;
  return (
    <table>
      <tbody>
        <tr>
          <th>Test bench</th>
          <td className="mono">{b.bench_id}</td>
        </tr>
        <tr>
          <th>Capable</th>
          <td>
            {b.capable
              ? "Yes — readings can be trusted"
              : "No — recalibrate before trusting"}
          </td>
        </tr>
        <tr>
          <th>%GRR</th>
          <td>{b.grr_pct === null ? "—" : `${b.grr_pct.toFixed(1)}%`}</td>
        </tr>
        <tr>
          <th>Bias vs peer benches</th>
          <td>{b.bias_vs_peers === null ? "—" : b.bias_vs_peers.toFixed(3)}</td>
        </tr>
        <tr>
          <th>Basis</th>
          <td>
            {b.n_values} readings, {b.n_repeats} repeats · {b.method}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

const Vehicles = ({ vins }: { vins: string[] }) =>
  vins.length === 0 ? (
    <p className="empty">No vehicles would be held.</p>
  ) : (
    <div
      className="panel mono"
      style={{ columns: "4 180px", fontSize: "var(--fs-0)", lineHeight: 1.7 }}
    >
      {vins.map((v) => (
        <div key={v}>{v}</div>
      ))}
    </div>
  );
