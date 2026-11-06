"use client";

import { AboutInfo } from "@/components/About";
import { SectionTitle } from "@/components/case";
import { EvidenceFile } from "@/components/evidence";
import { CascadeChart, PrivacyEvidence, TriageEvidence, isCascadeChart, isPrivacy, isTriage } from "@/components/evidenceSpecific";
import { Page } from "@/components/Shell";
import { ErrorBox, Eyebrow, H1, H3, Loading, Notice, Prov } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtNum, usePrefs } from "@/lib/prefs";
import type { LociRegister, SourceCitation } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

function SourceLine({ s }: { s?: SourceCitation | null }) {
  if (!s) return <span className="text-muted">—</span>;
  return (
    <span className="block">
      {s.citation}
      {(s.pmid || s.url) && (
        <span className="mt-0.5 block text-xs">
          {s.pmid ? (
            <a className="text-accent underline" href={`https://pubmed.ncbi.nlm.nih.gov/${s.pmid}/`} target="_blank" rel="noreferrer">
              PMID {s.pmid}
            </a>
          ) : (
            <a className="break-all text-accent underline" href={s.url} target="_blank" rel="noreferrer">
              {s.url}
            </a>
          )}
          {s.population && <span className="text-muted"> · {s.population}</span>}
          {s.sample_size !== undefined && <span className="text-muted"> · n = {s.sample_size.toLocaleString("en-US")}</span>}
        </span>
      )}
    </span>
  );
}

const th = "px-3 py-2 text-start text-xs font-semibold uppercase tracking-wide text-muted";

function Register() {
  const { t } = usePrefs();
  const { data, error, loading, reload } = useLoad(() => api<LociRegister>("/api/content/loci", { auth: false }), "loci");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const bg = data.background_inbreeding;
  return (
    <div className="grid gap-6 [&>*]:min-w-0" dir="ltr" lang="en">
      <div className="rounded-xl border border-line bg-surface p-4 text-sm">
        <H3>{t("ev.background")}: F = {bg.value}</H3>
        <p className="mt-1 text-ink-2">{bg.meaning}</p>
        <div className="mt-2"><SourceLine s={bg.source} /></div>
      </div>
      {data.loci.map((l) => (
        <div key={l.id}>
          <H3>
            {l.display} <span className="font-mono text-sm text-muted">({l.gene})</span>
          </H3>
          <div className="mt-2 overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b border-line">
                <tr>
                  <th className={th}>{t("c.allele")}</th>
                  <th className={th}>{t("c.published")}</th>
                  <th className={th}>{t("c.frequency")}</th>
                  <th className={th}>{t("c.detection")}</th>
                  <th className={th}>{t("c.sources")}</th>
                </tr>
              </thead>
              <tbody>
                {l.sources.map((s) => {
                  const a = l.alleles.find((x) => x.id === s.id);
                  return (
                    <tr key={s.id} className="border-b border-line align-top last:border-0">
                      <td className="px-3 py-2"><span className="font-mono font-semibold">{s.id}</span><span className="block text-xs text-muted">{s.label}</span></td>
                      <td className="px-3 py-2 tabular-nums">
                        <Prov kind="recorded" />{" "}
                        {s.published_value !== undefined ? fmtNum(s.published_value, 6) : "—"}
                        <span className="block text-xs text-muted">{s.published_measure?.replace(/_/g, " ")}</span>
                      </td>
                      <td className="px-3 py-2 tabular-nums"><Prov kind="calculated" /> {a ? fmtNum(a.frequency, 6) : "—"}</td>
                      <td className="px-3 py-2 tabular-nums">
                        {a ? a.detection_rate : "—"}
                        <span className="mt-1 block max-w-56 text-xs text-muted">
                          {s.detection_source ? <SourceLine s={s.detection_source} /> : s.detection_note}
                        </span>
                      </td>
                      <td className="max-w-md px-3 py-2"><SourceLine s={s.source} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {l.derivations.length > 0 && (
            <ul className="mt-2 grid gap-1 text-xs text-ink-2">
              {l.derivations.map((d, i) => (
                <li key={i} className="font-mono">
                  {d.allele}: {d.formula} → q = {fmtNum(d.allele_frequency, 6)}
                </li>
              ))}
            </ul>
          )}
          {l.limitations.length > 0 && (
            <ul className="mt-2 list-disc ps-5 text-xs text-muted">
              {l.limitations.map((x, i) => <li key={i}>{x}</li>)}
            </ul>
          )}
        </div>
      ))}
      {data.excluded.length > 0 && (
        <div>
          <H3>{t("ev.excluded")}</H3>
          <ul className="mt-2 grid gap-2">
            {data.excluded.map((e) => (
              <li key={e.id} className="rounded-xl border border-line bg-surface p-3 text-sm">
                <span className="font-semibold">{e.display}</span> <span className="font-mono text-xs text-muted">({e.id})</span>
                <p className="mt-1 text-ink-2">{e.reason}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Evidence() {
  const { t } = usePrefs();
  const { data, error, loading, reload } = useLoad(() => api<Record<string, unknown>>("/api/evidence", { auth: false }), "ev");
  const files = data ? Object.entries(data) : [];
  const rank = (d: unknown) => (isCascadeChart(d) ? 0 : isTriage(d) ? 1 : isPrivacy(d) ? 2 : 3);
  files.sort((a, b) => rank(a[1]) - rank(b[1]) || a[0].localeCompare(b[0]));
  return (
    <>
      <Eyebrow>{t("app.name")}</Eyebrow>
      <H1 className="mt-2">{t("ev.title")}</H1>
      <p className="mt-3 max-w-3xl text-ink-2">{t("ev.lead")}</p>
      <div className="mt-8 grid gap-6 [&>*]:min-w-0">
        {loading && !data && <Loading />}
        {error && !data ? <ErrorBox error={error} onRetry={reload} /> : null}
        {data && files.length === 0 && <Notice>{t("ev.empty")}</Notice>}
        {files.map(([k, v]) => {
          const d = v as Record<string, unknown>;
          if (isCascadeChart(v)) return <CascadeChart key={k} file={k} doc={d} />;
          if (isTriage(v)) return <TriageEvidence key={k} file={k} doc={d} />;
          if (isPrivacy(v)) return <PrivacyEvidence key={k} file={k} doc={d} />;
          return <EvidenceFile key={k} name={k} doc={v} />;
        })}
      </div>
      <section className="mt-14" aria-labelledby="reg-h">
        <SectionTitle id="reg-h">{t("ev.register")}</SectionTitle>
        <p className="-mt-2 mb-5 text-sm text-ink-2">{t("ev.registerLead")}</p>
        <Register />
      </section>
      <div className="mt-10"><AboutInfo /></div>
    </>
  );
}

export default function EvidencePage() {
  return (
    <Page wide>
      <Evidence />
    </Page>
  );
}
