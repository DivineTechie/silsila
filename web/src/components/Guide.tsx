"use client";

// "Ask about Silsila": a guide to the tool itself. It is NOT a language model. The API matches the words of a
// question to one of a fixed set of answers and, for some answers, runs a real lookup (the exact engine, the
// evidence files, the audit chain, the parameter register) and returns the values with their sources. When
// nothing matches it says so. It does not answer personal or medical questions.
//
// It is shown to visitors, judges and staff. It is deliberately absent from a relative's invitation page and
// from a family's case, where every sentence is approved wording or a verbatim quotation.

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { Lang } from "@/lib/types";
import { Button, Num, cx, inputCls } from "./ui";

interface Fact { label: string; value: string; source: string }
interface Source { label: string; path?: string; url?: string }
interface Suggestion { id: string; question: string }
interface Answer {
  kind: "answer" | "no_match" | "handoff";
  id?: string;
  question?: string;
  answer: string;
  facts?: Fact[];
  tool?: { name: string; description: string; ms: number } | null;
  sources?: Source[];
  method?: string;
  suggestions: Suggestion[];
  not_ai: string;
}
interface Topics { not_ai: Record<Lang, string>; topics: { id: string; q_en: string; q_ar: string }[] }
interface Turn { asked: string; out: Answer | null; error?: boolean }

const STARTERS = ["what", "no_ai_text", "relationship", "accuracy", "hosting", "limits"];

export function GuideLauncher() {
  const pathname = usePathname();
  const { t, lang } = usePrefs();
  const [open, setOpen] = useState(false);
  const [topics, setTopics] = useState<Topics | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    if (!topics) api<Topics>("/api/guide", { auth: false }).then(setTopics).catch(() => {});
  }, [open, topics]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  // Not on a relative's page or inside a family's case: those show only approved wording and quotations.
  if (pathname.startsWith("/r/") || pathname.startsWith("/family")) return null;

  async function ask(question: string, id?: string) {
    const asked = question.trim();
    if (!asked || busy) return;
    setBusy(true);
    setText("");
    setTurns((x) => [...x, { asked, out: null }]);
    try {
      const out = await api<Answer>("/api/guide/ask", { body: id ? { id, lang } : { text: asked.slice(0, 400), lang }, auth: false });
      setTurns((x) => [...x.slice(0, -1), { asked, out }]);
    } catch {
      setTurns((x) => [...x.slice(0, -1), { asked, out: null, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  const starters = (topics?.topics || []).filter((x) => STARTERS.includes(x.id));
  return (
    <div
      className="fixed bottom-4 end-4 z-40 flex flex-col items-end gap-2 print:hidden"
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      {open && (
        <div
          id="guide-panel"
          role="dialog"
          aria-label={t("guide.title")}
          className="flex max-h-[min(78vh,42rem)] w-[min(27rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-line-strong bg-surface shadow-2xl"
        >
          <div className="flex items-start justify-between gap-3 border-b border-line bg-surface-2 px-4 py-3">
            <div>
              <p className="font-semibold text-ink">{t("guide.title")}</p>
              <p className="mt-0.5 text-xs text-ink-2">{topics?.not_ai[lang] || t("guide.notAi")}</p>
            </div>
            <button type="button" onClick={() => setOpen(false)} aria-label={t("guide.close")} className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-2 hover:bg-surface">
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" /></svg>
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3" tabIndex={0} role="log" aria-label={t("guide.log")} aria-live="polite">
            {turns.length === 0 && (
              <div>
                <p className="text-sm text-ink-2">{t("guide.intro")}</p>
                <ul className="mt-3 grid gap-1.5">
                  {starters.map((s) => (
                    <li key={s.id}>
                      <button type="button" onClick={() => void ask(lang === "ar" ? s.q_ar : s.q_en, s.id)} className="w-full rounded-lg border border-line-strong px-3 py-2 text-start text-sm text-ink hover:border-accent hover:bg-accent-soft">
                        {lang === "ar" ? s.q_ar : s.q_en}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="grid gap-4">
              {turns.map((turn, i) => (
                <div key={i} className="grid gap-2">
                  <p className="ms-auto max-w-[88%] rounded-2xl rounded-ee-sm bg-accent-soft px-3 py-2 text-sm text-ink" dir="auto">{turn.asked}</p>
                  {turn.error ? (
                    <p className="text-sm text-ink-2">{t("common.network")}</p>
                  ) : !turn.out ? (
                    <p className="text-sm text-muted">…</p>
                  ) : (
                    <div className={cx("rounded-xl border p-3 text-sm", turn.out.kind === "answer" ? "border-line bg-surface" : "border-notice-line bg-notice")}>
                      <p className="leading-relaxed text-ink">{turn.out.answer}</p>
                      {turn.out.facts && turn.out.facts.length > 0 && (
                        <div className="mt-3 rounded-lg border border-line bg-surface-2/60 p-2.5">
                          <p className="text-[0.68rem] font-semibold uppercase tracking-wide text-ink-2">
                            {t("guide.lookup")}{turn.out.tool ? <> · <span dir="ltr" lang="en">{turn.out.tool.description}</span> <Num>({Math.round(turn.out.tool.ms)} ms)</Num></> : null}
                          </p>
                          {lang === "ar" && <p className="mt-1 text-[0.68rem] text-muted">{t("guide.lookupNote")}</p>}
                          <dl className="mt-1.5 grid gap-2" dir="auto">
                            {turn.out.facts.map((f, k) => (
                              <div key={k}>
                                <dt className="text-xs text-ink-2" dir="auto">{f.label}</dt>
                                <dd className="font-medium text-ink [overflow-wrap:anywhere]" dir="auto">{f.value}</dd>
                                <dd className="text-[0.68rem] text-muted [overflow-wrap:anywhere]" dir="ltr" lang="en">
                                  {/^https?:\/\//.test(f.source) ? <a className="underline" href={f.source} target="_blank" rel="noreferrer">{f.source}</a> : f.source}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        </div>
                      )}
                      {turn.out.sources && turn.out.sources.length > 0 && (
                        <p className="mt-2 text-xs text-ink-2">
                          {t("guide.sources")}:{" "}
                          {turn.out.sources.map((s, k) => (
                            <span key={k}>
                              {k > 0 && " · "}
                              {s.url ? <a className="text-accent underline" href={s.url} target="_blank" rel="noreferrer" dir="ltr" lang="en">{s.label}</a>
                                : <span dir="ltr" lang="en">{s.label} <code className="text-[0.68rem] text-muted">{s.path}</code></span>}
                            </span>
                          ))}
                        </p>
                      )}
                      {turn.out.method && <p className="mt-1.5 text-[0.68rem] text-muted" dir="ltr" lang="en">{turn.out.method}</p>}
                      {i === turns.length - 1 && turn.out.suggestions.length > 0 && (
                        <ul className="mt-3 flex flex-wrap gap-1.5">
                          {turn.out.suggestions.slice(0, 4).map((s) => (
                            <li key={s.id}>
                              <button type="button" onClick={() => void ask(s.question, s.id)} className="rounded-full border border-line-strong px-2.5 py-1 text-start text-xs text-ink hover:border-accent hover:bg-accent-soft">
                                {s.question}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div ref={end} />
          </div>
          <form
            className="flex gap-2 border-t border-line p-3"
            onSubmit={(e) => {
              e.preventDefault();
              void ask(text);
            }}
          >
            <label htmlFor="guide-q" className="sr-only">{t("guide.placeholder")}</label>
            <input id="guide-q" ref={input} value={text} onChange={(e) => setText(e.target.value)} maxLength={400} placeholder={t("guide.placeholder")}
              autoComplete="off" className={cx(inputCls, "min-h-10 text-sm")} />
            <Button type="submit" variant="primary" size="sm" className="min-h-10" disabled={busy || !text.trim()}>{t("guide.ask")}</Button>
          </form>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="guide-panel"
        className="inline-flex min-h-12 items-center gap-2 rounded-full bg-accent px-4 text-sm font-semibold text-accent-ink shadow-lg hover:opacity-90"
      >
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M4 4.5h12v8.5H9l-3.5 3v-3H4z" />
          <path d="M8 8.2a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9M10 12.6v.1" />
        </svg>
        {t("guide.open")}
      </button>
    </div>
  );
}
