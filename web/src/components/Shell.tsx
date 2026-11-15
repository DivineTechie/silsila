"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePrefs } from "@/lib/prefs";
import type { ReactNode } from "react";
import { cx } from "./ui";

export function Logo({ className }: { className?: string }) {
  // A short chain of pedigree symbols: square, circle, square joined by a line.
  return (
    <svg viewBox="0 0 48 20" aria-hidden="true" className={className} fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="4" width="12" height="12" rx="1.5" />
      <circle cx="24" cy="10" r="6.5" />
      <rect x="34" y="4" width="12" height="12" rx="1.5" />
      <path d="M14 10h3.5M30.5 10H34" />
      <circle cx="24" cy="10" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function Header({ wide = false }: { wide?: boolean }) {
  const { t, lang, setLang, theme, toggleTheme, session, signOut } = usePrefs();
  const router = useRouter();
  const home = session?.user.role === "counsellor" ? "/counsellor" : session ? "/family" : "/";
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/95 backdrop-blur supports-[backdrop-filter]:bg-bg/80">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:start-2 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
      >
        {t("nav.skip")}
      </a>
      <div className={cx("mx-auto flex items-center gap-2 px-4 py-2.5", wide ? "max-w-7xl" : "max-w-3xl")}>
        <Link href={home} className="flex min-h-11 items-center gap-2 rounded-md text-accent" aria-label={t("app.name")}>
          <Logo className="h-5 w-12" />
          <span className="text-lg font-semibold tracking-tight text-ink">{t("app.name")}</span>
        </Link>
        <nav className="ms-auto flex items-center gap-1" aria-label="Main">
          <Link href="/cascade" className="hidden min-h-11 items-center rounded-md px-2.5 text-sm text-ink-2 hover:text-ink sm:inline-flex">
            {t("nav.cascade")}
          </Link>
          <Link href="/twin" className="hidden min-h-11 items-center rounded-md px-2.5 text-sm text-ink-2 hover:text-ink sm:inline-flex">
            {t("nav.twin")}
          </Link>
          <Link href="/evidence" className="hidden min-h-11 items-center rounded-md px-2.5 text-sm text-ink-2 hover:text-ink sm:inline-flex">
            {t("nav.evidence")}
          </Link>
          <button
            type="button"
            onClick={() => setLang(lang === "ar" ? "en" : "ar")}
            aria-label={t("lang.switchLabel")}
            lang={lang === "ar" ? "en" : "ar"}
            className="min-h-11 rounded-md px-2.5 text-sm font-medium text-ink hover:bg-surface-2"
          >
            {t("lang.switch")}
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={t("theme.label")}
            title={t("theme.label")}
            className="grid h-11 w-11 place-items-center rounded-md text-ink-2 hover:bg-surface-2"
          >
            {theme === "dark" ? (
              <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <circle cx="10" cy="10" r="3.5" />
                <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4" />
              </svg>
            ) : (
              <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path d="M15.5 12.5A6.5 6.5 0 0 1 7.5 4.5a6.5 6.5 0 1 0 8 8z" />
              </svg>
            )}
          </button>
          {session && (
            <button
              type="button"
              onClick={() => {
                signOut();
                router.push("/");
              }}
              className="min-h-11 rounded-md px-2.5 text-sm text-ink-2 hover:bg-surface-2 hover:text-ink"
            >
              {t("nav.signout")}
            </button>
          )}
        </nav>
      </div>
    </header>
  );
}

export function Footer({ wide = false }: { wide?: boolean }) {
  const { t } = usePrefs();
  return (
    <footer className="mt-16 border-t border-line">
      <div className={cx("mx-auto flex flex-col gap-1.5 px-4 py-6 text-xs text-muted", wide ? "max-w-7xl" : "max-w-3xl")}>
        <p>{t("app.prototype")} {t("footer.fictional")}</p>
        <p>{t("footer.noai")}</p>
        <p lang="en" dir="ltr" className="text-start">Arabic text is machine-translated and pending native clinical review.</p>
        <p lang="ar" dir="rtl" className="text-start">النص العربي مترجم آلياً وبانتظار مراجعة سريرية من متحدثين أصليين.</p>
        <p className="mt-2 flex gap-4">
          <Link href="/" className="underline underline-offset-2 hover:text-ink">{t("nav.home")}</Link>
          <Link href="/evidence" className="underline underline-offset-2 hover:text-ink">{t("nav.evidence")}</Link>
        </p>
      </div>
    </footer>
  );
}

export function Page({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <>
      <Header wide={wide} />
      <main id="main" className={cx("mx-auto w-full flex-1 px-4 py-6 sm:py-10", wide ? "max-w-7xl" : "max-w-3xl")}>
        {children}
      </main>
      <Footer wide={wide} />
    </>
  );
}
