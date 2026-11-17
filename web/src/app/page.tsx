"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AboutInfo } from "@/components/About";
import { CriteriaGuide, HeroPedigree, OnlySilsila } from "@/components/HomeParts";
import { JudgeMode } from "@/components/JudgeMode";
import { Page } from "@/components/Shell";
import { Button, ErrorBox, Eyebrow, Field, H1, H2, Notice, inputCls } from "@/components/ui";
import { API_URL, api, setSession } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { User } from "@/lib/types";

export default function Landing() {
  const { t, session } = usePrefs();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // Identity providers (UAE PASS, the organisation's staff directory) appear only when the API has them configured.
  const [providers, setProviders] = useState<{ id: string; role: string; start: string }[]>([]);
  useEffect(() => {
    api<{ id: string; role: string; start: string }[]>("/api/auth/oidc/providers", { auth: false })
      .then(setProviders)
      .catch(() => setProviders([]));
  }, []);

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
    <Page wide>
      <Notice className="mb-8">
        <strong className="font-semibold">{t("app.prototype")}</strong> {t("footer.fictional")}
      </Notice>

      <div className="grid gap-12 [&>*]:min-w-0">
        <section aria-labelledby="intro" className="grid items-center gap-8 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <div>
            <Eyebrow>{t("app.tagline")}</Eyebrow>
            <H1 className="mt-3 text-balance sm:text-4xl">
              <span id="intro">
                <span className="block text-ink-2">{t("home.hook1")}</span>
                <span className="block text-accent">{t("home.hook2")}</span>
              </span>
            </H1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-2">{t("home.lead")}</p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link href="/cascade" className="inline-flex min-h-12 flex-col justify-center rounded-xl bg-accent px-5 py-2 text-accent-ink hover:opacity-90">
                <span className="font-semibold">▶ {t("home.watch")}</span>
                <span className="text-xs opacity-90">{t("home.watchD")}</span>
              </Link>
              <Link href="/twin" className="inline-flex min-h-12 items-center rounded-xl border border-line-strong bg-surface px-4 font-medium text-ink hover:bg-surface-2">
                {t("home.twin")}
              </Link>
              <Link href="/evidence" className="inline-flex min-h-12 items-center rounded-xl border border-line-strong bg-surface px-4 font-medium text-ink hover:bg-surface-2">
                {t("home.evidence")}
              </Link>
              {/* jumps to the one-click roles further down, so judges find them from the first screen */}
              <a href="#try" className="inline-flex min-h-12 items-center rounded-xl border-2 border-accent bg-surface px-4 font-semibold text-accent hover:bg-surface-2">
                {t("home.try")} ↓
              </a>
              <a href="#signin" onClick={() => document.getElementById("signin")?.setAttribute("open", "")}
                className="inline-flex min-h-12 items-center rounded-xl border border-line-strong bg-surface px-4 font-medium text-ink hover:bg-surface-2">
                {t("signin.title")} ↓
              </a>
            </div>
          </div>
          <HeroPedigree />
        </section>

        <OnlySilsila />

        <div id="try" className="scroll-mt-24">
          <JudgeMode />
        </div>

        <CriteriaGuide />

        <section aria-labelledby="how-h">
          <H2 id="how-h">{t("landing.how")}</H2>
          <ol className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
        </section>

        <details id="signin" className="group scroll-mt-24 rounded-2xl border border-line bg-surface p-4 sm:px-6" open={!!session}>
          <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-3 font-semibold text-ink">
            <span>{session ? t("signin.title") : t("home.signin")}</span>
            <span aria-hidden="true" className="text-muted transition-transform group-open:rotate-180">⌄</span>
          </summary>
          {session ? (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <p className="text-ink-2">{t("signin.signedInAs", { name: session.user.display_name })}</p>
              <Button variant="primary" onClick={() => router.push(session.user.role === "counsellor" ? "/counsellor" : "/family")}>
                {t("signin.continue")}
              </Button>
            </div>
          ) : (
            <>
            {providers.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-3">
                {providers.map((p) => (
                  <a key={p.id} href={`${API_URL}${p.start}`}
                    className="inline-flex min-h-11 items-center rounded-xl border border-line bg-surface px-4 font-semibold text-ink hover:bg-surface-2">
                    {t(p.role === "counsellor" ? "signin.oidc.staff" : "signin.oidc.family")}
                  </a>
                ))}
              </div>
            ) : null}
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
              <div className="flex flex-wrap items-center gap-3">
                <Button type="submit" variant="primary" disabled={busy || !username || !password}>
                  {busy ? t("signin.busy") : t("signin.submit")}
                </Button>
                {/* the guest route sits beside the login button: one-click roles, no password */}
                <a href="#try" className="inline-flex min-h-11 items-center rounded-xl border-2 border-accent bg-surface px-4 font-semibold text-accent hover:bg-surface-2">
                  {t("home.try")}
                </a>
              </div>
              <p className="text-xs text-muted">{t("landing.credentials")}</p>
            </form>
            </>
          )}
          <p className="mt-4 text-sm text-muted">{t("landing.relativeHint")}</p>
        </details>

        <AboutInfo />
      </div>
    </Page>
  );
}
