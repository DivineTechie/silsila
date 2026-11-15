"use client";

// Scenario calculator: what benchmark B4's yields would mean at programme scale. Every input is either a
// published figure (with its source) or a labelled, editable assumption. Nothing here is a forecast.

import { useMemo, useState } from "react";
import { Card, H2, Num, Prov, cx, inputCls } from "./ui";
import { usePrefs } from "@/lib/prefs";

interface Row {
  budget_tests_per_family: number | string;
  ranked_per_1000_tests: number;
  unranked_per_1000_tests: number;
  ranked_ci95: [number, number];
  unranked_ci95: [number, number];
}
type B4 = {
  results: { theta_calibrated: { loci: Record<string, { atrisk_couples: Row[] }> } };
  premarital_context?: { abu_dhabi_premarital?: { incompatible_couples: number; period: string; source: string } };
};

export function isB4(d: unknown): d is B4 {
  return !!d && typeof d === "object" && "results" in d && "premarital_context" in d;
}

/** Reported count used for the newborn preset (docs/evidence/uae_context.json). */
interface NewbornBasis { index_newborns_per_year: number; source: string }
type Preset = "premarital" | "newborn" | "custom";

export function ScenarioCalculator({ b4, newborn }: { b4: B4; newborn?: NewbornBasis }) {
  const { t } = usePrefs();
  const ad = b4.premarital_context?.abu_dhabi_premarital;
  const [locus, setLocus] = useState<"HBB" | "CYP21A2">("HBB");
  const [families, setFamilies] = useState(ad?.incompatible_couples ?? 500);
  const [preset, setPreset] = useState<Preset>(ad ? "premarital" : "custom");
  const choose = (p: Exclude<Preset, "custom">) => {
    setPreset(p);
    if (p === "premarital" && ad) setFamilies(ad.incompatible_couples);
    if (p === "newborn" && newborn) {
      setFamilies(newborn.index_newborns_per_year);
      setLocus("CYP21A2"); // the demonstration family's condition; any condition can be chosen
    }
  };
  const [budget, setBudget] = useState(5);
  const [hours, setHours] = useState(1.5);
  const rows = b4.results.theta_calibrated.loci[locus]?.atrisk_couples ?? [];
  const budgets = rows.map((r) => r.budget_tests_per_family).filter((b): b is number => typeof b === "number" && b > 1);
  const row = rows.find((r) => r.budget_tests_per_family === budget) ?? rows[0];

  const out = useMemo(() => {
    if (!row) return null;
    const tests = families * budget;
    const k = tests / 1000;
    return {
      tests,
      ranked: row.ranked_per_1000_tests * k,
      rankedLo: row.ranked_ci95[0] * k,
      rankedHi: row.ranked_ci95[1] * k,
      unranked: row.unranked_per_1000_tests * k,
      hours: tests * hours,
    };
  }, [row, families, budget, hours]);

  return (
    <Card>
      <H2>{t("sc.title")}</H2>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{t("sc.lead")}</p>
      {ad && newborn && (
        <div className="mt-4 flex flex-wrap items-center gap-2" role="group" aria-label={t("sc.start")}>
          <span className="text-sm text-ink-2">{t("sc.start")}:</span>
          {(["premarital", "newborn"] as const).map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={preset === p}
              onClick={() => choose(p)}
              className={cx("min-h-9 rounded-lg border px-3 text-sm font-medium",
                preset === p ? "border-accent bg-accent-soft text-ink" : "border-line-strong bg-surface text-ink hover:bg-surface-2")}
            >
              {p === "premarital" ? t("sc.preset.premarital", { n: ad.incompatible_couples }) : t("sc.preset.newborn", { n: newborn.index_newborns_per_year })}
            </button>
          ))}
        </div>
      )}
      {preset === "newborn" && newborn && (
        <p className="mt-3 rounded-xl border border-notice-line bg-notice px-4 py-3 text-sm">
          <strong className="font-semibold">{t("sc.projection")}</strong> {t("sc.newbornSrc", { n: newborn.index_newborns_per_year })}{" "}
          <a className="text-accent underline" href={newborn.source} target="_blank" rel="noreferrer" dir="ltr" lang="en">Khaleej Times</a>
        </p>
      )}
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="grid gap-1 text-sm" htmlFor="sc-locus">
          {t("sc.condition")}
          <select id="sc-locus" className={inputCls} value={locus} onChange={(e) => setLocus(e.target.value as "HBB" | "CYP21A2")}>
            <option value="HBB">Beta-thalassaemia / sickle cell (HBB)</option>
            <option value="CYP21A2">Congenital adrenal hyperplasia (CYP21A2)</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="sc-fam">
          {t("sc.families")}
          <input id="sc-fam" type="number" min={1} max={100000} className={inputCls} value={families}
            onChange={(e) => { setPreset("custom"); setFamilies(Math.max(1, Math.min(100000, Number(e.target.value) || 1))); }} />
          {ad && preset !== "newborn" && (
            <span className="text-xs text-muted">
              <Prov kind="recorded" /> {t("sc.familiesSrc", { n: ad.incompatible_couples, period: ad.period })}{" "}
              <a className="text-accent underline" href={ad.source} target="_blank" rel="noreferrer">Gulf News</a>
            </span>
          )}
        </label>
        <label className="grid gap-1 text-sm" htmlFor="sc-budget">
          {t("sc.budget")}
          <select id="sc-budget" className={inputCls} value={budget} onChange={(e) => setBudget(Number(e.target.value))}>
            {budgets.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <span className="text-xs text-muted">{t("sc.budgetSrc")}</span>
        </label>
        <label className="grid gap-1 text-sm" htmlFor="sc-hours">
          {t("sc.hours")}
          <input id="sc-hours" type="number" min={0.25} max={8} step={0.25} className={inputCls} value={hours}
            onChange={(e) => setHours(Math.max(0.25, Math.min(8, Number(e.target.value) || 1)))} />
          <span className="text-xs text-muted">{t("sc.hoursSrc")}</span>
        </label>
      </div>
      {out && (
        <div className="mt-5 grid gap-3 sm:grid-cols-3" aria-live="polite">
          <div className="rounded-xl border border-accent bg-accent-soft p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{t("sc.ranked")}{preset === "newborn" ? ` · ${t("sc.projectionTag")}` : ""}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums"><Num>{Math.round(out.ranked)}</Num></p>
            <p className="text-xs text-ink-2"><Prov kind="calculated" /> {t("sc.couples")} · 95% <Num>{Math.round(out.rankedLo)}–{Math.round(out.rankedHi)}</Num></p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{t("sc.unranked")}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums"><Num>{Math.round(out.unranked)}</Num></p>
            <p className="text-xs text-ink-2"><Prov kind="calculated" /> {t("sc.couples")}</p>
          </div>
          <div className="rounded-xl border border-line bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{t("sc.workload")}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums"><Num>{Math.round(out.hours).toLocaleString("en-US")}</Num></p>
            <p className="text-xs text-ink-2">{t("sc.workloadD", { tests: out.tests.toLocaleString("en-US") })}</p>
          </div>
        </div>
      )}
      <p className="mt-4 text-xs text-muted">{t("sc.caveat")}</p>
    </Card>
  );
}
