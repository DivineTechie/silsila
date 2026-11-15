"use client";

// Generic renderer for benchmark JSON files in docs/evidence. The files are
// produced by another part of the project and may change shape, so this
// recognises a few common patterns and falls back to tables and raw JSON.

import { fmtNum, usePrefs } from "@/lib/prefs";
import { H3, cx } from "./ui";

type J = unknown;
type Obj = Record<string, J>;

const isObj = (v: J): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isNum = (v: J): v is number => typeof v === "number" && Number.isFinite(v);
const human = (k: string) => k.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim().replace(/^./, (c) => c.toUpperCase());

const VALUE_KEYS = ["value", "estimate", "point", "mean", "median", "rate", "proportion", "per_1000"];
const LABEL_KEYS = ["strategy", "label", "name", "arm", "method", "group", "id", "scenario", "key"];

export function ciOf(o: Obj): [number, number] | null {
  for (const k of ["ci95", "exact_ci95", "ci_95", "ci", "interval", "wilson_ci", "ci95_wilson"]) {
    const v = o[k];
    if (Array.isArray(v) && v.length === 2 && isNum(v[0]) && isNum(v[1])) return [v[0], v[1]];
    if (isObj(v)) {
      const lo = v.lo ?? v.low ?? v.lower;
      const hi = v.hi ?? v.high ?? v.upper;
      if (isNum(lo) && isNum(hi)) return [lo, hi];
    }
  }
  for (const [lk, hk] of [["ci_low", "ci_high"], ["ci_lo", "ci_hi"], ["lower", "upper"], ["lo", "hi"], ["ci95_low", "ci95_high"]]) {
    if (isNum(o[lk]) && isNum(o[hk])) return [o[lk] as number, o[hk] as number];
  }
  return null;
}

function valueOf(o: Obj): [string, number] | null {
  for (const k of VALUE_KEYS) if (isNum(o[k])) return [k, o[k] as number];
  for (const [k, v] of Object.entries(o)) if (k.includes("per_1000") && isNum(v)) return [k, v];
  return null;
}

function passFail(o: Obj): { pass: number; fail: number; total?: number } | null {
  const pass = o.passed ?? o.pass ?? o.n_passed ?? o.passes;
  const fail = o.failed ?? o.fail ?? o.n_failed ?? o.failures;
  if (isNum(pass) && isNum(fail)) return { pass, fail, total: isNum(o.total) ? o.total : undefined };
  return null;
}

function labelOf(o: Obj): string | null {
  for (const k of LABEL_KEYS) if (typeof o[k] === "string") return o[k] as string;
  return null;
}

/** Array of objects each with a label and a numeric value: a chart series. */
function asSeries(arr: J[]): { label: string; value: number; ci: [number, number] | null; key: string }[] | null {
  if (arr.length < 2 || !arr.every(isObj)) return null;
  const out = [];
  for (const o of arr as Obj[]) {
    const l = labelOf(o);
    const v = valueOf(o) || Object.entries(o).find(([, x]) => isNum(x)) || null;
    if (!l || !v) return null;
    out.push({ label: l, value: v[1] as number, ci: ciOf(o), key: v[0] as string });
  }
  return out;
}

function fmt(v: J): string {
  if (isNum(v)) return fmtNum(v, 5);
  if (typeof v === "boolean") return v ? "true" : "false";
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

// ------------------------------------------------------------------ pieces --
function Metric({ name, o }: { name: string; o: Obj }) {
  const { t } = usePrefs();
  const v = valueOf(o)!;
  const ci = ciOf(o);
  const n = o.n ?? o.N ?? o.denominator ?? o.trials;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-sm text-ink-2">{typeof o.label === "string" ? o.label : human(name)}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums tracking-tight">{fmtNum(v[1], 4)}</p>
      {ci && (
        <p className="mt-1 text-sm tabular-nums text-ink-2">
          {t("ev.ci")} {fmtNum(ci[0], 4)} – {fmtNum(ci[1], 4)}
        </p>
      )}
      {isNum(n) && <p className="mt-1 text-xs text-muted">n = {n.toLocaleString("en-US")}</p>}
      {typeof o.unit === "string" && <p className="mt-1 text-xs text-muted">{o.unit}</p>}
    </div>
  );
}

function PassFail({ name, pf }: { name: string; pf: { pass: number; fail: number; total?: number } }) {
  const { t } = usePrefs();
  const total = pf.total ?? pf.pass + pf.fail;
  const pct = total ? (pf.pass / total) * 100 : 0;
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-sm text-ink-2">{human(name)}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">
        {pf.pass.toLocaleString("en-US")} / {total.toLocaleString("en-US")}
      </p>
      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-ink-2 tabular-nums">
        {t("ev.pass")} {pf.pass} · {t("ev.fail")} {pf.fail}
      </p>
    </div>
  );
}

/** Horizontal bar chart: one series, one hue, value labels, CI whiskers,
 *  native tooltip per bar, and a table view for screen readers. */
export function BarChart({ title, data, unit }: { title: string; data: { label: string; value: number; ci: [number, number] | null }[]; unit?: string }) {
  const max = Math.max(...data.map((d) => Math.max(d.value, d.ci?.[1] ?? 0)), 0) || 1;
  const rowH = 34;
  const labelW = 170;
  const W = 560;
  const plotW = W - labelW - 70;
  const H = data.length * rowH + 28;
  const sx = (v: number) => labelW + (Math.max(0, v) / max) * plotW;
  return (
    <figure className="min-w-0 rounded-xl border border-line bg-surface p-4">
      <figcaption className="text-sm font-semibold">{title}</figcaption>
      <div className="mt-3 overflow-x-auto" dir="ltr" tabIndex={0} role="region" aria-label={title}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ minWidth: 340, maxWidth: W }} role="img" aria-label={title}>
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={sx(max * f)} x2={sx(max * f)} y1={4} y2={H - 22} stroke="var(--line)" strokeWidth={1} />
              <text x={sx(max * f)} y={H - 6} textAnchor="middle" fontSize="11" fill="var(--muted)">
                {fmtNum(max * f, 3)}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const y = 6 + i * rowH;
            const w = Math.max(2, sx(d.value) - labelW);
            return (
              <g key={d.label}>
                <title>{`${d.label}: ${fmtNum(d.value, 4)}${d.ci ? ` (95% CI ${fmtNum(d.ci[0], 4)}–${fmtNum(d.ci[1], 4)})` : ""}${unit ? ` ${unit}` : ""}`}</title>
                <text x={labelW - 10} y={y + rowH / 2 + 1} textAnchor="end" dominantBaseline="middle" fontSize="12" fill="var(--ink)">
                  {d.label.length > 24 ? d.label.slice(0, 23) + "…" : d.label}
                </text>
                <rect x={labelW} y={y + 7} width={w} height={rowH - 16} rx={4} fill="var(--accent)" />
                {d.ci && (
                  <g stroke="var(--ink)" strokeWidth={1.5}>
                    <line x1={sx(d.ci[0])} x2={sx(d.ci[1])} y1={y + rowH / 2 - 1} y2={y + rowH / 2 - 1} />
                    <line x1={sx(d.ci[0])} x2={sx(d.ci[0])} y1={y + rowH / 2 - 6} y2={y + rowH / 2 + 4} />
                    <line x1={sx(d.ci[1])} x2={sx(d.ci[1])} y1={y + rowH / 2 - 6} y2={y + rowH / 2 + 4} />
                  </g>
                )}
                <text x={sx(Math.max(d.value, d.ci?.[1] ?? 0)) + 8} y={y + rowH / 2 + 1} dominantBaseline="middle" fontSize="12" fontWeight={600} fill="var(--ink)">
                  {fmtNum(d.value, 3)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-ink-2">Table</summary>
        <SimpleTable label={`${title}: table`} rows={data.map((d) => ({ label: d.label, value: d.value, ci95: d.ci ? `${fmtNum(d.ci[0], 4)} – ${fmtNum(d.ci[1], 4)}` : "—" }))} />
      </details>
    </figure>
  );
}

export function SimpleTable({ rows, label }: { rows: Obj[]; label: string }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 12);
  return (
    <div className="mt-2 overflow-x-auto rounded-lg border border-line" dir="ltr" tabIndex={0} role="region" aria-label={label}>
      <table className="w-full text-sm">
        <thead className="border-b border-line bg-surface-2/60">
          <tr>{cols.map((c) => <th key={c} scope="col" className="px-3 py-2 text-start text-xs font-semibold text-muted">{human(c)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 200).map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {cols.map((c) => <td key={c} className={cx("px-3 py-1.5 align-top", isNum(r[c]) && "tabular-nums")}>{fmt(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ----------------------------------------------------------------- walker --
interface Found {
  metrics: { name: string; o: Obj }[];
  passfail: { name: string; pf: { pass: number; fail: number; total?: number } }[];
  series: { name: string; data: ReturnType<typeof asSeries> & object }[];
  tables: { name: string; rows: Obj[] }[];
  scalars: { name: string; v: J }[];
  texts: { name: string; v: string }[];
}

function walk(v: J, name: string, f: Found, depth: number) {
  if (depth > 5) return;
  if (isObj(v)) {
    const pf = passFail(v);
    if (pf) f.passfail.push({ name, pf });
    if (valueOf(v) && (ciOf(v) || depth > 0)) {
      f.metrics.push({ name, o: v });
      return;
    }
    const entries = Object.entries(v);
    // a dict of flat records keyed by name (e.g. results by category) becomes one table
    const flatRec = (x: J) => isObj(x) && Object.values(x).every((y) => !isObj(y) && !Array.isArray(y));
    if (depth > 0 && entries.length >= 3 && entries.every(([, x]) => flatRec(x))) {
      f.tables.push({ name, rows: entries.map(([k, x]) => ({ key: k, ...(x as Obj) })) });
      return;
    }
    // a dict of {label: number} becomes a series when there are several numbers
    const numeric = entries.filter(([, x]) => isNum(x));
    if (numeric.length >= 3 && numeric.length === entries.length && depth > 0) {
      f.series.push({ name, data: numeric.map(([k, x]) => ({ label: human(k), value: x as number, ci: null, key: k })) });
      return;
    }
    for (const [k, x] of entries) {
      if (pf && ["passed", "pass", "failed", "fail", "total", "n_passed", "n_failed"].includes(k)) continue;
      const path = name ? `${name} · ${k}` : k;
      if (isObj(x) || Array.isArray(x)) walk(x, k === "headline" || k === "metrics" ? name || k : path, f, depth + 1);
      else if (typeof x === "string" && x.length > 60) f.texts.push({ name: k, v: x });
      else f.scalars.push({ name: path, v: x });
    }
    return;
  }
  if (Array.isArray(v)) {
    const s = asSeries(v);
    if (s) {
      f.series.push({ name, data: s });
      return;
    }
    if (v.length && v.every(isObj)) {
      const flat = (v as Obj[]).map((o) =>
        Object.fromEntries(Object.entries(o).map(([k, x]) => [k, isObj(x) || Array.isArray(x) ? JSON.stringify(x) : x])),
      );
      // arrays of check results with boolean outcomes count as pass/fail
      const okKey = ["passed", "pass", "ok", "success"].find((k) => (v as Obj[]).every((o) => typeof o[k] === "boolean"));
      if (okKey) {
        const pass = (v as Obj[]).filter((o) => o[okKey]).length;
        f.passfail.push({ name, pf: { pass, fail: v.length - pass } });
      }
      f.tables.push({ name, rows: flat });
      return;
    }
    if (v.length) f.scalars.push({ name, v: v.map(fmt).join(", ") });
  }
}

export function EvidenceFile({ name, doc }: { name: string; doc: J }) {
  const { t } = usePrefs();
  const f: Found = { metrics: [], passfail: [], series: [], tables: [], scalars: [], texts: [] };
  const title = isObj(doc) && typeof doc.title === "string" ? doc.title : human(name);
  const body = isObj(doc) ? Object.fromEntries(Object.entries(doc).filter(([k]) => k !== "title")) : doc;
  walk(body, "", f, 0);
  return (
    <article className="min-w-0 [overflow-wrap:anywhere] rounded-2xl border border-line bg-surface-2/40 p-4 sm:p-6" aria-labelledby={`ev-${name}`}>
      <p className="font-mono text-xs text-muted">docs/evidence/{name}.json</p>
      <h2 id={`ev-${name}`} className="mt-1 text-lg font-semibold sm:text-xl">{title}</h2>
      {f.texts.map((x) => (
        <p key={x.name} className="mt-2 max-w-3xl text-sm text-ink-2" dir="ltr">
          <span className="font-semibold">{human(x.name)}:</span> {x.v}
        </p>
      ))}
      {(f.metrics.length > 0 || f.passfail.length > 0) && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" dir="ltr">
          {f.metrics.map((m, i) => <Metric key={`m${i}`} name={m.name} o={m.o} />)}
          {f.passfail.map((p, i) => <PassFail key={`p${i}`} name={p.name || title} pf={p.pf} />)}
        </div>
      )}
      {f.series.map((s, i) => {
        const per1000 = /1000|per_1k/i.test(s.name + s.data.map((d) => d.key).join(" "));
        return (
          <div key={`s${i}`} className="mt-4">
            <BarChart title={per1000 ? `${t("ev.chart")}${s.name ? ` · ${human(s.name)}` : ""}` : human(s.name || title)} data={s.data} />
          </div>
        );
      })}
      {(f.tables.length > 0 || f.scalars.length > 0) && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-ink-2">
            {f.tables.length} × table · {f.scalars.length} × value
          </summary>
      {f.tables.map((tb, i) => (
        <div key={`t${i}`} className="mt-4">
          <H3>{human(tb.name || title)}</H3>
          <SimpleTable label={`${title}: ${human(tb.name || title)} (${i + 1})`} rows={tb.rows} />
        </div>
      ))}
      {f.scalars.length > 0 && (
        <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2" dir="ltr">
          {f.scalars.slice(0, 60).map((s, i) => (
            <div key={i} className="flex justify-between gap-3 border-b border-line py-1">
              <dt className="text-muted">{human(s.name)}</dt>
              <dd className="text-end tabular-nums">{fmt(s.v)}</dd>
            </div>
          ))}
        </dl>
      )}
        </details>
      )}
      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-ink-2">{t("ev.raw")}</summary>
        <pre dir="ltr" className="mt-2 max-h-96 overflow-auto rounded-lg bg-surface p-3 font-mono text-xs" tabIndex={0} role="region" aria-label={`${title}: raw data`}>{JSON.stringify(doc, null, 2)}</pre>
      </details>
    </article>
  );
}
