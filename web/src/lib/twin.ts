// Family Twin: types, API calls and small helpers shared by the scene and the page.

import { api } from "./api";

export interface TwinPerson {
  id: string;
  name: string;
  sex: "female" | "male";
  mother: string | null;
  father: string | null;
  generation: number;
  deceased: boolean;
  status: "affected" | "unknown";
  affected_with?: string;
  test: { detected: string[] } | null;
}

export interface RaceEvent {
  person: string;
  carrier: boolean;
  detected: string[];
  via: string;
  couples_found: string[][];
  total_couples: number;
}

export interface TwinClan {
  locus_id: string;
  seed: number;
  index: string;
  parents: string[];
  people: TwinPerson[];
  unions: { a: string; b: string; kinship: number }[];
  consanguineous: string[][];
  race: { uptake: number; ranked: RaceEvent[]; family_order: RaceEvent[]; true_atrisk_couples: string[][] };
  note: string;
}

export interface WhatIf {
  status: "ok" | "inconsistent";
  ms: number;
  people_count?: number;
  p_carrier?: Record<string, number>;
  founders?: { id: string; p: number }[];
  next_best?: string[];
}

/** A recorded result: "carrier", "clear", or the variants found ("S", "B,B"). */
export type Result = string;

export const fetchClan = () => api<TwinClan>("/api/twin", { auth: false });
export const whatIf = (results: Record<string, Result>) =>
  api<WhatIf>("/api/twin/what-if", { body: { results }, auth: false });

/** Family-graph distance (parents, children, partners) from one person, for the ripple animation. */
export function distancesFrom(clan: TwinClan, start: string): Record<string, number> {
  const adj = new Map<string, Set<string>>();
  const link = (a: string, b: string) => {
    if (!adj.has(a)) adj.set(a, new Set());
    if (!adj.has(b)) adj.set(b, new Set());
    adj.get(a)!.add(b);
    adj.get(b)!.add(a);
  };
  for (const p of clan.people) {
    if (p.mother) link(p.id, p.mother);
    if (p.father) link(p.id, p.father);
  }
  for (const u of clan.unions) link(u.a, u.b);
  const dist: Record<string, number> = { [start]: 0 };
  const queue = [start];
  while (queue.length) {
    const x = queue.shift()!;
    for (const y of adj.get(x) || []) {
      if (dist[y] === undefined) {
        dist[y] = dist[x] + 1;
        queue.push(y);
      }
    }
  }
  return dist;
}

/** The line of descent from the index up to the ancestor most likely to carry the variant. */
export function originPath(clan: TwinClan, p: Record<string, number>): string[] {
  const byId = new Map(clan.people.map((x) => [x.id, x]));
  const path = [clan.index];
  let cur = byId.get(clan.index);
  while (cur && cur.mother && cur.father) {
    const m = byId.get(cur.mother)!;
    const f = byId.get(cur.father)!;
    const next = (p[m.id] ?? 0) >= (p[f.id] ?? 0) ? m : f;
    path.push(next.id);
    cur = next;
  }
  return path;
}

export function pct(p: number): string {
  if (p >= 0.9995) return "100%";
  if (p < 0.0005) return "<0.1%";
  return p < 0.1 ? `${(p * 100).toFixed(1)}%` : `${Math.round(p * 100)}%`;
}
