"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { layoutPedigree } from "@/lib/pedigreeLayout";
import { usePrefs } from "@/lib/prefs";
import type { LocusInfo as Locus, PedPerson, Pedigree, Report } from "@/lib/types";
import { cx } from "./ui";

const UNIT = 136; // horizontal slot
const ROW = 178; // generation spacing
const S = 40; // symbol size
const PAD_X = 28;
const PAD_Y = 34;

function splitName(name: string): [string, string | null] {
  const m = name.match(/^(.*?)\s*\((.*)\)\s*$/);
  return m ? [m[1], m[2]] : [name, null];
}

function clip(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

export function isCarrier(p: PedPerson, locus?: Locus): boolean {
  const det = p.test?.detected || [];
  if (p.status === "affected" || det.length === 0) return false;
  if (!locus) return det.length === 1;
  const pathogenic = new Set(locus.alleles.filter((a) => a.pathogenic).map((a) => a.id));
  return det.filter((d) => pathogenic.has(d)).length === 1;
}

export function Symbol({
  sex,
  affected,
  carrier,
  deceased,
  size = S,
  x = 0,
  y = 0,
}: {
  sex: "male" | "female";
  affected?: boolean;
  carrier?: boolean;
  deceased?: boolean;
  size?: number;
  x?: number;
  y?: number;
}) {
  const h = size / 2;
  const fill = affected ? "var(--ink)" : "var(--surface)";
  return (
    <g transform={`translate(${x},${y})`}>
      {sex === "male" ? (
        <rect x={-h} y={-h} width={size} height={size} fill={fill} stroke="var(--ink)" strokeWidth={2} />
      ) : (
        <circle r={h} fill={fill} stroke="var(--ink)" strokeWidth={2} />
      )}
      {carrier && <circle r={size * 0.13} fill="var(--ink)" />}
      {deceased && <line x1={-h - 7} y1={h + 7} x2={h + 7} y2={-h - 7} stroke="var(--ink)" strokeWidth={2} />}
    </g>
  );
}

export function PedigreeChart({
  pedigree,
  report,
  indexId,
  selectedId,
  onSelect,
  marks,
  startFit = false,
}: {
  pedigree: Pedigree;
  report?: Report | null;
  indexId?: string;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  /** Optional cascade state per person: a ring and a short label (also read to screen readers). */
  marks?: Record<string, { label: string; tone: "info" | "done" | "alert" }>;
  /** Start scaled to fit its column (people can still switch to full size). */
  startFit?: boolean;
}) {
  const { t } = usePrefs();
  const layout = useMemo(() => layoutPedigree(pedigree), [pedigree]);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [wrapW, setWrapW] = useState(0);
  // Start in "fit" mode on phone-width screens so the whole family is visible.
  const [fit, setFit] = useState(
    () => startFit || (typeof window !== "undefined" && window.matchMedia("(max-width: 640px)").matches),
  );

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWrapW(el.clientWidth));
    ro.observe(el);
    setWrapW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const W = layout.width * UNIT + PAD_X * 2;
  const H = (layout.depth - 1) * ROW + S + 100 + PAD_Y * 2;
  const overflow = wrapW > 0 && W > wrapW;

  const cx_ = (id: string) => PAD_X + layout.x[id] * UNIT + UNIT / 2;
  const cy_ = (id: string) => PAD_Y + layout.gen[id] * ROW + S / 2;

  const kinship = new Map<string, number>();
  for (const c of report?.couples || []) {
    kinship.set([c.female, c.male].sort().join("|"), c.kinship);
  }

  // stagger sibship lines of couples in the same row so they stay distinct
  const rowCount: Record<number, number> = {};
  const sibOffset = new Map<string, number>();
  for (const c of layout.couples) {
    if (!c.children.length) continue;
    const g = layout.gen[c.children[0]];
    const k = rowCount[g] || 0;
    rowCount[g] = k + 1;
    sibOffset.set(`${c.a}|${c.b}`, k);
  }

  const lines: React.ReactNode[] = [];
  for (const c of layout.couples) {
    const [l, r] = cx_(c.a) <= cx_(c.b) ? [c.a, c.b] : [c.b, c.a];
    const x1 = cx_(l);
    const x2 = cx_(r);
    const y1 = cy_(l);
    const y2 = cy_(r);
    const related = (kinship.get([c.a, c.b].sort().join("|")) || 0) > 0;
    const key = `${c.a}|${c.b}`;
    if (y1 === y2) {
      const xa = x1 + S / 2;
      const xb = x2 - S / 2;
      if (related) {
        lines.push(
          <g key={`u-${key}`}>
            <line x1={xa} x2={xb} y1={y1 - 3} y2={y1 - 3} stroke="var(--ink)" strokeWidth={1.6} />
            <line x1={xa} x2={xb} y1={y1 + 3} y2={y1 + 3} stroke="var(--ink)" strokeWidth={1.6} />
          </g>,
        );
      } else {
        lines.push(<line key={`u-${key}`} x1={xa} x2={xb} y1={y1} y2={y1} stroke="var(--ink)" strokeWidth={1.6} />);
      }
    } else {
      lines.push(<line key={`u-${key}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--ink)" strokeWidth={1.6} />);
    }
    if (c.children.length) {
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2 + (related ? 3 : 0);
      const childTop = Math.min(...c.children.map((k) => cy_(k))) - S / 2;
      const sibY = childTop - 22 - (sibOffset.get(key) || 0) * 7;
      const xs = c.children.map(cx_);
      const lo = Math.min(mx, ...xs);
      const hi = Math.max(mx, ...xs);
      lines.push(
        <g key={`s-${key}`} stroke="var(--ink-2)" strokeWidth={1.4} fill="none">
          <line x1={mx} x2={mx} y1={my} y2={sibY} />
          <line x1={lo} x2={hi} y1={sibY} y2={sibY} />
          {c.children.map((k) => (
            <line key={k} x1={cx_(k)} x2={cx_(k)} y1={sibY} y2={cy_(k) - S / 2} />
          ))}
        </g>,
      );
    }
  }

  const calcLabel = t("prov.calculated");

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">{t("tree.hint")}</p>
        {overflow && (
          <div role="group" aria-label={t("tree.title")} className="inline-flex rounded-lg border border-line-strong p-0.5 text-xs">
            <button
              type="button"
              aria-pressed={!fit}
              onClick={() => setFit(false)}
              className={cx("min-h-8 rounded-md px-2.5", !fit && "bg-accent-soft font-semibold text-ink")}
            >
              {t("tree.actual")}
            </button>
            <button
              type="button"
              aria-pressed={fit}
              onClick={() => setFit(true)}
              className={cx("min-h-8 rounded-md px-2.5", fit && "bg-accent-soft font-semibold text-ink")}
            >
              {t("tree.fit")}
            </button>
          </div>
        )}
      </div>
      <div
        ref={wrapRef}
        dir="ltr"
        className="relative overflow-x-auto overscroll-x-contain rounded-xl border border-line bg-surface"
        style={{ touchAction: "pan-x pan-y pinch-zoom" }}
        tabIndex={0}
        role="region"
        aria-label={t("tree.region")}
      >
        <svg
          role="group"
          aria-label={t("tree.diagramLabel", { n: pedigree.people.length })}
          viewBox={`0 0 ${W} ${H}`}
          width={fit || !overflow ? "100%" : W}
          height={fit || !overflow ? undefined : H}
          style={!overflow ? { maxWidth: W, display: "block", margin: "0 auto" } : { display: "block" }}
          className="select-none"
        >
          <g>{lines}</g>
          {pedigree.people.map((p) => {
            const x = cx_(p.id);
            const y = cy_(p.id);
            const pr = report?.people?.[p.id];
            const affected = p.status === "affected";
            const carrier = isCarrier(p, report?.locus);
            const [nm, rel] = splitName(p.name || p.id);
            // A negative test with no published detection rate: the chance that remains cannot be
            // calculated, so the tree shows the recorded result instead of a calculated "0".
            const recordedClear = !affected && !!pr?.residual_note;
            const chance = !affected && pr && !recordedClear ? pr.computed.chance_text : null;
            const selected = selectedId === p.id;
            const aria = [
              p.name || p.id,
              t(p.sex === "male" ? "tree.male" : "tree.female"),
              t(`person.status.${p.status || "unknown"}`),
              carrier ? t("tree.carrier") : null,
              p.deceased ? t("person.deceased") : null,
              p.pregnant ? t("person.pregnant") : null,
              p.id === indexId ? t("tree.index") : null,
              chance ? `${calcLabel}: ${chance}` : null,
              recordedClear ? `${t("prov.recorded")}: ${t("tree.noVariant")}` : null,
              marks?.[p.id]?.label ?? null,
            ]
              .filter(Boolean)
              .join(", ");
            return (
              <g
                key={p.id}
                role={onSelect ? "button" : "img"}
                tabIndex={onSelect ? 0 : undefined}
                aria-label={aria}
                aria-pressed={onSelect ? selected : undefined}
                onClick={onSelect ? () => onSelect(p.id) : undefined}
                onKeyDown={
                  onSelect
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelect(p.id);
                        }
                      }
                    : undefined
                }
                className={cx(onSelect && "cursor-pointer", "pedigree-person")}
              >
                <rect
                  x={x - UNIT / 2 + 6}
                  y={y - S / 2 - 12}
                  width={UNIT - 12}
                  height={S + 104}
                  rx={10}
                  fill={selected ? "var(--accent-soft)" : "transparent"}
                  stroke={selected ? "var(--accent)" : "none"}
                  strokeWidth={1.5}
                />
                <Symbol sex={p.sex} affected={affected} carrier={carrier} deceased={!!p.deceased} x={x} y={y} />
                {marks?.[p.id] && (() => {
                  const m = marks[p.id];
                  const col = m.tone === "done" ? "var(--accent)" : m.tone === "alert" ? "#c2410c" : "var(--brass)";
                  return (
                    <g aria-hidden="true">
                      <circle cx={x} cy={y} r={S * 0.82} fill="none" stroke={col} strokeWidth={3.5}
                        strokeDasharray={m.tone === "info" ? "6 5" : undefined} className="cascade-ring" />
                      <rect x={x - 46} y={y - S / 2 - 40} width={92} height={22} rx={11} fill={col} />
                      <text x={x} y={y - S / 2 - 25} textAnchor="middle" fontSize="12" fontWeight={700} fill="#fff">
                        {m.label}
                      </text>
                    </g>
                  );
                })()}
                {p.pregnant && (
                  <g transform={`translate(${x + S / 2 + 12},${y - S / 2 - 1})`}>
                    <path d="M0 -10 L10 0 L0 10 L-10 0 Z" fill="var(--surface)" stroke="var(--ink)" strokeWidth={1.5} />
                    <text textAnchor="middle" dy="4" fontSize="11" fontWeight={700} fill="var(--ink)">
                      P
                    </text>
                  </g>
                )}
                {p.id === indexId && (
                  <g stroke="var(--brass)" fill="var(--brass)" strokeWidth={2.4}>
                    <line x1={x - S / 2 - 26} y1={y + S / 2 + 16} x2={x - S / 2 - 6} y2={y + S / 2 - 2} />
                    <path
                      d={`M${x - S / 2 - 3} ${y + S / 2 - 5} l-9.5 1.5 l6.5 7 z`}
                      strokeWidth={1}
                    />
                  </g>
                )}
                <text x={x} y={y + S / 2 + 19} textAnchor="middle" fontSize="13" fontWeight={600} fill="var(--ink)">
                  {clip(nm, 17)}
                </text>
                {rel && (
                  <text x={x} y={y + S / 2 + 35} textAnchor="middle" fontSize="11" fill="var(--muted)">
                    {clip(rel, 21)}
                  </text>
                )}
                {chance && (
                  <g>
                    <rect
                      x={x - 34}
                      y={y + S / 2 + 44}
                      width={68}
                      height={15}
                      rx={3}
                      fill="var(--tag-calculated-bg)"
                    />
                    <text
                      x={x}
                      y={y + S / 2 + 55}
                      textAnchor="middle"
                      fontSize="9"
                      fontWeight={700}
                      letterSpacing="0.06em"
                      fill="var(--tag-calculated)"
                    >
                      {calcLabel.toUpperCase()}
                    </text>
                    <text x={x} y={y + S / 2 + 74} textAnchor="middle" fontSize="12.5" fontWeight={500} fill="var(--ink)">
                      {chance}
                    </text>
                  </g>
                )}
                {recordedClear && (
                  <g>
                    <rect x={x - 34} y={y + S / 2 + 44} width={68} height={15} rx={3} fill="var(--tag-recorded-bg)" />
                    <text x={x} y={y + S / 2 + 55} textAnchor="middle" fontSize="9" fontWeight={700} letterSpacing="0.06em" fill="var(--tag-recorded)">
                      {t("prov.recorded").toUpperCase()}
                    </text>
                    <text x={x} y={y + S / 2 + 74} textAnchor="middle" fontSize="12.5" fontWeight={500} fill="var(--ink)">
                      {t("tree.noVariant")}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <Legend />
    </div>
  );
}

export function Legend() {
  const { t } = usePrefs();
  const item = (key: Parameters<typeof t>[0], sym: React.ReactNode) => (
    <li className="flex items-center gap-2">
      <svg viewBox="-16 -16 32 32" className="h-6 w-6 shrink-0" aria-hidden="true">
        {sym}
      </svg>
      <span>{t(key)}</span>
    </li>
  );
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer font-medium text-ink-2">{t("tree.legend")}</summary>
      <ul className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1.5 text-ink-2 sm:grid-cols-2">
        {item("tree.male", <Symbol sex="male" size={20} />)}
        {item("tree.female", <Symbol sex="female" size={20} />)}
        {item("tree.affected", <Symbol sex="female" affected size={20} />)}
        {item("tree.carrier", <Symbol sex="male" carrier size={20} />)}
        {item("tree.unknown", <Symbol sex="female" size={20} />)}
        {item("tree.deceased", <Symbol sex="male" deceased size={16} />)}
        {item(
          "tree.consanguineous",
          <g stroke="var(--ink)" strokeWidth={1.6}>
            <line x1={-14} x2={14} y1={-3} y2={-3} />
            <line x1={-14} x2={14} y1={3} y2={3} />
          </g>,
        )}
        {item(
          "tree.pregnancy",
          <g>
            <path d="M0 -11 L11 0 L0 11 L-11 0 Z" fill="var(--surface)" stroke="var(--ink)" strokeWidth={1.5} />
            <text textAnchor="middle" dy="4" fontSize="11" fontWeight={700} fill="var(--ink)">
              P
            </text>
          </g>,
        )}
        {item(
          "tree.index",
          <g stroke="var(--brass)" fill="var(--brass)" strokeWidth={2.4}>
            <line x1={-12} y1={12} x2={4} y2={-4} />
            <path d="M8 -8 l-10 1.5 l7 7 z" strokeWidth={1} />
          </g>,
        )}
      </ul>
    </details>
  );
}
