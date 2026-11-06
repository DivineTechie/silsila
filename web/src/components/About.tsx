"use client";

import { usePrefs } from "@/lib/prefs";
import { Prov, type ProvKind } from "./ui";

/** "About this information": what each provenance label means, and that no
 *  text in Silsila is written by AI. */
export function AboutInfo({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const { t } = usePrefs();
  const kinds: ProvKind[] = ["recorded", "calculated", "source", "template"];
  return (
    <details open={defaultOpen} className="group rounded-2xl border border-line bg-surface-2/60 p-4 sm:px-6">
      <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-3 font-semibold text-ink">
        <span className="flex items-center gap-2">
          <svg viewBox="0 0 20 20" className="h-5 w-5 text-accent" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <circle cx="10" cy="10" r="7.5" />
            <path d="M10 9v5M10 6.2v.1" strokeLinecap="round" />
          </svg>
          {t("about.title")}
        </span>
        <span aria-hidden="true" className="text-muted transition-transform group-open:rotate-180">⌄</span>
      </summary>
      <div className="mt-3 space-y-3 text-sm text-ink-2">
        <p className="font-medium text-ink">{t("about.noai")}</p>
        <p>{t("about.labels")}</p>
        <dl className="grid gap-2 sm:grid-cols-2">
          {kinds.map((k) => (
            <div key={k} className="rounded-lg border border-line bg-surface p-3">
              <dt>
                <Prov kind={k} />
              </dt>
              <dd className="mt-1.5">{t(`prov.${k}.d`)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </details>
  );
}
