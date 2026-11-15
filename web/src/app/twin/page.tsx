"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Page } from "@/components/Shell";
import { Button, Card, Chip, ErrorBox, Eyebrow, H1, H2, Loading, Notice, Num, Prov, cx } from "@/components/ui";
import { usePrefs } from "@/lib/prefs";
import { fetchClan, originPath, pct, whatIf, type RaceEvent, type Result, type TwinClan, type WhatIf } from "@/lib/twin";

const TwinScene = dynamic(() => import("@/components/twin/TwinScene").then((m) => m.TwinScene), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center rounded-2xl bg-[#071719] text-sm text-white/70">…</div>,
});

type Strategy = "ranked" | "family_order";

function useReducedMotion(): boolean {
  const [r, setR] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setR(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, []);
  return r;
}

export default function TwinPage() {
  const { t, lang } = usePrefs();
  const reduced = useReducedMotion();
  const [clan, setClan] = useState<TwinClan | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [results, setResults] = useState<Record<string, Result>>({});
  const [calc, setCalc] = useState<WhatIf | null>(null);
  const [ripple, setRipple] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showOrigin, setShowOrigin] = useState(false);
  const [table, setTable] = useState(false);
  const [race, setRace] = useState<{ strategy: Strategy; step: number } | null>(null);
  const raceTimer = useRef<number | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    fetchClan().then(setClan).catch(setError);
  }, []);

  const recompute = useCallback(async (next: Record<string, Result>, from: string | null) => {
    const my = ++seq.current;
    try {
      const r = await whatIf(next);
      if (my !== seq.current) return;
      setCalc(r);
      setRipple(from);
      setError(null);
    } catch (e) {
      if (my === seq.current) setError(e);
    }
  }, []);

  useEffect(() => {
    if (!clan) return;
    let live = true;
    whatIf({})
      .then((r) => live && setCalc(r))
      .catch((e) => live && setError(e));
    return () => {
      live = false;
    };
  }, [clan]);

  const byId = useMemo(
    () => new Map((clan?.people || []).map((p) => [p.id, { ...p, name: lang === "ar" && p.name_ar ? p.name_ar : p.name }])),
    [clan, lang],
  );
  const names = useMemo(() => Object.fromEntries([...byId.values()].map((p) => [p.id, p.name])), [byId]);
  const nGen = useMemo(() => new Set((clan?.people || []).map((p) => p.generation)).size, [clan]);
  const probs = calc?.status === "ok" ? calc.p_carrier! : null;
  const origin = useMemo(() => (clan && probs && showOrigin ? originPath(clan, probs) : null), [clan, probs, showOrigin]);

  const setResult = (id: string, r: Result | null) => {
    stopRace();
    const next = { ...results };
    if (r === null) delete next[id];
    else next[id] = r;
    setResults(next);
    void recompute(next, id);
  };

  function stopRace() {
    if (raceTimer.current) window.clearTimeout(raceTimer.current);
    raceTimer.current = null;
    setRace(null);
  }

  const play = (strategy: Strategy) => {
    if (!clan) return;
    stopRace();
    const events = clan.race[strategy];
    const acc: Record<string, Result> = {};
    setResults({});
    setSelected(null);
    const stepTo = (i: number) => {
      if (i >= events.length) {
        raceTimer.current = null;
        return;
      }
      const e = events[i];
      acc[e.person] = e.carrier ? e.detected.join(",") : "clear";
      setResults({ ...acc });
      setRace({ strategy, step: i + 1 });
      void recompute({ ...acc }, e.person);
      raceTimer.current = window.setTimeout(() => stepTo(i + 1), reduced ? 250 : 1100);
    };
    setRace({ strategy, step: 0 });
    raceTimer.current = window.setTimeout(() => stepTo(0), 300);
  };

  useEffect(() => () => stopRace(), []);

  if (!clan) {
    return (
      <Page wide>
        {error ? <ErrorBox error={error} /> : <Loading />}
      </Page>
    );
  }

  const sel = selected ? byId.get(selected) : null;
  const fixed = sel ? !!sel.test || sel.status === "affected" : false;
  const raceEvents: RaceEvent[] = race ? clan.race[race.strategy].slice(0, race.step) : [];
  const raceCouples = raceEvents.length ? raceEvents[raceEvents.length - 1].total_couples : 0;
  const findable = clan.race.true_atrisk_couples.length;
  const nextNames = (calc?.next_best || []).filter((id) => !results[id]).slice(0, 3).map((id) => byId.get(id)?.name || id);

  return (
    <Page wide>
      <Eyebrow>{t("tw.eyebrow")}</Eyebrow>
      <H1 className="mt-2 max-w-3xl text-balance">{t("tw.title")}</H1>
      <p className="mt-3 max-w-3xl text-ink-2">{t("tw.lead")}</p>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        <Chip>{t("tw.relatives", { n: clan.people.length })}</Chip>
        <Chip>{t("tw.generations", { n: nGen })}</Chip>
        <Chip>{t("tw.cousin", { n: clan.consanguineous.length })}</Chip>
        {calc && (
          <span className="flex items-center gap-2 rounded-full border border-accent px-2.5 py-0.5 text-xs font-medium text-accent" aria-live="polite">
            <Prov kind="calculated" />
            <Num>{t("tw.recompute", { ms: Math.round(calc.ms) })}</Num>
          </span>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid gap-3">
          <div className="h-[58vh] min-h-[360px] lg:h-[72vh]">
            <TwinScene
              clan={clan}
              probs={probs}
              results={results}
              selected={selected}
              onSelect={setSelected}
              rippleFrom={ripple}
              origin={origin}
              reducedMotion={reduced}
              label={t("tw.sceneLabel")}
              names={names}
              affectedLabel={t("tw.affected")}
            />
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-2">
            <span className="flex items-center gap-2">
              <span className="h-2.5 w-24 rounded-full" style={{ background: "linear-gradient(90deg,#1d3836,#25625c,#3fa293,#b7c25e,#f0a93a,#ff8547,#fff1d6)" }} aria-hidden="true" />
              {t("tw.legendLow")} → {t("tw.legendHigh")}
            </span>
            <span className="flex items-center gap-2"><span className="h-1 w-6 rounded bg-[#f2c14e]" aria-hidden="true" />{t("tw.legendGold")}</span>
            <span>● ♀ · ■ ♂</span>
            <Button size="sm" variant="quiet" onClick={() => setTable((x) => !x)}>{table ? t("tw.tableHide") : t("tw.table")}</Button>
          </div>
          {calc?.status === "inconsistent" && <Notice role="alert">{t("tw.inconsistent")}</Notice>}
          {error ? <ErrorBox error={error} /> : null}
          {table && probs && (
            <div className="max-h-96 overflow-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label={t("tw.table")}>
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface-2 text-xs uppercase tracking-wide text-muted">
                  <tr><th className="px-3 py-2 text-start">{t("tw.colPerson")}</th><th className="px-3 py-2 text-start">{t("tw.colGen")}</th><th className="px-3 py-2 text-start">{t("tw.colChance")}</th></tr>
                </thead>
                <tbody>
                  {[...byId.values()].sort((a, b) => (probs[b.id] ?? 0) - (probs[a.id] ?? 0)).map((p) => (
                    <tr key={p.id} className={cx("border-t border-line", selected === p.id && "bg-accent-soft")}>
                      <td className="px-3 py-1.5">
                        <button type="button" className="text-start underline-offset-4 hover:underline" onClick={() => setSelected(p.id)}>
                          {p.name}{p.deceased ? ` (${t("tw.deceased").toLowerCase()})` : ""}
                        </button>
                      </td>
                      <td className="px-3 py-1.5"><Num>{p.generation + 1}</Num></td>
                      <td className="px-3 py-1.5"><Num>{p.status === "affected" ? t("tw.affected") : pct(probs[p.id] ?? 0)}</Num>{results[p.id] ? ` · ${results[p.id] === "clear" ? t("tw.clearFound") : t("tw.carrierFound", { v: results[p.id] })}` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="grid content-start gap-4">
          <Card>
            {!sel ? (
              <p className="text-sm text-ink-2">{t("tw.pick")}</p>
            ) : (
              <div>
                <div className="flex items-start justify-between gap-2">
                  <H2>{sel.name}</H2>
                  <Button size="sm" variant="quiet" onClick={() => setSelected(null)} aria-label="Close">×</Button>
                </div>
                <p className="mt-1 text-sm text-muted">
                  {t("tw.gen", { g: sel.generation + 1, n: nGen })}{sel.deceased ? ` · ${t("tw.deceased")}` : ""}
                </p>
                <div className="mt-3 flex items-center gap-2">
                  <Prov kind="calculated" />
                  <span className="text-sm text-ink-2">{t("tw.chance")}:</span>
                  <span className="text-2xl font-semibold tabular-nums">
                    {sel.status === "affected" ? t("tw.affected") : probs ? pct(probs[sel.id] ?? 0) : "…"}
                  </span>
                </div>
                {fixed ? (
                  <p className="mt-3 text-sm text-muted">{t("tw.fixedResult")}</p>
                ) : (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button size="sm" variant="primary" disabled={sel.deceased} onClick={() => setResult(sel.id, "carrier")}>{t("tw.recordCarrier")}</Button>
                    <Button size="sm" disabled={sel.deceased} onClick={() => setResult(sel.id, "clear")}>{t("tw.recordClear")}</Button>
                    {results[sel.id] && <Button size="sm" variant="quiet" onClick={() => setResult(sel.id, null)}>{t("tw.remove")}</Button>}
                  </div>
                )}
              </div>
            )}
            {nextNames.length > 0 && <p className="mt-4 border-t border-line pt-3 text-xs text-muted">{t("tw.next", { names: nextNames.join(lang === "ar" ? "، " : ", ") })}</p>}
          </Card>

          <Card>
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold">{t("tw.results")}</h2>
              {Object.keys(results).length > 0 && (
                <Button size="sm" variant="quiet" onClick={() => { stopRace(); setResults({}); void recompute({}, null); }}>{t("tw.clearAll")}</Button>
              )}
            </div>
            {Object.keys(results).length === 0 ? (
              <p className="mt-2 text-sm text-muted">{t("tw.none")}</p>
            ) : (
              <ul className="mt-2 flex flex-wrap gap-2">
                {Object.entries(results).map(([id, r]) => (
                  <li key={id}>
                    <button type="button" onClick={() => setSelected(id)} className="rounded-full border border-line-strong px-2.5 py-0.5 text-xs hover:border-accent">
                      {byId.get(id)?.name}: {r === "clear" ? t("tw.clearFound") : t("tw.carrierFound", { v: r === "carrier" ? "B" : r })}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <h2 className="text-base font-semibold">{t("tw.origin")}</h2>
            <p className="mt-1 text-sm text-ink-2">{t("tw.originLead")}</p>
            <Button size="sm" className="mt-3" variant={showOrigin ? "secondary" : "primary"} onClick={() => setShowOrigin((x) => !x)}>
              {showOrigin ? t("tw.originHide") : t("tw.origin")}
            </Button>
            {showOrigin && calc?.founders && (
              <ul className="mt-3 grid gap-1 text-sm">
                {calc.founders.slice(0, 4).map((f) => (
                  <li key={f.id} className="flex items-center justify-between gap-2">
                    <span>{byId.get(f.id)?.name}</span>
                    <span className="flex items-center gap-2"><Prov kind="calculated" /><Num>{pct(f.p)}</Num></span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <h2 className="text-base font-semibold">{t("tw.race")}</h2>
            <p className="mt-1 text-sm text-ink-2">{t("tw.raceLead")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="primary" onClick={() => play("ranked")}>{t("tw.playRanked")}</Button>
              <Button size="sm" onClick={() => play("family_order")}>{t("tw.playFamily")}</Button>
              {race && <Button size="sm" variant="quiet" onClick={stopRace}>{t("tw.stop")}</Button>}
            </div>
            {race && (
              <div className="mt-4" aria-live="polite">
                <p className="text-sm font-medium">{race.strategy === "ranked" ? t("tw.playRanked").replace(/^.*?: /, "") : t("tw.playFamily").replace(/^.*?: /, "")}</p>
                <div className="mt-2 flex items-baseline gap-4">
                  <span><span className="text-2xl font-semibold tabular-nums">{race.step}</span> <span className="text-sm text-muted">{t("tw.tests")}</span></span>
                  <span><span className="text-2xl font-semibold tabular-nums text-brass">{raceCouples}</span> <span className="text-sm text-muted">{t("tw.couples")} · {t("tw.of", { n: findable })}</span></span>
                </div>
                <div className="mt-2 h-2 w-full rounded-full bg-surface-2"><div className="h-2 rounded-full bg-brass transition-all" style={{ width: `${(raceCouples / Math.max(findable, 1)) * 100}%` }} /></div>
                <div className="mt-3 max-h-40 overflow-auto" tabIndex={0} role="region" aria-label={t("tw.race")}>
                <ol className="grid gap-1 text-xs text-ink-2">
                  {raceEvents.slice().reverse().map((e, i) => (
                    <li key={i}>
                      <Num>{raceEvents.length - i}.</Num> {byId.get(e.person)?.name}: {e.carrier ? t("tw.carrierFound", { v: e.detected.join("/") }) : t("tw.clearFound")}
                      {e.couples_found.length > 0 && <strong className="text-brass"> · +{e.couples_found.length}</strong>}
                    </li>
                  ))}
                </ol>
                </div>
              </div>
            )}
            <p className="mt-4 border-t border-line pt-3 text-xs text-muted">{t("tw.raceNote")}</p>
          </Card>

          <p className="text-xs text-muted">{t("tw.honesty")}</p>
        </div>
      </div>
    </Page>
  );
}
