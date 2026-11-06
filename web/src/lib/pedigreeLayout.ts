// Generation-based layout for a pedigree diagram.
//
// 1. Generation: founders start at 0; everyone else is one below their
//    deeper parent. A founder who married into the family takes their
//    partner's generation; founders with children sit one above them.
// 2. Order within a generation: couples are kept side by side and blocks are
//    sorted by the position of their parents above.
// 3. A bottom-up pass centres parents over their children where space allows.

import type { Pedigree, PedPerson } from "./types";

export interface LayoutCouple {
  a: string;
  b: string;
  children: string[];
}

export interface Layout {
  x: Record<string, number>; // slot units
  gen: Record<string, number>; // 0-based row
  rows: string[][];
  couples: LayoutCouple[];
  width: number; // slot units
  depth: number; // rows
}

const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`);

export function layoutPedigree(ped: Pedigree): Layout {
  const people = ped.people;
  const byId = new Map<string, PedPerson>(people.map((p) => [p.id, p]));
  const hasParents = (id: string) => {
    const p = byId.get(id);
    return !!(p && p.mother && p.father && byId.has(p.mother) && byId.has(p.father));
  };

  // couples: explicit unions + co-parents
  const coupleMap = new Map<string, LayoutCouple>();
  const addCouple = (a: string, b: string) => {
    if (!byId.has(a) || !byId.has(b) || a === b) return;
    const k = pairKey(a, b);
    if (!coupleMap.has(k)) coupleMap.set(k, { a, b, children: [] });
    return coupleMap.get(k)!;
  };
  for (const p of people) {
    if (p.mother && p.father) {
      const c = addCouple(p.mother, p.father);
      if (c) c.children.push(p.id);
    }
  }
  for (const u of ped.unions || []) addCouple(u.a, u.b);
  const couples = [...coupleMap.values()];
  const partners = new Map<string, string[]>();
  for (const c of couples) {
    partners.set(c.a, [...(partners.get(c.a) || []), c.b]);
    partners.set(c.b, [...(partners.get(c.b) || []), c.a]);
  }
  const children = new Map<string, string[]>();
  for (const p of people) {
    for (const par of [p.mother, p.father]) {
      if (par && byId.has(par)) children.set(par, [...(children.get(par) || []), p.id]);
    }
  }

  // ---- generations
  const gen: Record<string, number> = {};
  for (const p of people) gen[p.id] = 0;
  for (let iter = 0; iter < 50; iter++) {
    let changed = false;
    const set = (id: string, g: number) => {
      if (gen[id] !== g) {
        gen[id] = g;
        changed = true;
      }
    };
    for (const p of people) {
      if (hasParents(p.id)) set(p.id, Math.max(gen[p.mother!], gen[p.father!]) + 1);
    }
    for (const c of couples) {
      const [lo, hi] = gen[c.a] <= gen[c.b] ? [c.a, c.b] : [c.b, c.a];
      if (gen[lo] < gen[hi] && !hasParents(lo)) set(lo, gen[hi]);
    }
    for (const p of people) {
      if (hasParents(p.id)) continue;
      const kids = children.get(p.id) || [];
      if (kids.length) {
        const want = Math.min(...kids.map((k) => gen[k])) - 1;
        if (want > gen[p.id]) set(p.id, want);
      }
    }
    if (!changed) break;
  }
  const minGen = Math.min(...Object.values(gen), 0);
  for (const id of Object.keys(gen)) gen[id] -= minGen;
  const depth = Math.max(0, ...Object.values(gen)) + 1;

  // ---- order within rows
  const x: Record<string, number> = {};
  const rows: string[][] = [];
  const blocksByRow: string[][][] = [];
  for (let g = 0; g < depth; g++) {
    const inRow = people.filter((p) => gen[p.id] === g).map((p) => p.id);
    const placed = new Set<string>();
    const blocks: { ids: string[]; key: number; order: number }[] = [];
    const parentCentre = (id: string) => {
      const p = byId.get(id)!;
      return hasParents(id) ? (x[p.mother!] + x[p.father!]) / 2 : NaN;
    };
    inRow.forEach((id, order) => {
      if (placed.has(id)) return;
      placed.add(id);
      const partner = (partners.get(id) || []).find((o) => gen[o] === g && !placed.has(o));
      let ids = [id];
      if (partner) {
        placed.add(partner);
        const pa = parentCentre(id);
        const pb = parentCentre(partner);
        if (Number.isNaN(pa) && !Number.isNaN(pb)) ids = [partner, id];
        else if (!Number.isNaN(pa) && Number.isNaN(pb)) ids = [id, partner];
        else ids = pa <= pb ? [id, partner] : [partner, id];
      }
      const centres = ids.map(parentCentre).filter((v) => !Number.isNaN(v));
      const key = centres.length ? centres.reduce((s, v) => s + v, 0) / centres.length : g === 0 ? order : Infinity;
      blocks.push({ ids, key, order });
    });
    blocks.sort((p, q) => (p.key === q.key ? p.order - q.order : p.key - q.key));
    let cursor = -Infinity;
    let prevKey: number | null = null;
    for (const b of blocks) {
      const ideal = Number.isFinite(b.key) ? b.key - (b.ids.length - 1) / 2 : cursor;
      const gap = prevKey !== null && prevKey !== b.key ? 1.25 : 1;
      const start = Math.max(Number.isFinite(ideal) ? ideal : 0, cursor === -Infinity ? -Infinity : cursor + gap);
      b.ids.forEach((id, i) => (x[id] = (Number.isFinite(start) ? start : 0) + i));
      cursor = x[b.ids[b.ids.length - 1]];
      prevKey = b.key;
    }
    rows.push(blocks.flatMap((b) => b.ids));
    blocksByRow.push(blocks.map((b) => b.ids));
  }

  // ---- centre parents above children (bottom-up), keeping order and spacing
  for (let sweep = 0; sweep < 2; sweep++) {
    for (let g = depth - 2; g >= 0; g--) {
      const blocks = blocksByRow[g];
      for (let i = 0; i < blocks.length; i++) {
        const ids = blocks[i];
        if (ids.length !== 2) continue;
        const c = coupleMap.get(pairKey(ids[0], ids[1]));
        if (!c || !c.children.length) continue;
        const want = c.children.reduce((s, k) => s + x[k], 0) / c.children.length;
        const cur = (x[ids[0]] + x[ids[1]]) / 2;
        let shift = want - cur;
        if (shift > 0 && i + 1 < blocks.length) shift = Math.min(shift, x[blocks[i + 1][0]] - 1 - x[ids[1]]);
        if (shift < 0 && i > 0) {
          const prev = blocks[i - 1];
          shift = Math.max(shift, x[prev[prev.length - 1]] + 1 - x[ids[0]]);
        }
        if (Math.abs(shift) > 1e-9) ids.forEach((id) => (x[id] += shift));
      }
    }
  }

  const xs = Object.values(x);
  const minX = xs.length ? Math.min(...xs) : 0;
  for (const id of Object.keys(x)) x[id] -= minX;
  const width = xs.length ? Math.max(...Object.values(x)) + 1 : 1;
  return { x, gen, rows, couples, width, depth };
}
