"use client";

import Link from "next/link";
import { useState } from "react";
import { RequireRole } from "@/components/case";
import { AuditLog, DemoTools, Inbox, Queue } from "@/components/counsellor";
import { VoiceIntake } from "@/components/intake";
import { Page } from "@/components/Shell";
import { TabPanel, Tabs } from "@/components/Tabs";
import { ErrorBox, Eyebrow, H1, Loading, Prov } from "@/components/ui";
import { api } from "@/lib/api";
import { age, usePrefs } from "@/lib/prefs";
import type { CaseSummary } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

type TabKey = "queue" | "cases" | "intake" | "messages" | "audit";

function Cases() {
  const { t, session, lang } = usePrefs();
  const { data, error, loading, reload } = useLoad(() => api<CaseSummary[]>("/api/cases", { query: { lang } }), `${session?.token || ""}:${lang}`);
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  return (
    <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {data?.map((c) => (
        <li key={c.id}>
          <Link href={`/counsellor/cases/${c.id}`} className="block h-full rounded-2xl border border-line bg-surface p-5 hover:border-accent">
            <span className="text-xs font-semibold tracking-wide text-brass" dir="ltr">{c.locus_id}</span>
            <span className="mt-1 block font-semibold">{c.title || c.id}</span>
            <span className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-2">
              <Prov kind="recorded" />
              {t("c.people", { n: c.people })} · {t("c.openInv", { n: c.open_invitations })}
            </span>
            <span className="mt-1 block text-xs text-muted">{t("c.updated", { when: age(c.updated, t) })}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Console() {
  const { t, session } = usePrefs();
  const [tab, setTab] = useState<TabKey>("queue");
  const [auditKey, setAuditKey] = useState(0);
  return (
    <>
      <Eyebrow>{session?.user.display_name}</Eyebrow>
      <H1 className="mt-2">{t("c.title")}</H1>
      <div className="mt-6">
        <Tabs<TabKey>
          idBase="con"
          label={t("c.title")}
          active={tab}
          onChange={setTab}
          tabs={[
            { key: "queue", label: t("c.queue") },
            { key: "cases", label: t("c.cases") },
            { key: "intake", label: t("vi.tab") },
            { key: "messages", label: t("c.messages") },
            { key: "audit", label: t("c.audit") },
          ]}
        />
        <TabPanel idBase="con" active={tab} heading={({ queue: t("c.queue"), cases: t("c.cases"), intake: t("vi.tab"), messages: t("c.messages"), audit: t("c.audit") } as Record<string, string>)[tab]}>
          {tab === "queue" && <Queue onOpenMessages={() => setTab("messages")} />}
          {tab === "cases" && <Cases />}
          {tab === "intake" && <VoiceIntake />}
          {tab === "messages" && <Inbox />}
          {tab === "audit" && (
            <div className="grid gap-8 [&>*]:min-w-0">
              <AuditLog refreshKey={auditKey} />
              <DemoTools onChanged={() => setAuditKey((k) => k + 1)} />
            </div>
          )}
        </TabPanel>
      </div>
    </>
  );
}

export default function CounsellorHome() {
  return (
    <Page wide>
      <RequireRole role="counsellor">
        <Console />
      </RequireRole>
    </Page>
  );
}
