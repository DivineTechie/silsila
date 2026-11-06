"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AboutInfo } from "@/components/About";
import { Page } from "@/components/Shell";
import { Button, Card, ErrorBox, Eyebrow, Field, H1, H2, Notice, inputCls } from "@/components/ui";
import { api, setSession } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { User } from "@/lib/types";

export default function Landing() {
  const { t, session } = usePrefs();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ token: string; user: User }>("/api/auth/login", {
        body: { username: username.trim(), password },
        auth: false,
      });
      setSession({ token: r.token, user: r.user });
      setPassword("");
      router.push(r.user.role === "counsellor" ? "/counsellor" : "/family");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const steps = ["landing.step1", "landing.step2", "landing.step3", "landing.step4"] as const;

  return (
    <Page>
      <Notice className="mb-8">
        <strong className="font-semibold">{t("app.prototype")}</strong> {t("footer.fictional")}
      </Notice>

      <div className="grid gap-10">
        <section aria-labelledby="intro">
          <Eyebrow>{t("app.tagline")}</Eyebrow>
          <H1 className="mt-3 max-w-2xl text-balance">
            <span id="intro">{t("landing.title")}</span>
          </H1>
          <p className="mt-4 max-w-2xl text-lg leading-relaxed text-ink-2">{t("landing.lead")}</p>
          <div className="rule-dots mt-8" aria-hidden="true" />
          <H2 className="mt-6">{t("landing.how")}</H2>
          <ol className="mt-4 grid gap-3 sm:grid-cols-2">
            {steps.map((k, i) => (
              <li key={k} className="flex gap-3 rounded-xl border border-line bg-surface p-4">
                <span
                  aria-hidden="true"
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 border-accent text-sm font-semibold text-accent"
                >
                  {i + 1}
                </span>
                <span className="text-[0.95rem] text-ink">{t(k)}</span>
              </li>
            ))}
          </ol>
          <p className="mt-6">
            <Link href="/evidence" className="font-medium text-accent underline underline-offset-4">
              {t("landing.evidenceLink")}
            </Link>
          </p>
        </section>

        <Card aria-labelledby="signin-h">
          <H2 id="signin-h">{t("signin.title")}</H2>
          {session ? (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <p className="text-ink-2">{t("signin.signedInAs", { name: session.user.display_name })}</p>
              <Button variant="primary" onClick={() => router.push(session.user.role === "counsellor" ? "/counsellor" : "/family")}>
                {t("signin.continue")}
              </Button>
            </div>
          ) : (
            <form onSubmit={submit} className="mt-4 grid gap-4 sm:max-w-sm" noValidate>
              <Field label={t("signin.username")} htmlFor="username">
                <input
                  id="username"
                  name="username"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className={inputCls}
                />
              </Field>
              <Field label={t("signin.password")} htmlFor="password">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={inputCls}
                />
              </Field>
              {error ? <ErrorBox error={error} /> : null}
              <Button type="submit" variant="primary" disabled={busy || !username || !password}>
                {busy ? t("signin.busy") : t("signin.submit")}
              </Button>
              <p className="text-xs text-muted">{t("landing.credentials")}</p>
            </form>
          )}
          <p className="mt-4 text-sm text-muted">{t("landing.relativeHint")}</p>
        </Card>

        <AboutInfo />
      </div>
    </Page>
  );
}
