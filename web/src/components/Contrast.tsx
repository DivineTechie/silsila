"use client";

// "Why not just ask a chatbot?" RECORDED answers from the benchmark models to the demo family's question, in
// English and Gulf Arabic, in free text and with the Silsila engine offered as a tool, beside the exact answer.
// Models are listed in a fixed order (not ranked). The message is about architecture, not vendors.

import { useEffect, useState } from "react";
import { Card, Chip, H2, Num, Prov, cx } from "./ui";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";

interface Row {
  register: "en" | "gulf";
  mode: string;
  value: number | null;
  tool_calls: number;
  tool_values: number[];
  error: string | null;
  answer_tail?: string;
  latency_s: number;
}
interface Data {
  created_at: string;
  settings: string;
  question: Record<string, string>;
  gold: { probability: number; one_in: string };
  models: Record<string, { label: string; model?: string; rows?: Row[]; error?: string }>;
}

const ORDER = ["jais-3-7b", "jais-3-32b", "bimedix2-8b", "llama3-med42-8b", "gpt-oss-120b"];

function fmt(p: number | null | undefined): string {
  if (p === null || p === undefined) return "no number";
  const v = p * 100;
  return v >= 10 ? `${v.toFixed(0)}%` : v >= 1 ? `${v.toFixed(1)}%` : `${v.toFixed(2)}%`;
}

function verdict(p: number | null | undefined, gold: number): "exact" | "close" | "off" | "none" {
  if (p === null || p === undefined) return "none";
  const r = Math.abs(p - gold) / gold;
  return r <= 0.05 ? "exact" : r <= 0.25 ? "close" : "off";
}

function Cell({ row, gold }: { row?: Row; gold: number }) {
  const { t } = usePrefs();
  if (!row) return <td className="px-3 py-2 text-muted">–</td>;
  const v = verdict(row.value, gold);
  return (
    <td className="px-3 py-2 align-top">
      <span
        className={cx(
          "inline-flex min-w-16 justify-center rounded-md px-2 py-0.5 text-sm font-semibold tabular-nums",
          v === "exact" && "bg-accent-soft text-accent",
          v === "close" && "bg-surface-2 text-ink",
          v === "off" && "bg-[#ffe3d6] text-[#9a3412] dark:bg-[#4a2416] dark:text-[#ffc9a8]",
          v === "none" && "bg-surface-2 text-muted",
        )}
        title={row.answer_tail || row.error || ""}
      >
        <Num>{row.error ? "error" : fmt(row.value)}</Num>
      </span>
      {row.mode !== "free text" && (
        <span className="mt-1 block text-[0.7rem] text-muted">
          {row.tool_calls > 0 ? t("ct.toolUsed", { n: row.tool_calls }) : t("ct.toolNotUsed")}
        </span>
      )}
    </td>
  );
}

export function Contrast() {
  const { t } = usePrefs();
  const [data, setData] = useState<Data | null>(null);
  useEffect(() => {
    api<Data>("/api/contrast", { auth: false }).then(setData).catch(() => setData(null));
  }, []);
  if (!data) return null;
  const gold = data.gold.probability;
  const names = ORDER.filter((n) => data.models[n]);
  const get = (n: string, reg: string, mode: string) => data.models[n].rows?.find((r) => r.register === reg && r.mode === mode);
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <H2>{t("ct.title")}</H2>
        <Chip>{t("ct.recorded", { date: data.created_at.slice(0, 10) })}</Chip>
      </div>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{t("ct.lead")}</p>
      <p className="mt-3 text-sm"><span className="text-muted">{t("ct.question")}:</span> {data.question.en.replace(/^Question:\s*/, "")}</p>
      <p className="mt-1 text-sm" dir="rtl" lang="ar">{data.question.gulf}</p>
      <div className="mt-4 flex items-center gap-3 rounded-xl border border-accent bg-accent-soft p-3">
        <Prov kind="calculated" />
        <span className="text-sm text-ink-2">{t("ct.exact")}:</span>
        <span className="text-2xl font-semibold tabular-nums"><Num>{fmt(gold)}</Num></span>
        <span className="text-sm text-ink-2">({data.gold.one_in})</span>
      </div>
      <div className="mt-4 overflow-x-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label={t("ct.title")}>
        <table className="w-full min-w-[640px] text-sm" dir="ltr">
          <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2 text-start" rowSpan={2}>{t("ct.model")}</th>
              <th className="px-3 py-1 text-start" colSpan={2}>{t("ct.free")}</th>
              <th className="px-3 py-1 text-start" colSpan={2}>{t("ct.tool")}</th>
            </tr>
            <tr>
              <th className="px-3 py-1 text-start">English</th><th className="px-3 py-1 text-start">Gulf Arabic</th>
              <th className="px-3 py-1 text-start">English</th><th className="px-3 py-1 text-start">Gulf Arabic</th>
            </tr>
          </thead>
          <tbody>
            {names.map((n) => (
              <tr key={n} className="border-t border-line">
                <td className="px-3 py-2 font-medium">{data.models[n].label}</td>
                <Cell row={get(n, "en", "free text")} gold={gold} />
                <Cell row={get(n, "gulf", "free text")} gold={gold} />
                <Cell row={get(n, "en", "engine as a tool")} gold={gold} />
                <Cell row={get(n, "gulf", "engine as a tool")} gold={gold} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-sm text-ink-2">{t("ct.tree")}</p>
      <p className="mt-2 text-xs text-muted">{t("ct.note", { settings: data.settings })}</p>
    </Card>
  );
}
