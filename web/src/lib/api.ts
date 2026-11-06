// Thin client for the Silsila API. The token lives in memory and in
// sessionStorage (cleared when the tab closes). No other storage is used.

import type { User } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const KEY = "silsila.session";

export interface Session {
  token: string;
  user: User;
}

let session: Session | null = null;
let loaded = false;
const listeners = new Set<() => void>();

function load(): void {
  if (loaded || typeof window === "undefined") return;
  loaded = true;
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (raw) session = JSON.parse(raw) as Session;
  } catch {
    session = null;
  }
}

export function getSession(): Session | null {
  load();
  return session;
}

export function setSession(s: Session | null): void {
  session = s;
  loaded = true;
  try {
    if (s) window.sessionStorage.setItem(KEY, JSON.stringify(s));
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: keep the in-memory copy */
  }
  listeners.forEach((l) => l());
}

export function subscribeSession(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Query = Record<string, string | number | boolean | undefined | null>;

export function url(path: string, query?: Query): string {
  const u = new URL(API_URL + path);
  for (const [k, v] of Object.entries(query || {})) {
    if (v !== undefined && v !== null) u.searchParams.set(k, String(v));
  }
  return u.toString();
}

export async function api<T>(
  path: string,
  opts: { method?: string; body?: unknown; query?: Query; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const s = getSession();
  if (opts.auth !== false && s) headers.Authorization = `Bearer ${s.token}`;
  let res: Response;
  try {
    res = await fetch(url(path, opts.query), {
      method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail)) detail = j.detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && s && opts.auth !== false) setSession(null);
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}
