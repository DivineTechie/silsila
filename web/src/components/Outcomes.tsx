"use client";

// Programme measures from the challenge statement, computed live by the API from recorded activity.

import { Button, Card, ErrorBox, H2, Loading, Num, Prov } from "./ui";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { StringKey } from "@/lib/strings";
import { useLoad } from "@/lib/useLoad";

interface Outcomes {
  invitations: number;
  funnel: Record<string, number>;
  ended: { declined_by_relative: number; no_response: number; withdrawn: number };
  comprehension: { submitted: number; passed: number };
  uptake: { opened: number; booked_or_tested: number };
  hours: Record<string, number | null>;
  by_language: Record<string, { opened: number; teachback: number; understood: number; booked_or_tested: number }>;
  privacy: { denied_requests: number; blocked_outputs: number; audit_chain: { intact: boolean } };
  messages: { total: number; escalated: number; crisis: number };
}

const STAGES = ["awaiting_counsellor", "sent", "opened", "understood", "booked", "tested", "closed"] as const;

function dur(h: number | null | undefined): string {
  if (h === null || h === undefined) return "–";
  if (h < 1 / 60) return "<1 min";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(1)} h`;
  return `${(h / 24).toFixed(1)} d`;
}

function Kpi({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{title}</p>
      <p className="mt-1 flex items-center gap-2 text-3xl font-semibold tabular-nums"><Num>{value}</Num></p>
      <p className="mt-1 text-xs text-ink-2"><Prov kind="calculated" /> {detail}</p>
    </div>
  );
}

export function OutcomesPanel() {
  const { t, session } = usePrefs();
  const { data, error, loading, reload } = useLoad(() => api<Outcomes>("/api/outcomes"), session?.token || "");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "–");
  const max = Math.max(1, ...STAGES.map((s) => data.funnel[s] ?? 0));
  const langs = Object.entries(data.by_language);
  return (
    <div className="grid gap-6 [&>*]:min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-3xl text-sm text-ink-2">{t("oc.lead")}</p>
        <Button size="sm" onClick={reload}>{t("oc.refresh")}</Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi title={t("oc.comprehension")} value={pct(data.comprehension.passed, data.comprehension.submitted)}
          detail={t("oc.comprehensionD", { passed: data.comprehension.passed, n: data.comprehension.submitted })} />
        <Kpi title={t("oc.uptake")} value={pct(data.uptake.booked_or_tested, data.uptake.opened)}
          detail={t("oc.uptakeD", { n: data.uptake.booked_or_tested, opened: data.uptake.opened })} />
        <Kpi title={t("oc.turnaround")} value={dur(data.hours.request_to_sent)} detail={t("oc.turnaroundD")} />
        <Kpi title={t("oc.privacy")} value={String(data.privacy.denied_requests)}
          detail={t("oc.privacyD", { denied: data.privacy.denied_requests, blocked: data.privacy.blocked_outputs,
            chain: data.privacy.audit_chain.intact ? t("oc.intact") : t("oc.broken") })} />
      </div>

      <Card>
        <H2>{t("oc.funnel")}</H2>
        <ol className="mt-4 grid gap-2">
          {STAGES.map((s) => {
            const n = data.funnel[s] ?? 0;
            return (
              <li key={s} className="grid grid-cols-[minmax(9rem,14rem)_1fr_3rem] items-center gap-3 text-sm">
                <span>{t(`oc.stage.${s}` as StringKey)}</span>
                <span className="h-3 rounded-full bg-surface-2" aria-hidden="true">
                  <span className="block h-3 rounded-full bg-accent" style={{ width: `${(100 * n) / max}%` }} />
                </span>
                <span className="text-end tabular-nums"><Num>{n}</Num></span>
              </li>
            );
          })}
        </ol>
        <p className="mt-3 text-xs text-muted">
          {t("oc.ended", { declined: data.ended.declined_by_relative, noresp: data.ended.no_response, withdrawn: data.ended.withdrawn })}
        </p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2 [&>*]:min-w-0">
        <Card>
          <H2>{t("oc.equity")}</H2>
          {langs.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("oc.none")}</p>
          ) : (
            <div className="mt-3 overflow-x-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label={t("oc.equity")}>
              <table className="w-full text-sm">
                <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-3 py-2 text-start">{t("oc.lang")}</th>
                    <th className="px-3 py-2 text-start">{t("oc.opened")}</th>
                    <th className="px-3 py-2 text-start">{t("oc.understood")}</th>
                    <th className="px-3 py-2 text-start">{t("oc.booked")}</th>
                  </tr>
                </thead>
                <tbody>
                  {langs.map(([lang, r]) => (
                    <tr key={lang} className="border-t border-line">
                      <td className="px-3 py-2">{lang === "ar" ? "العربية" : "English"}</td>
                      <td className="px-3 py-2 tabular-nums"><Num>{r.opened}</Num></td>
                      <td className="px-3 py-2 tabular-nums"><Num>{r.understood}/{r.teachback} ({pct(r.understood, r.teachback)})</Num></td>
                      <td className="px-3 py-2 tabular-nums"><Num>{r.booked_or_tested} ({pct(r.booked_or_tested, r.opened)})</Num></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-xs text-muted">
            {t("oc.messages", { n: data.messages.total, esc: data.messages.escalated, crisis: data.messages.crisis })}
          </p>
        </Card>
        <Card>
          <H2>{t("oc.timing")}</H2>
          <dl className="mt-3 grid gap-2 text-sm">
            {(["case_to_first_invitation", "request_to_sent", "sent_to_opened", "opened_to_booked"] as const).map((k) => (
              <div key={k} className="flex justify-between gap-3 border-b border-line py-1">
                <dt className="text-ink-2">{t(`oc.t.${k}` as StringKey)}</dt>
                <dd className="tabular-nums"><Num>{dur(data.hours[k])}</Num></dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
      <p className="text-sm font-medium text-ink-2">{t("oc.notMeasured")}</p>
    </div>
  );
}
