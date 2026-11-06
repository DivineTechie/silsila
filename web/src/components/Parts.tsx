"use client";

import { usePrefs } from "@/lib/prefs";
import type { Part } from "@/lib/types";
import { Prov, cx } from "./ui";

/** Short citation chip for a quoted MedlinePlus paragraph. */
export function CitationChip({ part }: { part: Part }) {
  const label = part.attribution || part.source_title || "Source";
  const short = label.includes("MedlinePlus") ? "MedlinePlus, National Library of Medicine" : label;
  const content = (
    <>
      <svg aria-hidden="true" viewBox="0 0 16 16" className="h-3 w-3 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M3 2.5h7l3 3v8H3z" />
        <path d="M5.5 7h5M5.5 9.5h5" />
      </svg>
      <span>{short}</span>
      {part.source_title && <span className="opacity-75">· {part.source_title}</span>}
    </>
  );
  const cls =
    "tag-source mt-1.5 inline-flex max-w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium leading-snug";
  return part.url ? (
    <a href={part.url} target="_blank" rel="noreferrer noopener" dir="ltr" lang="en" className={cx(cls, "underline-offset-2 hover:underline")}>
      {content}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  ) : (
    <span dir="ltr" lang="en" className={cls}>{content}</span>
  );
}

/**
 * Render approved parts exactly as the API gave them. Template parts carry
 * the "Approved wording" label; source parts carry "Quoted source" and a
 * citation chip. Quoted MedlinePlus text is English (it is quoted verbatim).
 */
export function Parts({
  parts,
  className,
  compact = false,
  showIds = false,
}: {
  parts: Part[] | null | undefined;
  className?: string;
  compact?: boolean;
  showIds?: boolean;
}) {
  const { lang } = usePrefs();
  if (!parts || parts.length === 0) return null;
  return (
    <div className={cx("flex flex-col", compact ? "gap-2" : "gap-4", className)}>
      {parts.map((p, i) => (
        <div key={`${p.id}-${i}`} className="min-w-0" data-part-id={p.id} data-part-type={p.type}>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Prov kind={p.type === "source" ? "source" : "template"} />
            {showIds && <code className="text-[0.7rem] text-muted">{p.id}</code>}
          </div>
          {p.type === "source" ? (
            <blockquote
              lang="en"
              dir="ltr"
              className={cx(
                "border-s-2 border-line-strong ps-3 text-ink-2",
                compact ? "text-sm" : "text-[0.95rem] leading-relaxed",
                lang === "ar" && "text-start",
              )}
            >
              {p.text}
            </blockquote>
          ) : (
            <p className={cx("text-ink", compact ? "text-sm" : "text-[0.98rem] leading-relaxed")}>{p.text}</p>
          )}
          {p.type === "source" && <CitationChip part={p} />}
        </div>
      ))}
    </div>
  );
}
