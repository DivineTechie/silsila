"use client";

// "On this page": a list of the page's sections, built from its level-2 headings once the content has
// loaded, so a long page (Evidence has 18 sections) can be reached in one click.

import { useEffect, useState } from "react";
import { usePrefs } from "@/lib/prefs";

export function OnThisPage({ ready, skip = [] }: { ready: unknown; skip?: string[] }) {
  const { t, lang } = usePrefs();
  const [items, setItems] = useState<{ id: string; text: string }[]>([]);
  useEffect(() => {
    const id = window.setTimeout(() => {
      const found: { id: string; text: string }[] = [];
      document.querySelectorAll<HTMLElement>("main h2").forEach((h, i) => {
        if (!h.id) h.id = `section-${i + 1}`;
        if (skip.includes(h.id)) return;
        h.style.scrollMarginTop = "5rem";
        found.push({ id: h.id, text: h.innerText.trim() });
      });
      setItems(found);
    }, 50);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rebuilt when the content or language changes
  }, [ready, lang]);
  if (items.length < 3) return null;
  return (
    <nav aria-label={t("toc.title")} className="rounded-2xl border border-line bg-surface p-4 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{t("toc.title")}</p>
      <ol className="mt-2 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2 xl:grid-cols-3">
        {items.map((it, i) => (
          <li key={it.id} className="flex gap-2">
            <span aria-hidden="true" className="w-5 shrink-0 text-end tabular-nums text-muted">{i + 1}</span>
            <a href={`#${it.id}`} className="text-accent underline-offset-4 hover:underline">{it.text}</a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
