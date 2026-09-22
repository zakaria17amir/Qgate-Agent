// The only network code: fetch with the pasted token; errors carry the status so pages can say
// "already decided" (409) or "not allowed" (403) instead of "something went wrong".
import { getToken } from "../auth/token";
import type { Amendment, AuditRow, Containment, Preview } from "./types";

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON body: keep the status text */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  queue: () => call<Containment[]>("/containments?state=PROPOSED,ESCALATED"),
  containment: (id: string) => call<Containment>(`/containments/${id}`),
  preview: (
    id: string,
    q: { window_start?: string; window_end?: string; lot_ids?: string[] },
  ) => {
    const p = new URLSearchParams();
    if (q.window_start) p.set("window_start", q.window_start);
    if (q.window_end) p.set("window_end", q.window_end);
    if (q.lot_ids?.length) p.set("lot_ids", q.lot_ids.join(","));
    return call<Preview>(`/containments/${id}/preview?${p}`);
  },
  approve: (id: string, reason?: string) =>
    call<Containment>(`/containments/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  amend: (id: string, body: Amendment) =>
    call<Containment>(`/containments/${id}/amend`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  reject: (id: string, reason: string) =>
    call<Containment>(`/containments/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  audit: () => call<AuditRow[]>("/audit"),
};
