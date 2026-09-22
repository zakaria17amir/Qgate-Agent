import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { Loading, Problem } from "../components";
import { fromLocalInput, toLocalInput } from "../format";

type Action = "APPROVE" | "AMEND" | "REJECT";

/** Approve, amend or reject. Amending shows what the new bounds would hold before you commit. */
export function Decide() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["case", id],
    queryFn: () => api.containment(id),
  });

  const [action, setAction] = useState<Action>("APPROVE");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [lots, setLots] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const [debounced, setDebounced] = useState({ start, end, lots });

  useEffect(() => {
    if (q.data && !start && !end) {
      setStart(toLocalInput(q.data.window_start));
      setEnd(toLocalInput(q.data.window_end));
      setLots(q.data.lot_ids);
    }
  }, [q.data, start, end]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced({ start, end, lots }), 300);
    return () => clearTimeout(t);
  }, [start, end, lots]);

  const preview = useQuery({
    queryKey: ["preview", id, debounced],
    queryFn: () =>
      api.preview(id, {
        window_start: fromLocalInput(debounced.start),
        window_end: fromLocalInput(debounced.end),
        lot_ids: debounced.lots,
      }),
    enabled: action === "AMEND" && !!q.data,
  });

  const submit = useMutation({
    mutationFn: () => {
      if (action === "APPROVE") return api.approve(id, reason || undefined);
      if (action === "REJECT") return api.reject(id, reason);
      return api.amend(id, {
        window_start: fromLocalInput(start),
        window_end: fromLocalInput(end),
        lot_ids: q.data?.kind === "LOT" ? lots : undefined,
        reason,
      });
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["case", id] });
      await qc.invalidateQueries({ queryKey: ["queue"] });
      nav(`/case/${id}`);
    },
  });

  if (q.isPending) return <Loading />;
  if (q.error) return <Problem error={q.error} />;
  const c = q.data;
  const needsReason = action !== "APPROVE";
  const ready = !needsReason || reason.trim().length > 0;
  const conflict =
    submit.error instanceof ApiError && submit.error.status === 409;

  return (
    <>
      <header>
        <h1>
          Decide · <span className="mono">{c.station_id ?? "—"}</span>
        </h1>
      </header>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "2fr 1fr",
          gap: "var(--s-4)",
        }}
      >
        <form
          className="panel"
          onSubmit={(e) => {
            e.preventDefault();
            submit.mutate();
          }}
        >
          <fieldset>
            <legend>Decision</legend>
            {(["APPROVE", "AMEND", "REJECT"] as const).map((a) => (
              <label key={a}>
                <input
                  type="radio"
                  name="action"
                  value={a}
                  checked={action === a}
                  onChange={() => setAction(a)}
                />{" "}
                {a === "APPROVE"
                  ? "Approve"
                  : a === "AMEND"
                    ? "Amend"
                    : "Reject"}
              </label>
            ))}
          </fieldset>

          {c.kind === "WINDOW" && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "var(--s-3)",
              }}
            >
              <label className="field">
                <span>Window start</span>
                <input
                  type="datetime-local"
                  value={start}
                  disabled={action !== "AMEND"}
                  onChange={(e) => setStart(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Window end</span>
                <input
                  type="datetime-local"
                  value={end}
                  disabled={action !== "AMEND"}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </label>
            </div>
          )}
          {c.kind === "LOT" && (
            <label className="field">
              <span>Parts lots (comma-separated)</span>
              <input
                type="text"
                className="mono"
                value={lots.join(", ")}
                disabled={action !== "AMEND"}
                onChange={(e) =>
                  setLots(
                    e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  )
                }
              />
            </label>
          )}

          <label className="field">
            <span>Reason{needsReason ? "" : " (optional)"}</span>
            <textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required={needsReason}
            />
          </label>

          {conflict && (
            <p className="error" role="alert">
              Already decided by someone else. The case page shows who.
            </p>
          )}
          {submit.error && !conflict && <Problem error={submit.error} />}

          <div style={{ display: "flex", gap: "var(--s-2)" }}>
            <button
              className="btn"
              type="submit"
              disabled={!ready || submit.isPending}
            >
              Submit decision
            </button>
            <button
              className="btn quiet"
              type="button"
              onClick={() => nav(`/case/${id}`)}
            >
              Back to case
            </button>
          </div>
        </form>

        <aside className="panel" aria-live="polite">
          <span className="muted">Vehicles this decision holds</span>
          <div className="big" data-testid="preview-count">
            {action === "REJECT"
              ? 0
              : action === "AMEND"
                ? preview.data?.vin_count ?? "…"
                : c.vin_count}
          </div>
          <div className="muted">was {c.vin_count}</div>
          {action === "AMEND" && preview.error && (
            <Problem error={preview.error} />
          )}
          {action === "AMEND" && (
            <p className="muted" style={{ fontSize: "var(--fs-0)" }}>
              The failing vehicle <span className="mono">{c.trigger_vin}</span>{" "}
              stays held whatever the window.
            </p>
          )}
        </aside>
      </div>
    </>
  );
}
