"use client";

// Return page after signing in with an identity provider (UAE PASS or the organisation's staff directory).
// The API puts the Silsila token in the URL fragment, which is never sent to a server; this page reads it,
// removes it from the address bar, checks it with /api/me, and starts the normal session.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { H1, Loading } from "@/components/ui";
import { API_URL, setSession } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { User } from "@/lib/types";

export default function SignedIn() {
  const { t } = usePrefs();
  const router = useRouter();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    window.history.replaceState(null, "", window.location.pathname);
    (token ? fetch(`${API_URL}/api/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? (r.json() as Promise<User>) : Promise.reject(r.status))) : Promise.reject("no token"))
      .then((user) => {
        setSession({ token: token as string, user });
        router.replace(user.role === "counsellor" ? "/counsellor" : "/family");
      })
      .catch(() => setFailed(true));
  }, [router]);

  return (
    <Page>
      {failed ? (
        <>
          <H1>{t("signin.oidc.failed")}</H1>
          <p className="mt-4">
            <Link href="/" className="font-semibold text-accent underline">{t("signin.oidc.home")}</Link>
          </p>
        </>
      ) : (
        <>
          <H1>{t("signin.oidc.working")}</H1>
          <div className="mt-6"><Loading /></div>
        </>
      )}
    </Page>
  );
}
