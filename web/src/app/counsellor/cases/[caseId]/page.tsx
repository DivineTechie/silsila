"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AboutInfo } from "@/components/About";
import { InvitationCard, PersonDetail, RequireRole, SectionTitle, TreeEditor } from "@/components/case";
import { AuditLog, Working } from "@/components/counsellor";
import { Parts } from "@/components/Parts";
import { PedigreeChart } from "@/components/PedigreeChart";
import { Page } from "@/components/Shell";
import { TabPanel, Tabs } from "@/components/Tabs";
import { Button, ErrorBox, Eyebrow, H1, H3, Loading, Notice, Prov } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, usePrefs } from "@/lib/prefs";
import type { CaseDetail } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

type TabKey = "tree" | "report" | "working" | "invitations" | "audit" | "fhir";
const TABS: TabKey[] = ["tree", "report", "working", "invitations", "audit", "fhir"];
const TERMINAL = new Set(["withdrawn", "declined_by_relative", "no_response", "closed"]);

function Fhir({ caseId }: { caseId: string }) {
  const { t } = usePrefs();
  const [json, setJson] = useState<string | null>(null);
  const [count, setCount] = useState(0);
  const [href, setHref] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [copied, setCopied] = useState(false);
  useEffect(() => () => {
    if (href) URL.revokeObjectURL(href);
  }, [href]);
  async function load() {
    setError(null);
    try {
      const b = await api<{ entry?: unknown[] }>(`/api/fhir/cases/${caseId}`);
      const text = JSON.stringify(b, null, 2);
      setJson(text);
      setCount(b.entry?.length || 0);
      setHref(URL.createObjectURL(new Blob([text], { type: "application/fhir+json" })));
    } catch (e) {
      setError(e);
    }
  }
  return (
    <div>
      <p className="text-sm text-ink-2">{t("c.fhirHint")}</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={load}>{t("c.fhirLoad")}</Button>
        {href && (
          <a href={href} download={`silsila-${caseId}-fhir.json`} className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-4 font-medium hover:bg-surface-2">
            {t("common.download")}
          </a>
        )}
        {json && (
          <Button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(json);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              } catch {
                /* clipboard unavailable */
              }
            }}
          >
            {copied ? t("common.copied") : t("common.copy")}
          </Button>
        )}
        {json && <span className="text-sm text-muted">{t("c.entries", { n: count })}</span>}
      </div>
      {error ? <div className="mt-3"><ErrorBox error={error} /></div> : null}
      {json && (
        <pre dir="ltr" className="mt-4 max-h-[28rem] overflow-auto rounded-xl border border-line bg-surface-2 p-4 font-mono text-xs">
          {json}
        </pre>
      )}
    </div>
  );
}

function CounsellorCase() {
  const { caseId } = useParams<{ caseId: string }>();
  const { t, lang, session } = usePrefs();
  const { data, error, loading, reload } = useLoad(
    () => api<CaseDetail>(`/api/cases/${caseId}`, { query: { lang } }),
    `${caseId}:${lang}:${session?.token}`,
  );
  const [tab, setTab] = useState<TabKey>(() => {
    const q = new URLSearchParams(window.location.search).get("tab") as TabKey | null;
    return q && TABS.includes(q) ? q : "tree";
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [auditKey, setAuditKey] = useState(0);

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const { case: c, report } = data;
  const names = Object.fromEntries(c.pedigree.people.map((p) => [p.id, p.name || p.id]));
  const person = selected ? c.pedigree.people.find((p) => p.id === selected) : null;
  const awaiting = data.invitations.filter((i) => i.status === "awaiting_counsellor").length;
  const open = data.invitations.filter((i) => !TERMINAL.has(i.status)).length;
  const refresh = () => {
    void reload();
    setAuditKey((k) => k + 1);
  };

  return (
    <>
      <Link href="/counsellor" className="text-sm text-muted underline underline-offset-4">{t("c.title")}</Link>
      <Eyebrow>{c.locus_id} · {c.id}</Eyebrow>
      <H1 className="mt-2">{c.title || c.id}</H1>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-2">
        <Prov kind="recorded" />
        {c.index_source.replace(/_/g, " ")} · {t("family.index")}: {names[c.index_person_id]} · {t("c.consents")}:{" "}
        {(["compute", "invite"] as const)
          .map((s) => `${s} ${c.consents?.[s]?.granted ? "✓" : "—"}`)
          .join(", ")}
      </p>
      {report.status !== "ok" && report.message && (
        <Notice className="mt-5"><Parts parts={report.message} compact /></Notice>
      )}

      <div className="mt-6">
        <Tabs<TabKey>
          idBase="cc"
          label={c.title || c.id}
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "tree", label: t("family.tree") },
            { key: "report", label: t("c.report") },
            { key: "working", label: t("c.working") },
            { key: "invitations", label: t("c.invitations"), badge: awaiting ? `${awaiting} / ${open}` : open },
            { key: "audit", label: t("c.audit") },
            { key: "fhir", label: t("c.fhir") },
          ]}
        />
        <TabPanel idBase="cc" active={tab}>
          {tab === "tree" && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
              <div className="min-w-0">
                <PedigreeChart
                  pedigree={c.pedigree}
                  report={report.status === "ok" ? report : null}
                  indexId={c.index_person_id}
                  selectedId={selected}
                  onSelect={(id) => setSelected(id === selected ? null : id)}
                />
                <div className="mt-6"><TreeEditor caseId={c.id} pedigree={c.pedigree} onSaved={refresh} /></div>
              </div>
              <div>{person ? <PersonDetail person={person} detail={data} /> : <p className="text-sm text-muted lg:mt-8">{t("tree.hint")}</p>}</div>
            </div>
          )}

          {tab === "report" && (
            <div className="grid gap-8 [&>*]:min-w-0">
              {report.status === "ok" ? (
                <>
                  <section>
                    <SectionTitle>{t("family.relatives")}</SectionTitle>
                    <ul className="grid gap-3 md:grid-cols-2">
                      {c.pedigree.people
                        .filter((p) => report.people?.[p.id]?.sentence || report.people?.[p.id]?.residual_note)
                        .map((p) => (
                          <li key={p.id} className="rounded-xl border border-line bg-surface p-4">
                            <div className="flex flex-wrap items-baseline justify-between gap-2">
                              <H3>{p.name}</H3>
                              <span className="flex items-center gap-2 text-sm"><Prov kind="calculated" /><span dir="ltr">{report.people![p.id].computed.chance_text}</span></span>
                            </div>
                            <Parts parts={report.people![p.id].sentence} className="mt-3" compact showIds />
                            <Parts parts={report.people![p.id].residual_note} className="mt-3" compact showIds />
                          </li>
                        ))}
                    </ul>
                  </section>
                  <section>
                    <SectionTitle>{t("family.couples")}</SectionTitle>
                    <ul className="grid gap-3 md:grid-cols-2">
                      {(report.couples || []).map((cp) => (
                        <li key={`${cp.female}-${cp.male}`} className="rounded-xl border border-line bg-surface p-4">
                          {cp.kinship > 0 && <p className="mb-2 text-xs text-muted"><Prov kind="calculated" /> {t("c.kinship")} = <span dir="ltr">{cp.kinship}</span></p>}
                          <Parts parts={cp.sentence} compact showIds />
                        </li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <SectionTitle>{t("inform.pick")}</SectionTitle>
                    <ol className="grid gap-2 text-sm">
                      {(report.invites || []).map((s) => (
                        <li key={s.person_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2">
                          <span className="tabular-nums font-semibold">{s.rank}.</span>
                          <span>{names[s.person_id]}</span>
                          <span className="text-muted">· {t(`reason.${s.reason_code}`)}</span>
                        </li>
                      ))}
                    </ol>
                  </section>
                </>
              ) : (
                <Working report={report} names={names} />
              )}
              <p className="text-xs text-muted" dir="ltr">{report.engine} · {fmtDate(report.computed_at)}</p>
            </div>
          )}

          {tab === "working" && <Working report={report} names={names} />}

          {tab === "invitations" && (
            <div className="grid gap-3 lg:grid-cols-2">
              {data.invitations.length === 0 && <p className="text-muted">{t("inform.noInvites")}</p>}
              {[...data.invitations].reverse().map((inv) => (
                <InvitationCard key={inv.id} inv={inv} role="counsellor" report={report} onChanged={refresh} />
              ))}
            </div>
          )}

          {tab === "audit" && <AuditLog caseId={c.id} refreshKey={auditKey} />}
          {tab === "fhir" && <Fhir caseId={c.id} />}
        </TabPanel>
      </div>
      <div className="mt-10"><AboutInfo /></div>
    </>
  );
}

export default function CounsellorCasePage() {
  return (
    <Page wide>
      <RequireRole role="counsellor">
        <CounsellorCase />
      </RequireRole>
    </Page>
  );
}
