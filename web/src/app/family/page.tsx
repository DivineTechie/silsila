"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { RequireRole } from "@/components/case";
import { Page } from "@/components/Shell";
import { ErrorBox, Eyebrow, H1, Loading, Prov } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, usePrefs } from "@/lib/prefs";
import type { CaseSummary } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

function CaseList() {
  const { t, session } = usePrefs();
  const router = useRouter();
  const { data, error, loading, reload } = useLoad(() => api<CaseSummary[]>("/api/cases"), session?.token || "");

  useEffect(() => {
    if (data && data.length === 1) router.replace(`/family/${data[0].id}`);
  }, [data, router]);

  return (
    <>
      <Eyebrow>{session?.user.display_name}</Eyebrow>
      <H1 className="mt-2">{t("family.title")}</H1>
      <div className="mt-6">
        {loading && !data && <Loading />}
        {error ? <ErrorBox error={error} onRetry={reload} /> : null}
        {data && data.length === 0 && <p className="text-muted">{t("family.noCases")}</p>}
        <ul className="grid gap-3">
          {data?.map((c) => (
            <li key={c.id}>
              <Link
                href={`/family/${c.id}`}
                className="block rounded-2xl border border-line bg-surface p-4 hover:border-accent sm:p-5"
              >
                <span className="block text-lg font-semibold">{c.title || c.id}</span>
                <span className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-2">
                  <Prov kind="recorded" />
                  {c.locus_id} · {t("c.people", { n: c.people })} · {t("c.openInv", { n: c.open_invitations })}
                </span>
                <span className="mt-1 block text-xs text-muted" dir="ltr">{fmtDate(c.updated)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}

export default function FamilyHome() {
  return (
    <Page>
      <RequireRole role="family">
        <CaseList />
      </RequireRole>
    </Page>
  );
}
