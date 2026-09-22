// Small formatting helpers shared by the pages. Times are shown in the operator's local zone.
export const fmtTime = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

export function age(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

/** 0..1 of the approval window still left; null when there is no deadline. */
export function timeLeft(
  proposed: string,
  expires: string | null,
): number | null {
  if (!expires) return null;
  const a = new Date(proposed).getTime();
  const b = new Date(expires).getTime();
  return Math.min(1, Math.max(0, (b - Date.now()) / (b - a)));
}

/** ISO -> the value a datetime-local input wants (local time, minute precision). */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export const fromLocalInput = (v: string) =>
  v ? new Date(v).toISOString() : undefined;

export const pct = (v: number | null) =>
  v === null ? "—" : `${Math.round(v * 100)}%`;

export const money = (v: number | string | null | undefined) =>
  v === null || v === undefined ? "—" : `$${Number(v).toFixed(4)}`;
