"use client";

import { useRef } from "react";
import { cx } from "./ui";

export interface TabDef<K extends string> {
  key: K;
  label: string;
  badge?: number | string | null;
}

/** Accessible tab bar (arrow keys move between tabs; mirrors in RTL). */
export function Tabs<K extends string>({
  tabs,
  active,
  onChange,
  label,
  idBase,
}: {
  tabs: TabDef<K>[];
  active: K;
  onChange: (k: K) => void;
  label: string;
  idBase: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <div role="tablist" aria-label={label} className="flex min-w-max gap-1 border-b border-line">
        {tabs.map((tab, i) => (
          <button
            key={tab.key}
            ref={(el) => {
              refs.current[i] = el;
            }}
            id={`${idBase}-tab-${tab.key}`}
            role="tab"
            type="button"
            aria-selected={active === tab.key}
            aria-controls={`${idBase}-panel`}
            tabIndex={active === tab.key ? 0 : -1}
            onClick={() => onChange(tab.key)}
            onKeyDown={(e) => {
              const rtl = document.documentElement.dir === "rtl";
              const next = e.key === (rtl ? "ArrowLeft" : "ArrowRight");
              const prev = e.key === (rtl ? "ArrowRight" : "ArrowLeft");
              if (!next && !prev) return;
              e.preventDefault();
              const j = (i + (next ? 1 : -1) + tabs.length) % tabs.length;
              refs.current[j]?.focus();
              onChange(tabs[j].key);
            }}
            className={cx(
              "relative -mb-px flex min-h-11 items-center gap-2 border-b-2 px-3 text-sm font-medium whitespace-nowrap",
              active === tab.key ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {tab.label}
            {tab.badge !== undefined && tab.badge !== null && tab.badge !== 0 && (
              <span className="rounded-full bg-accent-soft px-1.5 text-xs tabular-nums text-ink">{tab.badge}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TabPanel({ idBase, active, children }: { idBase: string; active: string; children: React.ReactNode }) {
  return (
    <div id={`${idBase}-panel`} role="tabpanel" aria-labelledby={`${idBase}-tab-${active}`} tabIndex={0} className="pt-6 focus-visible:outline-offset-4">
      {children}
    </div>
  );
}
