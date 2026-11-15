"use client";

// Watch a cascade: one result travelling through a family, step by step, on the live API. Each run uses its
// own fresh copy of the fictional CAH family (/api/demo/story). The family tree is the stage; beside it, what
// the person sees and what Silsila recorded (the hash-chained audit entries this run created).

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { StatusChip } from "@/components/case";
import { ReasonChip } from "@/components/counsellor";
import { Parts } from "@/components/Parts";
import { PedigreeChart } from "@/components/PedigreeChart";
import { Page } from "@/components/Shell";
import { Button, Card, Chip, ErrorBox, Eyebrow, H1, H2, Loading, Num, Prov, cx } from "@/components/ui";
import { API_URL, ApiError } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { StringKey } from "@/lib/strings";
import type { CaseDetail, Invitation, Part, RelativeView } from "@/lib/types";

const STEPS = 12;
const NOURA = "noura";
const QUESTION_AR = "هل نوقف الحمل؟ وش الأفضل لنا؟";

interface AuditEvent { seq: number; ts: string; actor: string; role: string; action: string; outcome: string; hash: string; case_id: string | null }
interface QueueItem { type: string; id: string; case_id: string | null; reasons: string[]; priority: number }
interface Outcomes { comprehension: { submitted: number; passed: number }; uptake: { opened: number; booked_or_tested: number }; hours: Record<string, number | null> }
interface Inject { attempted: string; blocked: boolean; reason: string | null; approved_original: string }

interface World {
  caseId: string;
  famToken: string;
  couToken: string;
  fam?: CaseDetail;
  inv?: Invitation;
  code?: string;
  queue?: QueueItem[];
  rel?: RelativeView;
  teach?: { score: number; total: number; passed: boolean };
  reply?: { reply: Part[]; escalated: boolean; labels: string[] };
  inject?: Inject;
  outcomes?: Outcomes;
  audit: AuditEvent[];
}

async function call<T>(path: string, opts: { token?: string; body?: unknown; method?: string; query?: Record<string, string> } = {}): Promise<T> {
  const u = new URL(API_URL + path);
  for (const [k, v] of Object.entries(opts.query || {})) u.searchParams.set(k, v);
  const res = await fetch(u.toString(), {
    method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
    headers: { Accept: "application/json", ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}) },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); if (typeof j.detail === "string") detail = j.detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** Perform step `i` on the live API and return the world after it. */
async function perform(i: number, w: World | null, lang: string): Promise<World> {
  if (i === 0 || !w) {
    const s = await call<{ case_id: string; family: { token: string }; counsellor: { token: string } }>("/api/demo/story", { method: "POST" });
    const fam = await call<CaseDetail>(`/api/cases/${s.case_id}`, { token: s.family.token, query: { lang } });
    return withAudit({ caseId: s.case_id, famToken: s.family.token, couToken: s.counsellor.token, fam, audit: [] });
  }
  const next: World = { ...w };
  const refreshFam = async () => {
    next.fam = await call<CaseDetail>(`/api/cases/${w.caseId}`, { token: w.famToken, query: { lang } });
  };
  const refreshQueue = async () => {
    const q = await call<QueueItem[]>("/api/queue", { token: w.couToken });
    next.queue = q.filter((x) => x.case_id === w.caseId);
  };
  switch (i) {
    case 1:
      break; // the report is already on screen; this step explains it
    case 2:
      await call(`/api/cases/${w.caseId}/consents`, { token: w.famToken, body: { scope: "invite", granted: true } });
      await refreshFam();
      break;
    case 3:
      next.inv = await call<Invitation>(`/api/cases/${w.caseId}/invitations`, { token: w.famToken,
        body: { person_id: NOURA, channel: "anonymous_invite" } });
      await refreshQueue();
      break;
    case 4:
      next.inv = await call<Invitation>(`/api/invitations/${w.inv!.id}/approve`, { token: w.couToken, method: "POST" });
      next.code = next.inv.code;
      break;
    case 5:
      next.rel = await call<RelativeView>(`/api/r/${w.code}`, { query: { lang } });
      break;
    case 6: {
      const answers = Object.fromEntries((w.rel?.teachback || []).map((q) => [q.id, "a"]));
      const r = await call<{ score: number; total: number; passed: boolean }>(`/api/r/${w.code}/teachback`, { body: { answers } });
      next.teach = { score: r.score, total: r.total, passed: r.passed };
      break;
    }
    case 7:
      await call(`/api/r/${w.code}/respond`, { method: "POST", query: { action: "book" } });
      break;
    case 8:
      next.reply = await call(`/api/messages`, { body: { text: QUESTION_AR, lang: "ar", invite_code: w.code } });
      await refreshQueue();
      break;
    case 9:
      next.inv = await call<Invitation>(`/api/invitations/${w.inv!.id}/result`, { token: w.couToken, body: { detected: [] } });
      await refreshFam();
      break;
    case 10:
      next.inject = await call<Inject>("/api/demo/inject", { token: w.couToken, method: "POST", query: { lang } });
      break;
    case 11:
      next.outcomes = await call<Outcomes>("/api/outcomes", { token: w.couToken });
      break;
  }
  return withAudit(next);
}

async function withAudit(w: World): Promise<World> {
  const all = await call<{ events: AuditEvent[] }>("/api/audit", { token: w.couToken });
  const mine = all.events.filter((e) => e.case_id === w.caseId || (e.action === "output_gate.block" && w.inject));
  return { ...w, audit: mine.slice(0, 14) };
}

function nouraMark(step: number): { label: StringKey; tone: "info" | "done" | "alert" } | null {
  if (step >= 9) return { label: "cx.mark.tested", tone: "done" };
  if (step >= 8) return { label: "cx.mark.asked", tone: "alert" };
  if (step >= 7) return { label: "cx.mark.booked", tone: "done" };
  if (step >= 6) return { label: "cx.mark.understood", tone: "done" };
  if (step >= 5) return { label: "cx.mark.opened", tone: "info" };
  if (step >= 4) return { label: "cx.mark.approved", tone: "info" };
  if (step >= 3) return { label: "cx.mark.invited", tone: "info" };
  if (step >= 1) return { label: "cx.mark.suggested", tone: "info" };
  return null;
}

export default function CascadePage() {
  const { t, lang } = usePrefs();
  const [snaps, setSnaps] = useState<World[]>([]);
  const [view, setView] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [playing, setPlaying] = useState(false);
  const started = useRef(false);

  const advance = useCallback(async () => {
    if (busy) return;
    if (view < snaps.length - 1) {
      setView(view + 1);
      return;
    }
    if (snaps.length >= STEPS) {
      setPlaying(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const w = await perform(snaps.length, snaps[snaps.length - 1] ?? null, lang);
      setSnaps((s) => [...s, w]);
      setView(snaps.length);
    } catch (e) {
      setError(e);
      setPlaying(false);
    } finally {
      setBusy(false);
    }
  }, [busy, view, snaps, lang]);

  const restart = () => {
    setSnaps([]);
    setView(0);
    setPlaying(false);
    started.current = false;
  };

  useEffect(() => {
    if (!started.current && snaps.length === 0 && !busy) {
      started.current = true;
      void advance();
    }
  }, [snaps.length, busy, advance]);

  useEffect(() => {
    if (!playing) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const id = window.setTimeout(() => void advance(), reduced ? 4000 : 6500);
    return () => window.clearTimeout(id);
  }, [playing, view, advance]);

  const w = snaps[view];
  const step = view;
  const fam = w?.fam;
  const nm = (id: string) => fam?.case.pedigree.people.find((p) => p.id === id)?.name || id;
  const marks: Record<string, { label: string; tone: "info" | "done" | "alert" }> = {};
  if (fam) {
    marks[fam.case.index_person_id] = { label: t("cx.mark.index"), tone: "alert" };
    const m = nouraMark(step);
    if (m) marks[NOURA] = { label: t(m.label), tone: m.tone };
  }
  const who: StringKey = step >= 5 && step <= 8 ? "cx.who.noura" : step === 11 ? "cx.who.programme" : "cx.who.mariam";
  const prevAudit = new Set((snaps[view - 1]?.audit || []).map((e) => e.seq));
  const k = (s: string) => `cx.s${step}.${s}` as StringKey;

  return (
    <Page wide>
      <Eyebrow>{t("cx.eyebrow")}</Eyebrow>
      <H1 className="mt-2">{t("cx.title")}</H1>
      <p className="mt-3 max-w-3xl text-ink-2">{t("cx.lead")}</p>

      <Card className="mt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="primary" onClick={() => setPlaying((p) => !p)} disabled={!w && busy}>
              {playing ? t("cx.pause") : t("cx.play")}
            </Button>
            <Button size="sm" onClick={() => setView((v) => Math.max(0, v - 1))} disabled={view === 0}>{t("cx.prev")}</Button>
            <Button size="sm" onClick={() => void advance()} disabled={busy || (view === STEPS - 1)}>{t("cx.next")}</Button>
            <Button size="sm" variant="quiet" onClick={restart}>{t("cx.restart")}</Button>
          </div>
          <span className="text-sm text-muted" aria-live="polite">{t("cx.step", { n: view + 1, total: STEPS })}</span>
        </div>
        <ol className="mt-4 flex gap-1.5" aria-label={t("cx.title")}>
          {Array.from({ length: STEPS }, (_, i) => (
            <li key={i} className="flex-1">
              <button
                type="button"
                onClick={() => i < snaps.length && setView(i)}
                disabled={i >= snaps.length}
                aria-label={`${i + 1}. ${t(`cx.s${i}.t` as StringKey)}`}
                aria-current={i === view ? "step" : undefined}
                className={cx("block h-2.5 w-full rounded-full", i === view ? "bg-brass" : i < snaps.length ? "bg-accent" : "bg-surface-2")}
              />
            </li>
          ))}
        </ol>
        {w && (
          <div className="mt-5" aria-live="polite">
            <H2>{t(k("t"))}</H2>
            <p className="mt-2 max-w-4xl text-ink">{t(k("d"))}</p>
            <p className="mt-2 max-w-4xl text-sm font-medium text-ink-2">{t(k("n"))}</p>
          </div>
        )}
        {busy && <p className="mt-3 text-sm text-muted" role="status">{!w ? t("cx.starting") : "…"}</p>}
        {error ? <div className="mt-3"><ErrorBox error={error} onRetry={() => void advance()} /></div> : null}
      </Card>

      {!w ? (
        busy ? <Loading /> : null
      ) : (
        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] [&>*]:min-w-0">
          {fam && (
            <div className="min-w-0">
              <PedigreeChart pedigree={fam.case.pedigree} report={fam.report} indexId={fam.case.index_person_id} marks={marks} startFit />
            </div>
          )}
          <div className="grid content-start gap-6 [&>*]:min-w-0">
            <Card>
              <p className="text-xs font-semibold uppercase tracking-wide text-brass">{t("cx.sees", { who: t(who) })}</p>
              <div className="mt-3 grid gap-3">
                {step === 0 && fam && (
                  <>
                    <p className="font-semibold">{fam.case.title}</p>
                    <Parts parts={fam.report.people?.[fam.case.index_person_id === "zayed" ? "mariam" : fam.case.index_person_id]?.sentence} />
                  </>
                )}
                {step === 1 && fam && (
                  <>
                    <p className="font-semibold">{t("cx.topInvites")}</p>
                    <ol className="grid gap-2">
                      {(fam.report.invites || []).slice(0, 3).map((s) => (
                        <li key={s.person_id} className="flex flex-wrap items-center gap-2 text-sm">
                          <bdi className="font-medium">{nm(s.person_id)}</bdi>
                          <ReasonChip code={s.reason_code} />
                        </li>
                      ))}
                    </ol>
                    <Parts parts={fam.report.people?.[NOURA]?.sentence} />
                  </>
                )}
                {step === 2 && fam && (
                  <>
                    <Parts parts={fam.consent_text.invite} />
                    <p className="font-semibold text-accent">✓ {t("cx.permission")}</p>
                  </>
                )}
                {(step === 3 || step === 4) && w.inv && (
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{t("cx.invitationTo", { name: nm(NOURA) })}</p>
                    <StatusChip status={w.inv.status} />
                    <p className="w-full text-sm text-ink-2">{t("cx.anonymous")}</p>
                  </div>
                )}
                {step === 5 && w.rel && (
                  <>
                    <Parts parts={w.rel.message} />
                    <Parts parts={w.rel.information.slice(0, 1)} />
                  </>
                )}
                {step === 6 && w.rel && w.teach && (
                  <>
                    <ul className="grid gap-2 text-sm">
                      {w.rel.teachback.map((q) => (
                        <li key={q.id}>
                          <span className="font-medium">{lang === "ar" ? q.ar : q.en}</span>
                          <span className="block text-ink-2">✓ {lang === "ar" ? q.options[0].ar : q.options[0].en}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="font-semibold text-accent">{t("cx.teachPassed", { score: w.teach.score, total: w.teach.total })}</p>
                  </>
                )}
                {step === 7 && w.rel && (
                  <>
                    <p className="font-semibold text-accent">✓ {t("cx.booked")}</p>
                    <Parts parts={w.rel.consent_note} />
                  </>
                )}
                {step === 8 && w.reply && (
                  <>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t("cx.asked")}</p>
                    <p className="ms-auto max-w-[85%] rounded-2xl rounded-ee-sm bg-accent-soft px-4 py-2" dir="rtl" lang="ar">{QUESTION_AR}</p>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t("cx.reply")}</p>
                    <Parts parts={w.reply.reply} />
                  </>
                )}
                {step === 9 && fam && (
                  <>
                    <p className="flex items-center gap-2 font-semibold"><Prov kind="recorded" />{t("cx.testRecorded", { name: nm(NOURA) })}</p>
                    <Parts parts={fam.report.people?.[NOURA]?.residual_note} />
                  </>
                )}
                {step === 10 && w.inject && (
                  <>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t("cx.approvedInstead")}</p>
                    <p className="rounded-lg border border-line bg-surface p-3 text-sm">{w.inject.approved_original}</p>
                  </>
                )}
                {step === 11 && (
                  <>
                    <p className="font-semibold">{t("cx.more")}</p>
                    <ul className="grid gap-2">
                      <li><Link className="text-accent underline underline-offset-4" href="/twin">{t("cx.moreTwin")}</Link></li>
                      <li><Link className="text-accent underline underline-offset-4" href="/counsellor">{t("cx.moreIntake")}</Link></li>
                      <li><Link className="text-accent underline underline-offset-4" href="/evidence">{t("cx.moreEvidence")}</Link></li>
                    </ul>
                  </>
                )}
              </div>
            </Card>

            <Card>
              <p className="text-xs font-semibold uppercase tracking-wide text-brass">{t("cx.recorded")}</p>
              <div className="mt-3 grid gap-3">
                {step === 1 && fam && (
                  <ul className="grid gap-1.5 text-sm" dir="ltr">
                    {(fam.report.invites || []).slice(0, 3).map((s) => (
                      <li key={s.person_id} className="flex flex-wrap items-center gap-2">
                        <Prov kind="calculated" />
                        <bdi>{nm(s.person_id)}</bdi>
                        <Num>carrier {(100 * s.p_carrier).toFixed(1)}%</Num>
                        {s.p_child_affected != null && <Num>· child affected {(100 * s.p_child_affected).toFixed(2)}%</Num>}
                      </li>
                    ))}
                  </ul>
                )}
                {(step === 3 || step === 8) && w.queue && w.queue[0] && (
                  <div className="rounded-lg border border-accent bg-accent-soft p-3 text-sm">
                    <p className="font-semibold">{t("cx.queueTop")}{step === 8 && w.reply?.escalated ? ` · ${t("cx.escalated")}` : ""}</p>
                    <span className="mt-1 flex flex-wrap gap-1.5">{w.queue[0].reasons.map((r) => <ReasonChip key={r} code={r} />)}</span>
                  </div>
                )}
                {step === 4 && w.inv && (
                  <p className="text-sm"><StatusChip status={w.inv.status} /> {t("cx.signedBy", { name: String(w.inv.history.find((h) => h.status === "approved")?.signed_by ?? "") })}</p>
                )}
                {step === 9 && w.inv && <p className="text-sm font-semibold text-accent">✓ {t("cx.closed")}</p>}
                {step === 10 && w.inject && (
                  <div className="rounded-lg border-2 border-dashed border-ink-2 bg-surface-2 p-3 text-sm">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t("cx.attempted")}</p>
                    <p className="mt-1 line-through">{w.inject.attempted}</p>
                    <p className="mt-2 font-semibold">{w.inject.blocked ? t("cx.blocked") : "—"}</p>
                  </div>
                )}
                {step === 11 && w.outcomes && (
                  <ul className="grid gap-1 text-sm">
                    <li>{t("oc.comprehension")}: <Num>{w.outcomes.comprehension.passed}/{w.outcomes.comprehension.submitted}</Num></li>
                    <li>{t("oc.uptake")}: <Num>{w.outcomes.uptake.booked_or_tested}/{w.outcomes.uptake.opened}</Num></li>
                  </ul>
                )}
                <p className="text-xs text-muted">{t("cx.recordedLead")}</p>
                {w.audit.length === 0 ? (
                  <p className="text-sm text-muted">{t("cx.noEvents")}</p>
                ) : (
                  <ol className="grid gap-1 font-mono text-xs" dir="ltr">
                    {w.audit.map((e) => (
                      <li key={e.seq} className={cx("flex flex-wrap gap-x-2 rounded px-1.5 py-0.5", !prevAudit.has(e.seq) && view > 0 && "bg-accent-soft")}>
                        <span className="text-muted">#{e.seq}</span>
                        <span>{e.action}</span>
                        <span className="text-ink-2">{e.role}</span>
                        {e.outcome !== "success" && <span className="font-semibold">{e.outcome}</span>}
                        <span className="text-muted">{e.hash.slice(0, 10)}…</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </Card>
          </div>
          <p className="text-xs text-muted xl:col-span-2"><Chip>{w.caseId}</Chip> {t("app.prototype")}</p>
        </div>
      )}
    </Page>
  );
}
