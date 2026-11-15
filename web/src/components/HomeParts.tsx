"use client";

// Home page: the picture, the four things only Silsila does (each with a measured number from
// docs/evidence, repeated in README), and a guide that ties each judging criterion to something a judge can
// open, the number behind it, and what is not yet shown.

import Link from "next/link";
import { usePrefs } from "@/lib/prefs";
import type { StringKey } from "@/lib/strings";
import { H2, Num, cx } from "./ui";

/** A three-generation family with one cousin marriage: the newborn's result, and who is told first. */
export function HeroPedigree() {
  const { t } = usePrefs();
  const line = { stroke: "var(--line-strong)", strokeWidth: 2, fill: "none" } as const;
  const person = { stroke: "var(--ink)", strokeWidth: 2, fill: "var(--surface)" } as const;
  return (
    <figure className="rounded-2xl border border-line bg-surface p-4">
      <svg viewBox="0 0 360 268" className="h-auto w-full" role="img" aria-label={t("home.figure")}>
        {/* grandparents */}
        <path d="M150 34h60M180 34v34M90 68h180M90 68v24M270 68v24" {...line} />
        <rect x="126" y="22" width="24" height="24" rx="2" {...person} />
        <circle cx="222" cy="34" r="12" {...person} />
        {/* two brothers and their wives */}
        <path d="M46 104h32M282 104h32M62 104v40M298 104v40M34 144h92M34 144v22M126 144v22M250 144h48M250 144v22" {...line} />
        <circle cx="34" cy="104" r="12" {...person} />
        <rect x="78" y="92" width="24" height="24" rx="2" {...person} />
        <rect x="258" y="92" width="24" height="24" rx="2" {...person} />
        <circle cx="326" cy="104" r="12" {...person} />
        {/* cousins who married: double line */}
        <path d="M138 175h100M138 181h100" stroke="var(--brass)" strokeWidth="2" fill="none" />
        <path d="M188 181v38" {...line} />
        {/* the sister, first to be told */}
        <circle cx="34" cy="178" r="20" fill="none" stroke="var(--brass)" strokeWidth="3" strokeDasharray="6 5" className="cascade-ring" />
        <circle cx="34" cy="178" r="12" {...person} />
        <path d="M58 166l9 9-9 9-9-9z" fill="var(--surface)" stroke="var(--ink)" strokeWidth="1.5" />
        <circle cx="126" cy="178" r="12" {...person} />
        <rect x="238" y="166" width="24" height="24" rx="2" {...person} />
        {/* the newborn with the result */}
        <circle cx="188" cy="232" r="21" fill="none" stroke="#c2410c" strokeWidth="3" className="cascade-ring" />
        <rect x="176" y="220" width="24" height="24" rx="2" fill="var(--ink)" stroke="var(--ink)" strokeWidth="2" />
        <g fontSize="11" fontWeight="600" fill="var(--ink-2)">
          <text x="188" y="264" textAnchor="middle">{t("home.fig.result")}</text>
          <text x="34" y="214" textAnchor="middle">{t("home.fig.first")}</text>
          <text x="188" y="162" textAnchor="middle" fill="var(--brass)">{t("home.fig.cousins")}</text>
        </g>
      </svg>
      <figcaption className="mt-2 text-sm text-ink-2">{t("home.figCaption")}</figcaption>
    </figure>
  );
}

const ONLY: { n: string; k: number; href: string }[] = [
  { n: "30,000 / 30,000", k: 1, href: "/evidence" },
  { n: "1.58×", k: 2, href: "/evidence" },
  { n: "59.4%", k: 3, href: "/evidence" },
  { n: "0 / 10,000", k: 4, href: "/evidence" },
];

export function OnlySilsila({ links = true }: { links?: boolean }) {
  const { t } = usePrefs();
  return (
    <section aria-labelledby="only-h">
      <H2 id="only-h">{t("home.only")}</H2>
      <ul className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {ONLY.map((o) => (
          <li key={o.k} className="flex flex-col rounded-2xl border border-line bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-brass">{t(`home.only${o.k}.t` as StringKey)}</p>
            <p className="mt-2 text-3xl font-semibold tracking-tight text-ink"><Num>{o.n}</Num></p>
            <p className="mt-2 flex-1 text-sm text-ink-2">{t(`home.only${o.k}.d` as StringKey)}</p>
            {links && <Link href={o.href} className="mt-3 text-sm font-medium text-accent underline underline-offset-4">{t("home.source")}</Link>}
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted">{t("home.onlyNote")}</p>
    </section>
  );
}

const CRITERIA: { k: number; href: string }[] = [
  { k: 1, href: "/cascade" },
  { k: 2, href: "/twin" },
  { k: 3, href: "#judge-h" },
  { k: 4, href: "/cascade" },
  { k: 5, href: "/evidence" },
  { k: 6, href: "/evidence" },
];

export function CriteriaGuide() {
  const { t } = usePrefs();
  return (
    <section aria-labelledby="crit-h">
      <H2 id="crit-h">{t("home.crit")}</H2>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{t("home.critLead")}</p>
      <ol className="mt-4 grid gap-3 lg:grid-cols-2">
        {CRITERIA.map((c) => (
          <li key={c.k} className="rounded-2xl border border-line bg-surface p-4 sm:p-5">
            <p className="flex items-baseline gap-2">
              <span aria-hidden="true" className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent text-sm font-semibold text-accent-ink">{c.k}</span>
              <span className="font-semibold text-ink">{t(`home.crit${c.k}.t` as StringKey)}</span>
            </p>
            <dl className="mt-3 grid gap-2 text-sm">
              {(["see", "measured", "notyet"] as const).map((row) => (
                <div key={row} className="grid gap-0.5 sm:grid-cols-[7.5rem_1fr] sm:gap-3">
                  <dt className={cx("text-xs font-semibold uppercase tracking-wide", row === "notyet" ? "text-brass" : "text-ink-2")}>{t(`home.${row}` as StringKey)}</dt>
                  <dd className="text-ink-2">
                    {row === "see" ? (
                      <Link href={c.href} className="font-medium text-accent underline underline-offset-4">{t(`home.crit${c.k}.see` as StringKey)}</Link>
                    ) : (
                      t(`home.crit${c.k}.${row}` as StringKey)
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ol>
    </section>
  );
}
