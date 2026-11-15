"use client";

// Counsellor intake: import an index result from a FHIR R4B genomics record (the reverse of the FHIR export).
// The record is checked first (nothing stored); the counsellor sees what was read, what will not be stored and
// any warnings, then confirms. A record that cannot be read safely is refused with the reason.

import Link from "next/link";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { StringKey } from "@/lib/strings";
import { useLoad } from "@/lib/useLoad";
import { Button, Card, Chip, H2, Notice, Prov, cx, inputCls } from "./ui";

interface Draft {
  locus_id: string;
  gene: string;
  condition: string;
  condition_ar: string;
  index: { sex: "male" | "female"; status: string; affected_with: string | null; test: { detected: string[] } | null };
  index_source: string;
  warnings: string[];
  notes: string[];
  not_stored: string[];
  source: { sha256: string; resources: Record<string, number> };
}
interface Result { created: boolean; case_id?: string; draft: Draft }

const SOURCES = ["", "newborn_screen", "premarital_at_risk", "diagnosed_child", "carrier_result"] as const;

export function FhirImport({ onCreated }: { onCreated?: () => void }) {
  const { t, lang, session } = usePrefs();
  const families = useLoad(() => api<{ id: string; display_name: string }[]>("/api/fhir/families"), session?.token || "");
  const [text, setText] = useState("");
  const [source, setSource] = useState<(typeof SOURCES)[number]>("");
  const [family, setFamily] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [badJson, setBadJson] = useState(false);
  const [busy, setBusy] = useState(false);

  const fam = family || families.data?.[0]?.id || ""; // the first family account until one is chosen

  const reset = () => {
    setResult(null);
    setError(null);
    setBadJson(false);
  };

  async function loadSample() {
    reset();
    try {
      setText(JSON.stringify(await api<unknown>("/api/fhir/sample"), null, 2));
      setSource("newborn_screen");
    } catch (e) {
      setError(e);
    }
  }

  async function send(dryRun: boolean) {
    setError(null);
    setBadJson(false);
    let bundle: unknown;
    try {
      bundle = JSON.parse(text);
    } catch {
      setBadJson(true);
      setResult(null);
      return;
    }
    setBusy(true);
    try {
      const r = await api<Result>("/api/fhir/import", {
        body: { bundle, index_source: source || null, family_user_id: fam || null, dry_run: dryRun },
      });
      setResult(r);
      if (r.created) onCreated?.();
    } catch (e) {
      setError(e);
      if (dryRun) setResult(null);
    } finally {
      setBusy(false);
    }
  }

  const d = result?.draft;

  return (
    <Card>
      <H2>{t("fi.title")}</H2>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{t("fi.lead")}</p>
      <div className="mt-4 grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => void loadSample()}>{t("fi.sample")}</Button>
          <Chip>{t("fi.sampleNote")}</Chip>
        </div>
        <label className="grid gap-1 text-sm" htmlFor="fi-json">
          {t("fi.record")}
          <textarea
            id="fi-json"
            dir="ltr"
            lang="en"
            rows={8}
            spellCheck={false}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              reset();
            }}
            className={cx(inputCls, "min-h-40 py-2 font-mono text-xs")}
          />
        </label>
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid gap-1 text-sm" htmlFor="fi-source">
            {t("fi.kind")}
            <select id="fi-source" className={inputCls} value={source} onChange={(e) => { setSource(e.target.value as (typeof SOURCES)[number]); reset(); }}>
              {SOURCES.map((s) => <option key={s} value={s}>{t(`fi.kind.${s || "auto"}` as StringKey)}</option>)}
            </select>
          </label>
          <Button variant="primary" disabled={busy || !text.trim()} onClick={() => void send(true)}>{t("fi.check")}</Button>
        </div>
        {badJson && <Notice role="alert"><strong className="font-semibold">{t("fi.refused")}</strong> {t("fi.badJson")}</Notice>}
        {error ? (
          <div role="alert" className="rounded-xl border-2 border-dashed border-ink-2 bg-surface-2 px-4 py-3 text-sm">
            <p className="font-semibold">{t("fi.refused")}</p>
            <p className="mt-1 text-ink-2" dir={error instanceof ApiError && error.status !== 0 ? "ltr" : undefined}>
              {error instanceof ApiError ? (error.status === 0 ? t("common.network") : error.message) : String(error)}
            </p>
          </div>
        ) : null}
        {d && (
          <div className="rounded-xl border border-accent bg-accent-soft/40 p-4" aria-live="polite">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">{result?.created ? t("fi.created") : t("fi.read")}</p>
            <dl className="mt-2 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <div><dt className="text-ink-2">{t("fi.condition")}</dt><dd className="font-medium">{lang === "ar" ? d.condition_ar : d.condition} <span className="font-mono text-xs text-muted" dir="ltr">({d.gene})</span></dd></div>
              <div><dt className="text-ink-2">{t("fi.kind")}</dt><dd className="font-medium">{t(`fi.kind.${d.index_source}` as StringKey)}</dd></div>
              <div>
                <dt className="text-ink-2">{t("fi.index")}</dt>
                <dd className="flex flex-wrap items-center gap-2 font-medium">
                  <Prov kind="recorded" />
                  {t(d.index.sex === "male" ? "tree.male" : "tree.female")} · {d.index.status === "affected" ? `${t("tree.affected")}: ${d.index.affected_with}` : t("fi.notDiagnosed")}
                </dd>
              </div>
              <div>
                <dt className="text-ink-2">{t("fi.variants")}</dt>
                <dd className="font-medium" dir="ltr">{d.index.test ? d.index.test.detected.join(" / ") : "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-ink-2">{t("fi.notStored")}</dt>
                <dd className="font-medium" dir="ltr">{d.not_stored.length ? d.not_stored.join(", ") : "—"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-ink-2">{t("fi.hash")}</dt>
                <dd className="break-all font-mono text-xs" dir="ltr">{d.source.sha256}</dd>
              </div>
            </dl>
            {d.warnings.length > 0 && (
              <Notice className="mt-3" role="status">
                <strong className="font-semibold">{t("fi.warnings")}</strong>
                <ul className="mt-1 list-disc ps-5" dir="ltr" lang="en">{d.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              </Notice>
            )}
            {d.notes.length > 0 && <ul className="mt-3 list-disc ps-5 text-xs text-ink-2" dir="ltr" lang="en">{d.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
            {result?.created && result.case_id ? (
              <p className="mt-4 text-sm">
                <span className="font-semibold text-accent">✓ {t("fi.created")}</span>{" "}
                <Link className="text-accent underline underline-offset-4" href={`/counsellor/cases/${result.case_id}`}>{t("fi.open")}</Link>
                <span className="mt-1 block text-ink-2">{t("fi.awaits")}</span>
              </p>
            ) : (
              <div className="mt-4 flex flex-wrap items-end gap-3">
                <label className="grid gap-1 text-sm" htmlFor="fi-family">
                  {t("fi.family")}
                  <select id="fi-family" className={inputCls} value={fam} onChange={(e) => setFamily(e.target.value)}>
                    {(families.data || []).map((f) => <option key={f.id} value={f.id}>{f.display_name}</option>)}
                  </select>
                </label>
                <Button variant="primary" disabled={busy || !fam} onClick={() => void send(false)}>{t("fi.create")}</Button>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
