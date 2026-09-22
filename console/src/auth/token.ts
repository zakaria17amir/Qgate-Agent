// The JWT lives in sessionStorage (design §6.6): pasted once per browser session, gone on close.
// The role is read client-side only to shape the UI; the api enforces it.
const KEY = "qgate.token";

export function getToken(): string | null {
  return sessionStorage.getItem(KEY);
}

export function setToken(token: string | null): void {
  if (token) sessionStorage.setItem(KEY, token.trim());
  else sessionStorage.removeItem(KEY);
  window.dispatchEvent(new Event("qgate-token"));
}

export interface Claims {
  sub: string;
  role: "viewer" | "approver" | "admin" | "service";
  exp: number;
}

export function claims(token: string | null = getToken()): Claims | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload)) as Claims;
  } catch {
    return null;
  }
}

export function canDecide(c: Claims | null): boolean {
  return c?.role === "approver" || c?.role === "admin";
}
