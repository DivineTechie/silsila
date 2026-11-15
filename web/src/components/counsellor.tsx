"use client";

import { ResetDemo } from "./JudgeMode";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { age, fmtDate, fmtNum, usePrefs } from "@/lib/prefs";
import type { StringKey } from "@/lib/strings";
import type { AuditResponse, ChainStatus, Health, InboxMessage, InjectResult, QueueItem, Report, SourceCitation } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";
import { Parts } from "./Parts";
import { SectionTitle } from "./case";
import { Button, Card, Chip, ErrorBox, Field, H3, Loading, Notice, Prov, cx, inputCls } from "./ui";

// ------------------------------------------------------------ work queue --
const REASON_LABELS: Record<string, { en: string; ar: string }> = {
  needs_approval: { en: "needs approval", ar: "تحتاج اعتماداً" },
  pregnancy_in_family: { en: "pregnancy in family", ar: "حمل في العائلة" },
  overdue: { en: "overdue", ar: "متأخر" },
  results_do_not_fit: { en: "results do not fit", ar: "نتائج غير متوافقة" },
  crisis: { en: "crisis", ar: "أزمة" },
  decision_request: { en: "decision request", ar: "طلب قرار" },
  religious: { en: "religious question", ar: "سؤال ديني" },
  third_party: { en: "about another person", ar: "عن شخص آخر" },
  distress: { en: "distress", ar: "ضيق" },
  booking: { en: "booking", ar: "حجز" },
  information: { en: "information", ar: "معلومات" },
  unclassified: { en: "unclassified", ar: "غير مصنف" },
};

export function ReasonChip({ code }: { code: string }) {
  const { lang, t } = usePrefs();
  // Queue reasons have labels above; the engine's "whom to tell first" reasons are interface strings.
  const key = `reason.${code}`;
  const fromStrings = t(key as StringKey);
  return <Chip>{REASON_LABELS[code]?.[lang] || (fromStrings !== key ? fromStrings : code.replace(/_/g, " "))}</Chip>;
}

export function PriorityBadge({ p }: { p: number }) {
  const { t } = usePrefs();
  const key = (["c.p0", "c.p1", "c.p2", "c.p3", "c.p4", "c.p5"] as const)[Math.min(5, Math.max(0, p))];
  // Neutral weight scale: higher priority = heavier ink, never red/green.
  return (
    <span
      className={cx(
        "inline-flex min-w-20 items-center justify-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold",
        p === 0 ? "bg-ink text-bg" : p === 1 ? "border-2 border-ink text-ink" : "border border-line-strong text-ink-2",
      )}
    >
      <span className="tabular-nums">P{p}</span> {t(key)}
    </span>
  );
}

export function Queue({ onOpenMessages }: { onOpenMessages: () => void }) {
  const { t, session } = usePrefs();
  const { data, error, loading, reload } = useLoad(() => api<QueueItem[]>("/api/queue"), session?.token || "");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data?.length) return <p className="text-muted">{t("c.queueEmpty")}</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface" tabIndex={0} role="region" aria-label={t("c.queue")}>
      <table className="w-full min-w-[640px] text-sm">
        <thead className="border-b border-line text-start text-xs uppercase tracking-wide text-muted">
          <tr>
            <th scope="col" className="px-4 py-3 text-start font-semibold">{t("c.priority")}</th>
            <th scope="col" className="px-4 py-3 text-start font-semibold">{t("c.type")}</th>
            <th scope="col" className="px-4 py-3 text-start font-semibold">{t("c.reasons")}</th>
            <th scope="col" className="px-4 py-3 text-start font-semibold">{t("c.age")}</th>
            <th scope="col" className="px-4 py-3 text-start font-semibold"><span className="sr-only">{t("c.open")}</span></th>
          </tr>
        </thead>
        <tbody>
          {data.map((q) => (
            <tr key={`${q.type}-${q.id}`} className="border-b border-line last:border-0">
              <td className="px-4 py-3"><PriorityBadge p={q.priority} /></td>
              <td className="px-4 py-3">
                <span className="font-medium">{t(`c.type.${q.type}`)}</span>
                {q.status && <span className="ms-2 text-muted">{t(`status.${q.status}`)}</span>}
                {q.case_id && <span className="block text-xs text-muted" dir="ltr">{q.case_id}</span>}
              </td>
              <td className="px-4 py-3">
                <span className="flex flex-wrap gap-1.5">{q.reasons.map((r) => <ReasonChip key={r} code={r} />)}</span>
              </td>
              <td className="px-4 py-3 tabular-nums text-ink-2" title={fmtDate(q.since)}>{age(q.since, t)}</td>
              <td className="px-4 py-3 text-end">
                {q.type === "message" ? (
                  <Button size="sm" onClick={onOpenMessages}>{t("c.open")}</Button>
                ) : q.case_id ? (
                  <Link href={`/counsellor/cases/${q.case_id}${q.type === "invitation" ? "?tab=invitations" : ""}`} className="inline-flex min-h-9 items-center rounded-lg border border-line-strong px-3 font-medium hover:bg-surface-2">
                    {t("c.open")}
                  </Link>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// -------------------------------------------------------------- messages --
export function Inbox() {
  const { t, session } = usePrefs();
  const { data, error, loading, reload } = useLoad(() => api<InboxMessage[]>("/api/messages"), session?.token || "");
  const [busy, setBusy] = useState<string | null>(null);
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data?.length) return <p className="text-muted">{t("c.noMessages")}</p>;
  return (
    <ul className="grid gap-3">
      {data.map((m) => (
        <li key={m.id} className={cx("rounded-xl border bg-surface p-4", m.escalate && !m.resolved ? "border-ink-2" : "border-line")}>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
            <span dir="ltr">
              {m.sender} · {m.case_id || "—"} · {fmtDate(m.created)}
            </span>
            <span className={cx("rounded-full px-2 py-0.5 font-semibold", m.resolved ? "bg-surface-2 text-ink-2" : "bg-accent-soft text-ink")}>
              {m.resolved ? t("c.resolved") : t("c.unresolved")}
            </span>
          </div>
          <p className="mt-2 flex flex-wrap items-start gap-2">
            <Prov kind="recorded" />
            <span lang={m.lang} dir="auto" className="min-w-0 flex-1">{m.text}</span>
          </p>
          <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
            <LabelGroup title={t("c.ruleLabels")} labels={m.rule_labels} />
            <LabelGroup title={t("c.ngramLabels")} labels={m.ngram_labels} />
            <LabelGroup
              title={t("c.modelLabels")}
              labels={m.model ? m.model_labels : undefined}
              note={m.model ? t("c.modelUsed", { m: m.model }) : t("c.noModel")}
            />
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-medium text-ink-2">{t("c.reply")}</summary>
            <Parts parts={m.reply} className="mt-2" compact showIds />
          </details>
          {!m.resolved && (
            <Button
              size="sm"
              className="mt-3"
              disabled={busy === m.id}
              onClick={async () => {
                setBusy(m.id);
                try {
                  await api(`/api/messages/${m.id}/resolve`, { method: "POST" });
                  await reload();
                } finally {
                  setBusy(null);
                }
              }}
            >
              {t("c.resolve")}
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function LabelGroup({ title, labels, note }: { title: string; labels?: string[]; note?: string }) {
  const { t } = usePrefs();
  return (
    <div className="rounded-lg border border-line p-2.5">
      <p className="text-xs font-semibold text-muted">{title}</p>
      <p className="mt-1 flex flex-wrap gap-1.5">
        {labels === undefined ? (
          <span className="text-xs text-muted">{t("c.notRun")}</span>
        ) : labels.length ? (
          labels.map((l) => <ReasonChip key={l} code={l} />)
        ) : (
          "—"
        )}
      </p>
      {note && <p className="mt-1 text-xs text-muted">{note}</p>}
    </div>
  );
}

// ----------------------------------------------------------------- audit --
export function ChainBadge({ chain }: { chain: ChainStatus }) {
  const { t } = usePrefs();
  return (
    <span
      role="status"
      className={cx(
        "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-semibold",
        chain.intact ? "bg-accent-soft text-ink" : "border-2 border-dashed border-ink bg-surface-2 text-ink",
      )}
    >
      <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        {chain.intact ? (
          <path d="M8 12l4-4M6.5 9.5l-2 2a2.5 2.5 0 0 0 3.5 3.5l2-2M13.5 10.5l2-2a2.5 2.5 0 0 0-3.5-3.5l-2 2" />
        ) : (
          <path d="M6.5 9.5l-2 2a2.5 2.5 0 0 0 3.5 3.5l2-2M13.5 10.5l2-2a2.5 2.5 0 0 0-3.5-3.5l-2 2M4 4l2 2M16 16l-2-2" />
        )}
      </svg>
      {t("c.chain")}: {chain.intact ? t("c.chainIntact") : t("c.chainBroken", { n: chain.first_broken_seq ?? "?" })}
      <span className="font-normal text-ink-2">· {t("c.events", { n: chain.events })}</span>
    </span>
  );
}

export function AuditLog({ caseId, refreshKey = 0 }: { caseId?: string; refreshKey?: number }) {
  const { t, session } = usePrefs();
  const [onlyCase, setOnlyCase] = useState(!!caseId);
  const { data, error, loading, reload } = useLoad(
    () => api<AuditResponse>("/api/audit", { query: { case_id: onlyCase ? caseId : undefined } }),
    `${session?.token}:${onlyCase}:${refreshKey}`,
  );
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const broken = data.chain.first_broken_seq;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <ChainBadge chain={data.chain} />
        <div className="flex items-center gap-3">
          {caseId && (
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="h-5 w-5 accent-[var(--accent)]" checked={onlyCase} onChange={(e) => setOnlyCase(e.target.checked)} />
              {t("c.filterCase")}
            </label>
          )}
          <Button size="sm" onClick={reload}>{t("common.retry")}</Button>
        </div>
      </div>
      <div className="max-h-[32rem] overflow-auto rounded-xl border border-line bg-surface" tabIndex={0} role="region" aria-label={t("c.audit")}>
        <table className="w-full min-w-[720px] text-sm">
          <thead className="sticky top-0 bg-surface text-xs uppercase tracking-wide text-muted">
            <tr className="border-b border-line">
              {(["c.seq", "c.when", "c.actor", "c.action", "c.entity", "c.outcome"] as const).map((k) => (
                <th key={k} scope="col" className="px-3 py-2 text-start font-semibold">{t(k)}</th>
              ))}
              <th scope="col" className="px-3 py-2 text-start font-semibold">hash</th>
            </tr>
          </thead>
          <tbody dir="ltr">
            {data.events.map((e) => (
              <tr key={e.seq} className={cx("border-b border-line last:border-0", broken !== null && e.seq >= broken && "bg-surface-2")}>
                <td className="px-3 py-2 tabular-nums font-semibold">
                  {e.seq}
                  {broken === e.seq && <span className="ms-1 text-xs">✕</span>}
                </td>
                <td className="px-3 py-2 whitespace-nowrap tabular-nums text-ink-2">{fmtDate(e.ts)}</td>
                <td className="px-3 py-2">{e.actor}<span className="block text-xs text-muted">{e.role}</span></td>
                <td className="px-3 py-2 font-mono text-xs">{e.action}</td>
                <td className="px-3 py-2 text-xs text-ink-2">{e.entity || e.case_id || "—"}</td>
                <td className="px-3 py-2 text-xs">{e.outcome}</td>
                <td className="px-3 py-2 font-mono text-[0.7rem] text-muted" title={e.hash}>{e.hash.slice(0, 10)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ demo tools --
export function DemoTools({ onChanged }: { onChanged: () => void }) {
  const { t, lang } = usePrefs();
  const health = useLoad(() => api<Health>("/api/health", { auth: false }), "health");
  const [inj, setInj] = useState<InjectResult | null>(null);
  const [seq, setSeq] = useState("2");
  const [tamper, setTamper] = useState<ChainStatus | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (!health.data?.demo_mode) return null;

  async function run<T>(fn: () => Promise<T>, set: (v: T) => void) {
    setBusy(true);
    setError(null);
    try {
      set(await fn());
      onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="border-dashed">
      <SectionTitle>{t("c.demo")}</SectionTitle>
      <p className="-mt-2 text-sm text-muted">{t("c.demoHint")}</p>
      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div>
          <H3>{t("c.inject")}</H3>
          <Button
            className="mt-3"
            size="sm"
            variant="primary"
            disabled={busy}
            onClick={() => run(() => api<InjectResult>("/api/demo/inject", { method: "POST", query: { lang } }), setInj)}
          >
            {t("c.injectRun")}
          </Button>
          {inj && (
            <div className="mt-4 grid gap-3 sm:grid-cols-2" role="status">
              <div className="rounded-lg border-2 border-dashed border-ink-2 bg-surface-2 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t("c.attempted")}</p>
                <p className="mt-2 text-sm line-through decoration-1">{inj.attempted}</p>
                <p className="mt-3 text-sm font-semibold">{inj.blocked ? t("c.blocked") : t("c.notBlocked")}</p>
                {inj.reason && <p className="mt-1 text-xs text-ink-2">{inj.reason}</p>}
              </div>
              <div className="rounded-lg border border-line bg-surface p-3">
                <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
                  {t("c.approvedWording")} <Prov kind="template" />
                </p>
                <p className="mt-2 text-sm">{inj.approved_original}</p>
                <code className="mt-2 block text-xs text-muted">reply.decision_request</code>
              </div>
            </div>
          )}
        </div>
        <div>
          <H3>{t("c.tamper")}</H3>
          <form
            className="mt-3 flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() => api<ChainStatus>("/api/demo/tamper", { method: "POST", query: { seq } }), setTamper);
            }}
          >
            <Field label={t("c.tamperSeq")} htmlFor="tamper-seq">
              <input id="tamper-seq" type="number" min={1} inputMode="numeric" className={cx(inputCls, "w-28")} value={seq} onChange={(e) => setSeq(e.target.value)} />
            </Field>
            <Button type="submit" size="md" disabled={busy || !seq}>{t("c.tamperRun")}</Button>
          </form>
          <p className="mt-2 text-xs text-muted">{t("c.tamperWarn")}</p>
          {tamper && <div className="mt-3"><ChainBadge chain={tamper} /></div>}
        </div>
      </div>
      <div className="mt-6 border-t border-line pt-4">
        <ResetDemo onDone={onChanged} />
      </div>
      {error ? <div className="mt-4"><ErrorBox error={error} /></div> : null}
    </Card>
  );
}

// ------------------------------------------------------ show the working --
function Cite({ s }: { s: SourceCitation }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3 text-sm">
      {s.citation && <p className="text-ink">{s.citation}</p>}
      <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2">
        {s.pmid && <span>PMID <a className="text-accent underline" href={`https://pubmed.ncbi.nlm.nih.gov/${s.pmid}/`} target="_blank" rel="noreferrer">{s.pmid}</a></span>}
        {s.url && !s.pmid && <a className="break-all text-accent underline" href={s.url} target="_blank" rel="noreferrer">{s.url}</a>}
        {s.population && <span>{s.population}</span>}
        {s.sample_size !== undefined && <span>n = {s.sample_size.toLocaleString("en-US")}</span>}
      </p>
      {s.note && <p className="mt-1.5 text-xs text-muted">{s.note}</p>}
    </div>
  );
}

const th = "px-3 py-2 text-start text-xs font-semibold uppercase tracking-wide text-muted";
const td = "px-3 py-2 align-top";

export function Working({ report, names }: { report: Report; names: Record<string, string> }) {
  const { t } = usePrefs();
  const L = report.locus;
  if (!L) {
    return (
      <div className="grid gap-4">
        {report.message && <Parts parts={report.message} />}
        {report.reason && <Notice>{report.reason}</Notice>}
      </div>
    );
  }
  return (
    <div className="grid gap-8 [&>*]:min-w-0" dir="ltr" lang="en">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <span><span className="text-muted">{t("c.engine")}:</span> {report.engine}</span>
        <span><span className="text-muted">{t("c.computedAt")}:</span> {fmtDate(report.computed_at)}</span>
        <span className="flex items-center gap-2"><Prov kind="recorded" /><span className="text-muted">{t("c.backgroundF")}:</span> {L.background_f}</span>
      </div>

      <section>
        <SectionTitle>{t("c.alleles")} · {L.gene}</SectionTitle>
        <div className="overflow-x-auto rounded-xl border border-line bg-surface" tabIndex={0} role="region" aria-label={`${t("c.alleles")} ${L.gene}`}>
          <table className="w-full min-w-[560px] text-sm">
            <thead className="border-b border-line"><tr>
              <th className={th}>{t("c.allele")}</th><th className={th}>{t("c.label")}</th>
              <th className={th}>{t("c.frequency")}</th><th className={th}>{t("c.detection")}</th><th className={th}>{t("c.pathogenic")}</th>
            </tr></thead>
            <tbody>
              {L.alleles.map((a) => (
                <tr key={a.id} className="border-b border-line last:border-0">
                  <td className={cx(td, "font-mono font-semibold")}>{a.id}</td>
                  <td className={td}>{a.label}</td>
                  <td className={cx(td, "tabular-nums")}><span className="me-2"><Prov kind="calculated" /></span>{fmtNum(a.frequency, 6)}</td>
                  <td className={cx(td, "tabular-nums")}><span className="me-2"><Prov kind="recorded" /></span>{a.detection_rate}</td>
                  <td className={td}>{a.pathogenic ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <SectionTitle>{t("c.derivations")}</SectionTitle>
        <div className="grid gap-3">
          {L.derivations.map((d, i) => (
            <div key={i} className="rounded-xl border border-line bg-surface p-4 text-sm">
              <p className="font-semibold">{t("c.allele")} <span className="font-mono">{d.allele}</span> · {d.measure.replace(/_/g, " ")}</p>
              <p className="mt-2 flex flex-wrap items-center gap-2"><Prov kind="recorded" /><span className="text-muted">{t("c.published")}:</span> <span className="tabular-nums">{fmtNum(d.published_value, 6)}</span></p>
              <p className="mt-2 text-muted">{t("c.formula")}</p>
              <pre className="mt-1 overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs" tabIndex={0} role="region" aria-label={`${t("c.formula")} ${d.allele}`}>{d.formula}</pre>
              <p className="mt-2 text-muted">{t("c.inputs")}</p>
              <ul className="mt-1 flex flex-wrap gap-2 font-mono text-xs">
                {Object.entries(d.inputs).map(([k, v]) => (
                  <li key={k} className="rounded bg-surface-2 px-2 py-1">{k} = {fmtNum(v, 6)}</li>
                ))}
              </ul>
              <p className="mt-2 flex flex-wrap items-center gap-2"><Prov kind="calculated" /><span className="text-muted">{t("c.result")}:</span> <span className="font-mono">q = {fmtNum(d.allele_frequency, 6)}</span></p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <SectionTitle>{t("c.sources")}</SectionTitle>
        <div className="grid gap-2">
          {L.sources.map((s, i) => (
            <div key={i}>
              <p className="mb-1 text-xs font-semibold text-muted">{t("c.allele")} {s.allele}</p>
              <Cite s={s} />
            </div>
          ))}
        </div>
        <h3 className="mt-5 mb-2 text-sm font-semibold">{t("c.detectionSources")}</h3>
        <div className="grid gap-2">
          {L.detection_sources.map((s, i) => (
            <div key={i}>
              <p className="mb-1 text-xs font-semibold text-muted">{t("c.allele")} {s.allele}</p>
              <Cite s={s} />
            </div>
          ))}
        </div>
      </section>

      {L.limitations.length > 0 && (
        <section>
          <SectionTitle>{t("c.limitations")}</SectionTitle>
          <ul className="grid list-disc gap-2 ps-5 text-sm text-ink-2">
            {L.limitations.map((l, i) => <li key={i}>{l}</li>)}
          </ul>
        </section>
      )}

      {report.people && (
        <section>
          <SectionTitle>{t("c.peopleTable")}</SectionTitle>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface" tabIndex={0} role="region" aria-label={t("c.peopleTable")}>
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b border-line"><tr>
                <th className={th}>{t("edit.person")}</th><th className={th}>{t("c.pCarrier")}</th><th className={th}>{t("c.pAffected")}</th>
                <th className={th}>{t("c.pAny")}</th><th className={th}>{t("c.genotypes")}</th>
              </tr></thead>
              <tbody>
                {Object.entries(report.people).map(([pid, p]) => (
                  <tr key={pid} className="border-b border-line last:border-0">
                    <td className={td}>{names[pid] || pid}<span className="block text-xs text-muted">{p.recorded.status}{p.recorded.test ? ` · test [${p.recorded.test.detected.join(",")}]` : ""}</span></td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(p.computed.p_carrier)}</td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(p.computed.p_affected)}</td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(p.computed.p_any_variant)} <span className="text-muted">({p.computed.chance_text})</span></td>
                    <td className={cx(td, "font-mono text-xs")}>
                      {Object.entries(p.computed.genotypes).map(([g, v]) => <span key={g} className="me-3 inline-block">{g}: {fmtNum(v, 3)}</span>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {report.couples && report.couples.length > 0 && (
        <section>
          <SectionTitle>{t("c.couples")}</SectionTitle>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface" tabIndex={0} role="region" aria-label={t("c.couples")}>
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b border-line"><tr>
                <th className={th}>{t("c.couples")}</th><th className={th}>{t("c.kinship")}</th><th className={th}>{t("c.pBoth")}</th>
                <th className={th}>{t("c.pChild")}</th><th className={th}>{t("c.baseline")}</th>
              </tr></thead>
              <tbody>
                {report.couples.map((c) => (
                  <tr key={`${c.female}-${c.male}`} className="border-b border-line last:border-0">
                    <td className={td}>{names[c.female] || c.female} + {names[c.male] || c.male}</td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(c.kinship)}</td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(c.computed.p_both_carry)}</td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(c.computed.p_child_affected)}</td>
                    <td className={cx(td, "tabular-nums")}>{fmtNum(c.computed.baseline_child_affected)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
