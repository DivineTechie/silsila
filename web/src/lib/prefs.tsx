"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import { getSession, setSession, subscribeSession, type Session } from "./api";
import { ar, en, type StringKey } from "./strings";
import type { Lang } from "./types";

const LANG_KEY = "silsila.lang";
const THEME_KEY = "silsila.theme";
type Theme = "light" | "dark";

// ---------------------------------------------------------------- stores --
function makeStore<T>(read: () => T, server: T) {
  const subs = new Set<() => void>();
  return {
    subscribe(fn: () => void) {
      subs.add(fn);
      return () => subs.delete(fn);
    },
    get: read,
    server: () => server,
    notify() {
      subs.forEach((f) => f());
    },
  };
}

const langStore = makeStore<Lang>(() => {
  try {
    return window.localStorage.getItem(LANG_KEY) === "ar" ? "ar" : "en";
  } catch {
    return "en";
  }
}, "en");

const themeStore = makeStore<Theme>(() => {
  const t = document.documentElement.getAttribute("data-theme");
  return t === "dark" ? "dark" : "light";
}, "light");

export function applyLang(lang: Lang): void {
  try {
    window.localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  langStore.notify();
}

function applyTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* ignore */
  }
  document.documentElement.setAttribute("data-theme", theme);
  themeStore.notify();
}

/** Runs before first paint: sets lang, dir and theme from storage/URL. */
export const PREFS_SCRIPT = `(function(){try{var d=document.documentElement;var q=new URLSearchParams(location.search).get('lang');var l=q==='ar'||q==='en'?q:localStorage.getItem('${LANG_KEY}');if(q)localStorage.setItem('${LANG_KEY}',q);if(l==='ar'){d.lang='ar';d.dir='rtl';}var t=localStorage.getItem('${THEME_KEY}');if(!t){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}d.setAttribute('data-theme',t);}catch(e){}})();`;

// --------------------------------------------------------------- context --
type Vars = Record<string, string | number>;

interface Prefs {
  lang: Lang;
  setLang: (l: Lang) => void;
  theme: Theme;
  toggleTheme: () => void;
  t: (key: StringKey, vars?: Vars) => string;
  session: Session | null;
  signOut: () => void;
}

const Ctx = createContext<Prefs | null>(null);

function fill(s: string, vars?: Vars): string {
  if (!vars) return s;
  return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
}

const noSession = () => null;

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const lang = useSyncExternalStore(langStore.subscribe, langStore.get, langStore.server);
  const theme = useSyncExternalStore(themeStore.subscribe, themeStore.get, themeStore.server);
  const session = useSyncExternalStore(subscribeSession, getSession, noSession);

  useEffect(() => {
    // keep <html> in sync if storage changed in another tab
    const onStorage = (e: StorageEvent) => {
      if (e.key === LANG_KEY) langStore.notify();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setLang = useCallback((l: Lang) => applyLang(l), []);
  const toggleTheme = useCallback(() => applyTheme(theme === "dark" ? "light" : "dark"), [theme]);
  const t = useCallback(
    (key: StringKey, vars?: Vars) => fill((lang === "ar" ? ar : en)[key] ?? en[key] ?? key, vars),
    [lang],
  );
  const signOut = useCallback(() => setSession(null), []);

  const value = useMemo(
    () => ({ lang, setLang, theme, toggleTheme, t, session, signOut }),
    [lang, setLang, theme, toggleTheme, t, session, signOut],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePrefs(): Prefs {
  const v = useContext(Ctx);
  if (!v) throw new Error("PrefsProvider missing");
  return v;
}

// ------------------------------------------------------------- formatting --
// Western digits in both languages.
export function fmtDate(iso: string | undefined | null, withTime = true): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return withTime ? `${date} ${pad(d.getHours())}:${pad(d.getMinutes())}` : date;
}

export function fmtNum(x: number, digits = 4): string {
  if (!Number.isFinite(x)) return String(x);
  if (x !== 0 && Math.abs(x) < 1e-3) return x.toExponential(2);
  return Number(x.toPrecision(digits)).toLocaleString("en-US", { maximumFractionDigits: 6 });
}

export function fmtPct(x: number): string {
  return `${Number((x * 100).toPrecision(3)).toLocaleString("en-US", { maximumFractionDigits: 3 })}%`;
}

export function age(iso: string, t: Prefs["t"]): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.max(0, Math.round(ms / 60000));
  if (min < 60) return t("common.minutes", { n: min });
  const h = Math.round(min / 60);
  if (h < 48) return t("common.hours", { n: h });
  return t("common.days", { n: Math.round(h / 24) });
}

const noopSubscribe = () => () => {};
/** False during server render and hydration, true afterwards. */
export function useHydrated(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}
