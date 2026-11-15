"use client";

// Judge mode: one-click entry as a demo persona (only when the API runs in demo mode with fictional data).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, ErrorBox, H2 } from "./ui";
import { api, setSession } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { StringKey } from "@/lib/strings";
import type { User } from "@/lib/types";
import { useLoad } from "@/lib/useLoad";

type Persona = "mariam" | "reem" | "counsellor" | "relative";

const PERSONAS: { key: Persona; title: StringKey; desc: StringKey }[] = [
  { key: "mariam", title: "judge.mariam", desc: "judge.mariamD" },
  { key: "counsellor", title: "judge.counsellor", desc: "judge.counsellorD" },
  { key: "relative", title: "judge.relative", desc: "judge.relativeD" },
  { key: "reem", title: "judge.reem", desc: "judge.reemD" },
];

export function JudgeMode() {
  const { t, setLang } = usePrefs();
  const router = useRouter();
  const health = useLoad(() => api<{ demo_mode: boolean }>("/api/health", { auth: false }), "health");
  const [busy, setBusy] = useState<Persona | null>(null);
  const [error, setError] = useState<unknown>(null);
  if (!health.data?.demo_mode) return null;

  async function enter(p: Persona) {
    setBusy(p);
    setError(null);
    try {
      if (p === "relative") {
        const r = await api<{ code: string }>("/api/demo/relative", { method: "POST", auth: false });
        router.push(`/r/${r.code}`);
        return;
      }
      const r = await api<{ token: string; user: User }>("/api/demo/login", { body: { persona: p }, auth: false });
      setSession({ token: r.token, user: r.user });
      if (r.user.lang === "ar") setLang("ar");
      router.push(r.user.role === "counsellor" ? "/counsellor" : "/family");
    } catch (e) {
      setError(e);
      setBusy(null);
    }
  }

  return (
    <Card aria-labelledby="judge-h" className="border-accent">
      <H2 id="judge-h">{t("judge.title")}</H2>
      <p className="mt-2 text-sm text-ink-2">{t("judge.lead")}</p>
      <Link
        href="/cascade"
        className="mt-4 flex flex-col gap-1 rounded-xl bg-accent p-4 text-accent-ink hover:opacity-90"
      >
        <span className="text-lg font-semibold">▶ {t("judge.cascade")}</span>
        <span className="text-sm opacity-90">{t("judge.cascadeD")}</span>
      </Link>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2">
        {PERSONAS.map((p) => (
          <li key={p.key}>
            <button
              type="button"
              onClick={() => enter(p.key)}
              disabled={busy !== null}
              className="flex h-full w-full flex-col items-start gap-1 rounded-xl border border-line-strong bg-surface p-4 text-start hover:border-accent hover:bg-accent-soft disabled:opacity-60"
            >
              <span className="font-semibold text-ink">{busy === p.key ? t("judge.busy") : t(p.title)}</span>
              <span className="text-sm text-ink-2">{t(p.desc)}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm text-muted">{t("judge.suggested")}</p>
      <Link href="/twin" className="mt-3 inline-flex font-medium text-accent underline underline-offset-4">
        {t("judge.twin")} →
      </Link>
      {error ? <div className="mt-3"><ErrorBox error={error} /></div> : null}
    </Card>
  );
}

export function ResetDemo({ onDone }: { onDone?: () => void }) {
  const { t } = usePrefs();
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<unknown>(null);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button
        size="sm"
        disabled={state === "busy"}
        onClick={async () => {
          setState("busy");
          setError(null);
          try {
            await api("/api/demo/reset", { method: "POST" });
            setState("done");
            onDone?.();
          } catch (e) {
            setError(e);
            setState("idle");
          }
        }}
      >
        {t("judge.reset")}
      </Button>
      {state === "done" && <span role="status" className="text-sm text-ink-2">{t("judge.resetDone")}</span>}
      {error ? <ErrorBox error={error} /> : null}
    </div>
  );
}
