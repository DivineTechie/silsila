"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { AboutInfo } from "@/components/About";
import { AskBox, ConsentCard, InvitationCard, PersonDetail, RequireRole, SectionTitle, TreeEditor } from "@/components/case";
import { InformFlow } from "@/components/InformFlow";
import { Parts } from "@/components/Parts";
import { PedigreeChart } from "@/components/PedigreeChart";
import { Page } from "@/components/Shell";
import { TabPanel, Tabs } from "@/components/Tabs";
import { ErrorBox, Eyebrow, H1, H3, Loading, Notice, Prov } from "@/components/ui";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { CaseDetail } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

type TabKey = "tree" | "relatives" | "inform" | "invitations" | "permissions" | "ask";
const TERMINAL = new Set(["withdrawn", "declined_by_relative", "no_response", "closed"]);

function FamilyCase() {
  const { caseId } = useParams<{ caseId: string }>();
  const { t, lang, session } = usePrefs();
  const { data, error, loading, reload } = useLoad(
    () => api<CaseDetail>(`/api/cases/${caseId}`, { query: { lang } }),
    `${caseId}:${lang}:${session?.token}`,
  );
  const [tab, setTab] = useState<TabKey>("tree");
  const [selected, setSelected] = useState<string | null>(null);

  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;

  const { case: c, report } = data;
  const person = selected ? c.pedigree.people.find((p) => p.id === selected) : null;
  const openInv = data.invitations.filter((i) => !TERMINAL.has(i.status)).length;
  const people = report.people || {};
  const relatives = c.pedigree.people.filter((p) => people[p.id]?.sentence || people[p.id]?.residual_note);

  return (
    <>
      <Link href="/family" className="text-sm text-muted underline underline-offset-4">
        {t("family.title")}
      </Link>
      <Eyebrow>{c.locus_id}</Eyebrow>
      <H1 className="mt-2">{c.title || c.id}</H1>
      {report.locus && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-2">
          <Prov kind="recorded" />
          {t("family.condition")}: {report.locus.display} · {t("family.gene")}: <span dir="ltr">{report.locus.gene}</span>
        </p>
      )}

      {report.status !== "ok" && report.message && (
        <Notice className="mt-5">
          <Parts parts={report.message} compact />
        </Notice>
      )}

      <div className="mt-6">
        <Tabs<TabKey>
          idBase="fam"
          label={c.title || c.id}
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "tree", label: t("family.tree") },
            { key: "relatives", label: t("family.relatives") },
            { key: "inform", label: t("family.inform") },
            { key: "invitations", label: t("family.invitations"), badge: openInv },
            { key: "permissions", label: t("family.permissions") },
            { key: "ask", label: t("family.ask") },
          ]}
        />
        <TabPanel idBase="fam" active={tab} heading={({ tree: t("family.tree"), relatives: t("family.relatives"), inform: t("family.inform"), invitations: t("family.invitations"), permissions: t("family.permissions"), ask: t("family.ask") } as Record<string, string>)[tab]}>
          {tab === "tree" && (
            <section aria-label={t("family.tree")}>
              <PedigreeChart
                pedigree={c.pedigree}
                report={report.status === "ok" ? report : null}
                indexId={c.index_person_id}
                selectedId={selected}
                onSelect={(id) => setSelected(id === selected ? null : id)}
              />
              {person && <PersonDetail person={person} detail={data} />}
              <div className="mt-6">
                <TreeEditor caseId={c.id} pedigree={c.pedigree} onSaved={reload} />
              </div>
            </section>
          )}

          {tab === "relatives" && (
            <section aria-label={t("family.relatives")}>
              {report.status !== "ok" ? (
                <p className="text-muted">{report.status === "awaiting_consent" ? t("family.pausedCompute") : t("family.notShown")}</p>
              ) : (
                <>
                  <ul className="grid gap-3">
                    {relatives.map((p) => (
                      <li key={p.id} className="rounded-xl border border-line bg-surface p-4">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <H3>{p.name || p.id}</H3>
                          <span className="flex items-center gap-2 text-sm">
                            <Prov kind="calculated" />
                            <span dir="ltr" className="font-medium">{people[p.id].computed.chance_text}</span>
                          </span>
                        </div>
                        <Parts parts={people[p.id].sentence} className="mt-3" compact />
                        <Parts parts={people[p.id].residual_note} className="mt-3" compact />
                      </li>
                    ))}
                  </ul>
                  {(report.couples || []).length > 0 && (
                    <div className="mt-8">
                      <SectionTitle>{t("family.couples")}</SectionTitle>
                      <ul className="grid gap-3">
                        {(report.couples || []).map((cp) => (
                          <li key={`${cp.female}-${cp.male}`} className="rounded-xl border border-line bg-surface p-4">
                            <Parts parts={cp.sentence} compact />
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </section>
          )}

          {tab === "inform" && (
            <section aria-label={t("family.inform")}>
              <InformFlow detail={data} onCreated={reload} goToPermissions={() => setTab("permissions")} />
            </section>
          )}

          {tab === "invitations" && (
            <section aria-label={t("family.invitations")} className="grid gap-3">
              {data.invitations.length === 0 && <p className="text-muted">{t("inform.noInvites")}</p>}
              {[...data.invitations].reverse().map((inv) => (
                <InvitationCard key={inv.id} inv={inv} role="family" report={report} onChanged={reload} />
              ))}
            </section>
          )}

          {tab === "permissions" && (
            <section aria-label={t("family.permissions")} className="grid gap-4">
              {(["compute", "invite"] as const).map((s) => (
                <ConsentCard
                  key={s}
                  scope={s}
                  caseId={c.id}
                  consent={c.consents?.[s]}
                  text={data.consent_text[s]}
                  canChange={session?.user.id === c.family_user_id}
                  onChanged={reload}
                />
              ))}
            </section>
          )}

          {tab === "ask" && (
            <section aria-label={t("family.ask")}>
              <AskBox caseId={c.id} />
            </section>
          )}
        </TabPanel>
      </div>

      <div className="mt-10">
        <AboutInfo />
      </div>
    </>
  );
}

export default function FamilyCasePage() {
  return (
    <Page>
      <RequireRole role="family">
        <FamilyCase />
      </RequireRole>
    </Page>
  );
}
