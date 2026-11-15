"use client";

// Renderers for the benchmark files whose shape is known (triage, privacy,
// cascade-yield chart). Anything else falls back to the generic EvidenceFile.

import { useState } from "react";
import { fmtPct, usePrefs } from "@/lib/prefs";
import { ReasonChip } from "./counsellor";
import { BarChart, SimpleTable } from "./evidence";
import { H3, cx } from "./ui";

type Obj = Record<string, unknown>;
interface Prop {
  k: number;
  n: number;
  value: number;
  ci95: [number, number];
}
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isProp = (v: unknown): v is Prop => isObj(v) && typeof v.value === "number" && Array.isArray(v.ci95);

// ------------------------------------------------------------- detection --
export const isTriage = (d: unknown) => isObj(d) && isObj(d.overall) && isObj(d.by_variety);
export const isPrivacy = (d: unknown) => isObj(d) && typeof d.attempts === "number" && "unauthorised_disclosures" in d;
export const isCascadeChart = (d: unknown) =>
  isObj(d) && Array.isArray(d.series) && d.series.every((s) => isObj(s) && Array.isArray(s.points));

function Shell({ file, title, children, note }: { file: string; title: string; children: React.ReactNode; note?: unknown }) {
  return (
    <article className="min-w-0 [overflow-wrap:anywhere] rounded-2xl border border-line bg-surface-2/40 p-4 sm:p-6" aria-label={title}>
      <p className="font-mono text-xs text-muted" dir="ltr">docs/evidence/{file}.json</p>
      <h2 className="mt-1 text-lg font-semibold sm:text-xl">{title}</h2>
      {typeof note === "string" && (
        <p lang="en" dir="ltr" className="mt-2 max-w-3xl text-start text-sm text-ink-2">
          {note}
        </p>
      )}
      <div className="mt-4">{children}</div>
    </article>
  );
}

/** Proportion with its 95% CI as a dot-and-whisker on a 0–100% track. */
function PropCell({ p, bar = true }: { p?: unknown; bar?: boolean }) {
  if (!isProp(p)) return <span className="text-muted">—</span>;
  const [lo, hi] = p.ci95;
  return (
    <div className="min-w-32" title={`${p.k}/${p.n}, 95% CI ${fmtPct(lo)}–${fmtPct(hi)}`}>
      <div className="flex items-baseline gap-2">
        <span className="font-semibold tabular-nums">{fmtPct(p.value)}</span>
        <span className="text-xs tabular-nums text-muted">
          {p.k}/{p.n}
        </span>
      </div>
      {bar && (
        <svg viewBox="0 0 100 10" className="mt-1 h-2.5 w-full max-w-40" aria-hidden="true" preserveAspectRatio="none">
          <rect x="0" y="4" width="100" height="2" rx="1" fill="var(--line)" />
          <rect x={lo * 100} y="2.5" width={Math.max(0.8, (hi - lo) * 100)} height="5" rx="1.5" fill="var(--accent)" opacity="0.35" />
          <rect x={Math.min(99, p.value * 100) - 0.8} y="0.5" width="1.6" height="9" rx="0.8" fill="var(--accent)" />
        </svg>
      )}
      <span className="block text-[0.7rem] tabular-nums text-muted">
        {fmtPct(lo)} – {fmtPct(hi)}
      </span>
    </div>
  );
}

const SPECIAL: Record<string, string> = {
  _escalation: "any escalation label",
  _crisis_reply_first: "crisis reply shown first",
  _crisis_reply_has_emergency_numbers: "crisis replies include 998 / 999",
  _human_review_reach: "messages that reach a person",
};

// ---------------------------------------------------------------- triage --
export function TriageEvidence({ file, doc }: { file: string; doc: Obj }) {
  const { t } = usePrefs();
  const overall = doc.overall as Obj;
  const varieties = Object.keys(doc.by_variety as Obj);
  const labels = Object.keys(overall).filter((k) => isObj(overall[k]) && "sensitivity" in (overall[k] as Obj));
  const extras = Object.keys(overall).filter((k) => !labels.includes(k));
  const pp = isObj(doc.privacy_prompts) ? doc.privacy_prompts : null;
  const th = "px-3 py-2 text-start text-xs font-semibold uppercase tracking-wide text-muted";
  const title = `${t("ev.triage")}: ${/ngram/.test(file) ? t("ev.triageNgram") : t("ev.triageRules")}`;
  const labelCell = (k: string) =>
    k.startsWith("_") ? <span className="font-semibold">{SPECIAL[k] || k}</span> : <ReasonChip code={k} />;
  return (
    <Shell file={file} title={title} note={doc.note}>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm" dir="ltr">
        <div><dt className="inline text-muted">{t("ev.messages")}: </dt><dd className="inline font-semibold tabular-nums">{String(doc.n_messages ?? "—")}</dd></div>
        <div><dt className="inline text-muted">{t("ev.gateFailures")}: </dt><dd className="inline font-semibold tabular-nums">{String(doc.gate_failures ?? "—")}</dd></div>
        <div><dt className="inline text-muted">{t("ev.llm")}: </dt><dd className="inline font-semibold">{doc.use_model ? "yes" : "no"}</dd></div>
      </dl>
      {typeof doc.testset === "string" && <p className="mt-1 font-mono text-xs text-muted" dir="ltr">{doc.testset}</p>}

      <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-surface" dir="ltr" tabIndex={0} role="region" aria-label={`${title}: results by label`}>
        <table className="w-full min-w-[620px] text-sm">
          <caption className="sr-only">{title}</caption>
          <thead className="border-b border-line">
            <tr>
              <th scope="col" className={th}>{t("ev.label")}</th>
              <th scope="col" className={th}>{t("ev.sens")}</th>
              <th scope="col" className={th}>{t("ev.spec")}</th>
              <th scope="col" className={th}>{t("ev.ppv")}</th>
            </tr>
          </thead>
          <tbody>
            {labels.map((k) => {
              const r = overall[k] as Obj;
              return (
                <tr key={k} className={cx("border-b border-line align-top last:border-0", k.startsWith("_") && "bg-surface-2/60")}>
                  <th scope="row" className="px-3 py-2 text-start font-normal">{labelCell(k)}</th>
                  <td className="px-3 py-2"><PropCell p={r.sensitivity} /></td>
                  <td className="px-3 py-2"><PropCell p={r.specificity} /></td>
                  <td className="px-3 py-2"><PropCell p={r.ppv} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {extras.length > 0 && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" dir="ltr">
          {extras.map((k) => {
            const v = overall[k] as Obj;
            return (
              <div key={k} className="rounded-xl border border-line bg-surface p-4">
                <p className="text-sm text-ink-2">{SPECIAL[k] || k}</p>
                {isProp(v) ? (
                  <div className="mt-1"><PropCell p={v} /></div>
                ) : (
                  <p className="mt-1 text-2xl font-semibold tabular-nums">{typeof v?.value === "number" ? fmtPct(v.value) : "—"}</p>
                )}
                {typeof v?.basis === "string" && <p className="mt-1 text-xs text-muted">{v.basis}</p>}
              </div>
            );
          })}
          {pp && (
            <div className="rounded-xl border border-line bg-surface p-4">
              <p className="text-sm text-ink-2">{t("ev.privacyPrompts")} (n = {String(pp.n)})</p>
              <p className="mt-2 text-xs text-muted">{t("ev.refusal")}</p>
              <PropCell p={pp.refusal_template} />
              <p className="mt-2 text-xs text-muted">{t("ev.caseData")}</p>
              <p className="text-xl font-semibold tabular-nums">{String(pp.replies_containing_case_data ?? "—")}</p>
            </div>
          )}
        </div>
      )}

      <H3 className="mt-6">{t("ev.byVariety")}</H3>
      <div className="mt-2 overflow-x-auto rounded-xl border border-line bg-surface" dir="ltr" tabIndex={0} role="region" aria-label={`${title}: ${t("ev.byVariety")}`}>
        <table className="w-full min-w-[720px] text-sm">
          <thead className="border-b border-line">
            <tr>
              <th scope="col" className={th}>{t("ev.label")}</th>
              {varieties.map((v) => (
                <th key={v} scope="col" className={th}>{v}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {labels.map((k) => (
              <tr key={k} className="border-b border-line align-top last:border-0">
                <th scope="row" className="px-3 py-2 text-start font-normal">{labelCell(k)}</th>
                {varieties.map((v) => {
                  const r = ((doc.by_variety as Obj)[v] as Obj)?.[k] as Obj | undefined;
                  return (
                    <td key={v} className="px-3 py-2"><PropCell p={r?.sensitivity} bar={false} /></td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 font-mono text-xs text-muted" dir="ltr">
        {t("ev.cases")}: docs/evidence/{file.replace(/\.json$/, "")}_cases.csv
      </p>
    </Shell>
  );
}

// --------------------------------------------------------------- privacy --
export function PrivacyEvidence({ file, doc }: { file: string; doc: Obj }) {
  const { t } = usePrefs();
  const chain = isObj(doc.audit_chain_after_run) ? doc.audit_chain_after_run : null;
  const cards: [string, unknown][] = [
    [t("ev.attempts"), doc.attempts],
    [t("ev.disclosures"), doc.unauthorised_disclosures],
    [t("ev.violations"), doc.disclosure_violations],
    [t("ev.denied"), doc.denied_attempts_in_audit],
  ];
  const byAttack = isObj(doc.by_attack)
    ? Object.entries(doc.by_attack)
        .filter(([, v]) => typeof v === "number")
        .map(([k, v]) => ({ label: k.replace(/_/g, " "), value: v as number, ci: null }))
    : [];
  return (
    <Shell file={file} title={t("ev.privacy")}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" dir="ltr">
        {cards.map(([label, v]) => (
          <div key={label} className="rounded-xl border border-line bg-surface p-4">
            <p className="text-sm text-ink-2">{label}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{typeof v === "number" ? v.toLocaleString("en-US") : "—"}</p>
          </div>
        ))}
        {chain && (
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-sm text-ink-2">{t("ev.chainAfter")}</p>
            <p className="mt-1 text-xl font-semibold">
              {chain.intact ? t("c.chainIntact") : t("c.chainBroken", { n: String(chain.first_broken_seq) })}
            </p>
            <p className="text-xs text-muted tabular-nums">{t("c.events", { n: Number(chain.events).toLocaleString("en-US") })}</p>
          </div>
        )}
      </div>
      {byAttack.length > 0 && (
        <div className="mt-4">
          <BarChart title={t("ev.byAttack")} data={byAttack} />
        </div>
      )}
      {Array.isArray(doc.disclosure_checks) && doc.disclosure_checks.length > 0 && (
        <div className="mt-4">
          <H3>{t("ev.disclosureChecks")}</H3>
          <SimpleTable label={t("ev.disclosureChecks")} rows={doc.disclosure_checks as Obj[]} />
        </div>
      )}
      {Array.isArray(doc.failures) && doc.failures.length > 0 && <SimpleTable label={`${file}: failures`} rows={doc.failures as Obj[]} />}
    </Shell>
  );
}

// --------------------------------------------------------- cascade chart --
interface Point {
  x: number | string;
  y: number;
  lo?: number;
  hi?: number;
  mean_tests?: number;
}

export function CascadeChart({ file, doc }: { file: string; doc: Obj }) {
  const { t } = usePrefs();
  const series = doc.series as { locus?: string; strategy?: string; name?: string; points: Point[] }[];
  const xs = Array.from(new Set(series.flatMap((s) => s.points.map((p) => String(p.x)))));
  const [x, setX] = useState(xs.includes("5") ? "5" : xs[Math.min(2, xs.length - 1)]);
  const loci = Array.from(new Set(series.map((s) => s.locus || "")));
  const yLabel = typeof doc.y_label === "string" ? doc.y_label : t("ev.chart");
  return (
    <Shell file={file} title={t("ev.chart")} note={doc.note}>
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("ev.budget")}>
        <span className="text-sm text-ink-2">{t("ev.budget")}:</span>
        {xs.map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={x === v}
            onClick={() => setX(v)}
            className={cx(
              "min-h-9 min-w-9 rounded-md border px-2 text-sm tabular-nums",
              x === v ? "border-accent bg-accent-soft font-semibold" : "border-line-strong",
            )}
          >
            {v}
          </button>
        ))}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {loci.map((l) => {
          const data = series
            .filter((s) => (s.locus || "") === l)
            .map((s) => {
              const p = s.points.find((q) => String(q.x) === x);
              return p
                ? {
                    label: s.strategy || s.name || "series",
                    value: p.y,
                    ci: typeof p.lo === "number" && typeof p.hi === "number" ? ([p.lo, p.hi] as [number, number]) : null,
                  }
                : null;
            })
            .filter((d): d is { label: string; value: number; ci: [number, number] | null } => d !== null);
          return data.length ? <BarChart key={l} title={`${l} · ${yLabel} · ${t("ev.budget")} = ${x}`} data={data} /> : null;
        })}
      </div>
    </Shell>
  );
}
