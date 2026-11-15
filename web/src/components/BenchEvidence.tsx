"use client";

// Silsila-Bench results: every model in the fixed pre-registered order (never ranked), headline metric per
// track with 95% intervals from a bootstrap over families, and the same-sample comparison (AMENDMENTS A10).

import { Card, Chip, H2, Num } from "./ui";
import { usePrefs } from "@/lib/prefs";

type CI = { value: number | null; lo: number; hi: number } | undefined;
type Track = { status: string; done?: number; expected?: number; metrics?: { overall: Record<string, CI | number> } };
type Model = { label: string; licence: string; status: string; reason?: string | null; tracks: Record<string, Track> };
export type Bench = {
  generated: string;
  preregistration_sha256: string;
  items: Record<string, number>;
  models: Record<string, Model>;
  same_sample?: { items: string; models: Record<string, Model> };
};

export const isBench = (d: unknown): d is Bench =>
  !!d && typeof d === "object" && "preregistration_sha256" in d && "models" in d;

const COLS: { track: string; metric: string; key: string; good: "high" | "low" }[] = [
  { track: "T1", metric: "exact", key: "bn.t1exact", good: "high" },
  { track: "T1", metric: "off_2x", key: "bn.t1off", good: "low" },
  { track: "T1", metric: "no_number", key: "bn.t1none", good: "low" },
  { track: "T2", metric: "tool_call_rate", key: "bn.t2called", good: "high" },
  { track: "T2", metric: "final_exact", key: "bn.t2exact", good: "high" },
  { track: "T3", metric: "edge_recall", key: "bn.t3recall", good: "high" },
  { track: "T3", metric: "engine_answer_correct", key: "bn.t3engine", good: "high" },
  { track: "T5", metric: "pmid_not_found", key: "bn.t5pmid", good: "low" },
];

function cell(m: Model, track: string, metric: string) {
  const t = m.tracks?.[track];
  const ci = t?.metrics?.overall?.[metric] as CI;
  if (!ci || ci.value === null || ci.value === undefined) return null;
  return ci;
}

function Table({ models, label }: { models: Record<string, Model>; label: string }) {
  const { t } = usePrefs();
  const rows = Object.entries(models).filter(([, m]) => Object.values(m.tracks || {}).some((x) => x.metrics));
  const notRun = Object.entries(models).filter(([, m]) => !Object.values(m.tracks || {}).some((x) => x.metrics));
  return (
    <>
      <div className="mt-3 overflow-x-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label={label}>
        <table className="w-full min-w-[880px] text-sm" dir="ltr">
          <thead className="bg-surface-2 text-xs text-muted">
            <tr>
              <th className="px-3 py-2 text-start font-semibold uppercase tracking-wide">{t("bn.model")}</th>
              {COLS.map((c) => (
                <th key={c.key} className="px-3 py-2 text-start font-semibold">
                  <span className="block uppercase tracking-wide">{c.track}</span>
                  {t(c.key as Parameters<typeof t>[0])}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([n, m]) => (
              <tr key={n} className="border-t border-line align-top">
                <td className="px-3 py-2">
                  <span className="font-medium">{m.label}</span>
                  {m.status.startsWith("reduced set") && <span className="mt-0.5 block text-xs text-muted">{t("bn.reduced")}</span>}
                </td>
                {COLS.map((c) => {
                  const ci = cell(m, c.track, c.metric);
                  return (
                    <td key={c.key} className="px-3 py-2 tabular-nums">
                      {ci ? (
                        <>
                          <Num>{(100 * (ci.value as number)).toFixed(1)}%</Num>
                          <span className="block text-[0.7rem] text-muted"><Num>{(100 * ci.lo).toFixed(0)}–{(100 * ci.hi).toFixed(0)}</Num></span>
                        </>
                      ) : (
                        <span className="text-muted">–</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {notRun.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          {t("bn.notRun")}: {notRun.map(([, m]) => `${m.label} (${m.reason || m.status})`).join("; ")}
        </p>
      )}
    </>
  );
}

export function BenchEvidence({ doc }: { doc: Bench }) {
  const { t } = usePrefs();
  return (
    <Card as="article" aria-labelledby="ev-bench">
      <p className="font-mono text-xs text-muted">docs/evidence/silsila_bench.json</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <h2 id="ev-bench" className="text-lg font-semibold sm:text-xl">{t("bn.title")}</h2>
        <Chip>{t("bn.prereg")}</Chip>
      </div>
      <p className="mt-2 max-w-3xl text-sm text-ink-2">{t("bn.lead")}</p>
      <div className="mt-4 grid gap-2 rounded-xl border border-accent bg-accent-soft p-4 text-sm">
        <p className="font-semibold">{t("bn.decides")}</p>
        <p>{t("bn.decidesText")}</p>
      </div>
      <Table models={doc.models} label={t("bn.title")} />
      {doc.same_sample && (
        <>
          <H2 className="mt-8">{t("bn.sameSample")}</H2>
          <p className="mt-1 max-w-3xl text-sm text-ink-2">{t("bn.sameSampleLead", { items: doc.same_sample.items })}</p>
          <Table models={doc.same_sample.models} label={t("bn.sameSample")} />
        </>
      )}
      <p className="mt-4 text-xs text-muted">
        {t("bn.foot", { date: doc.generated.slice(0, 10), sha: doc.preregistration_sha256.slice(0, 12) })}
      </p>
    </Card>
  );
}
