"use client";

// Announced UAE programmes that Silsila connects to (docs/evidence/uae_context.json). Reported figures with
// their sources; none is a Silsila result. Conditional wording is marked where a source does not say something.

import { Card, Chip, H2 } from "./ui";
import { usePrefs } from "@/lib/prefs";

interface Item {
  id: string;
  fact_en: string;
  fact_ar: string;
  source: string;
  url: string;
  conditional: boolean;
  silsila_en: string;
  silsila_ar: string;
}

export interface UaeContext {
  kind: "uae_context";
  retrieved: string;
  not_found: string;
  items: Item[];
  newborn_projection?: { index_newborns_per_year: number; source: string };
}

export function isUaeContext(d: unknown): d is UaeContext {
  return !!d && typeof d === "object" && (d as { kind?: unknown }).kind === "uae_context" && Array.isArray((d as { items?: unknown }).items);
}

export function ProgrammeContext({ doc }: { doc: UaeContext }) {
  const { t, lang } = usePrefs();
  return (
    <Card aria-labelledby="ctx-h">
      <p className="font-mono text-xs text-muted" dir="ltr">docs/evidence/uae_context.json</p>
      <H2 id="ctx-h" className="mt-1">{t("ctx.title")}</H2>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{t("ctx.lead", { date: doc.retrieved })}</p>
      <ul className="mt-4 grid gap-3">
        {doc.items.map((it) => (
          <li key={it.id} className="grid gap-3 rounded-xl border border-line bg-surface p-4 md:grid-cols-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{t("ctx.reported")}</p>
              <p className="mt-1 text-sm">{lang === "ar" ? it.fact_ar : it.fact_en}</p>
              <a className="mt-2 inline-block text-xs text-accent underline underline-offset-2" href={it.url} target="_blank" rel="noreferrer" dir="ltr" lang="en">
                {it.source}
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            </div>
            <div>
              <p className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-2">
                {t("ctx.fit")}
                {it.conditional && <Chip>{t("ctx.conditional")}</Chip>}
              </p>
              <p className="mt-1 text-sm text-ink-2">{lang === "ar" ? it.silsila_ar : it.silsila_en}</p>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm font-medium text-ink-2">{t("ctx.notFound")}</p>
    </Card>
  );
}
