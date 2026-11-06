"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { AboutInfo } from "@/components/About";
import { AskBox, SectionTitle, StatusChip } from "@/components/case";
import { Parts } from "@/components/Parts";
import { Page } from "@/components/Shell";
import { Button, Card, ErrorBox, H1, Loading, Notice, Prov, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { InvitationStatus, RelativeView, TeachbackResult } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

function Relative() {
  const { code } = useParams<{ code: string }>();
  const { t, lang } = usePrefs();
  const { data, error, loading, reload } = useLoad(
    () => api<RelativeView>(`/api/r/${encodeURIComponent(code)}`, { query: { lang }, auth: false }),
    `${code}:${lang}`,
  );
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [score, setScore] = useState<TeachbackResult | null>(null);
  const [status, setStatus] = useState<InvitationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [actError, setActError] = useState<unknown>(null);

  if (loading && !data) return <Loading />;
  if (error && !data) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return (
        <Card>
          <H1 className="text-xl sm:text-2xl">{t("rel.title")}</H1>
          <p className="mt-3 text-ink-2">{t("rel.invalid")}</p>
        </Card>
      );
    }
    return <ErrorBox error={error} onRetry={reload} />;
  }
  if (!data) return null;

  const current = status || data.status;
  const done = ["booked", "declined_by_relative", "tested", "closed"].includes(current);
  const q = data.teachback;
  const allAnswered = q.every((x) => answers[x.id]);

  async function submitTeachback(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setActError(null);
    try {
      const r = await api<TeachbackResult>(`/api/r/${encodeURIComponent(code)}/teachback`, { body: { answers }, auth: false });
      setScore(r);
      if (r.passed && current === "opened") setStatus("understood");
    } catch (err) {
      setActError(err);
    } finally {
      setBusy(false);
    }
  }

  async function respond(action: "book" | "decline") {
    setBusy(true);
    setActError(null);
    try {
      const r = await api<{ status: InvitationStatus }>(`/api/r/${encodeURIComponent(code)}/respond`, {
        method: "POST",
        query: { action },
        auth: false,
      });
      setStatus(r.status);
    } catch (err) {
      setActError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <H1>{t("rel.title")}</H1>
        <span className="flex items-center gap-2 text-sm text-ink-2">
          {t("rel.currentStatus")} <StatusChip status={current} />
        </span>
      </div>

      <Card className="mt-6">
        <Parts parts={data.message} />
      </Card>

      <section className="mt-10" aria-labelledby="info-h">
        <SectionTitle id="info-h">{t("rel.info")}</SectionTitle>
        <Parts parts={data.information} />
      </section>

      <section className="mt-10" aria-labelledby="check-h">
        <SectionTitle id="check-h">{t("rel.check")}</SectionTitle>
        <p className="-mt-2 mb-4 text-sm text-muted">{t("rel.checkHint")}</p>
        <form onSubmit={submitTeachback} className="grid gap-4">
          {q.map((question, qi) => {
            const res = score?.items[question.id];
            return (
              <fieldset key={question.id} className="rounded-xl border border-line bg-surface p-4">
                <legend className="sr-only">{question[lang]}</legend>
                <p aria-hidden="true" className="flex gap-2 font-medium">
                  <span className="text-muted tabular-nums">{qi + 1}.</span>
                  <span>{question[lang]}</span>
                </p>
                <div className="mt-3 grid gap-2">
                  {question.options.map((o) => (
                    <label
                      key={o.id}
                      className={cx(
                        "flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-[0.95rem]",
                        answers[question.id] === o.id ? "border-accent bg-accent-soft/50" : "border-line",
                      )}
                    >
                      <input
                        type="radio"
                        name={question.id}
                        value={o.id}
                        className="h-5 w-5 shrink-0 accent-[var(--accent)]"
                        checked={answers[question.id] === o.id}
                        onChange={() => {
                          setAnswers({ ...answers, [question.id]: o.id });
                          setScore(null);
                        }}
                      />
                      <span>{o[lang]}</span>
                    </label>
                  ))}
                </div>
                {res && !res.correct && res.evidence.startsWith("mp:") && (
                  <p className="mt-2 text-sm text-ink-2">
                    {t("rel.evidence")}:{" "}
                    <a href={`#${res.evidence}`} className="text-accent underline underline-offset-2" onClick={(e) => {
                      const el = document.querySelector(`[data-part-id="${CSS.escape(res.evidence)}"]`);
                      if (el) {
                        e.preventDefault();
                        el.scrollIntoView({ block: "center" });
                      }
                    }}>
                      <code className="text-xs">{res.evidence}</code>
                    </a>
                  </p>
                )}
              </fieldset>
            );
          })}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={!allAnswered || busy}>
              {t("rel.submit")}
            </Button>
            {score && (
              <p role="status" className="flex items-center gap-2 text-sm">
                <Prov kind="recorded" />
                {t("rel.score", { score: score.score, total: score.total })}
              </p>
            )}
          </div>
        </form>
      </section>

      <section className="mt-10" aria-labelledby="next-h">
        <SectionTitle id="next-h">{t("rel.next")}</SectionTitle>
        <Parts parts={data.consent_note} compact />
        {done ? (
          <Notice className="mt-4" role="status">
            {current === "declined_by_relative" ? t("rel.done.declined") : t("rel.done.booked")}
          </Notice>
        ) : (
          <div className="mt-4 flex flex-wrap gap-3">
            <Button variant="primary" onClick={() => respond("book")} disabled={busy}>
              {t("rel.book")}
            </Button>
            <Button onClick={() => respond("decline")} disabled={busy}>
              {t("rel.decline")}
            </Button>
          </div>
        )}
        {actError ? <div className="mt-3"><ErrorBox error={actError} /></div> : null}
      </section>

      <section className="mt-10" aria-labelledby="ask-h">
        <SectionTitle id="ask-h">{t("rel.ask")}</SectionTitle>
        <AskBox inviteCode={code} />
      </section>

      <div className="mt-10">
        <AboutInfo />
      </div>
    </>
  );
}

export default function RelativePage() {
  return (
    <Page>
      <Relative />
    </Page>
  );
}
