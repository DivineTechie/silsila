"use client";

// Voice intake (counsellor only): recorded demo of speech -> transcript -> model-drafted family tree ->
// counsellor checks -> exact engine. Every change goes through the API, which re-checks the draft and
// writes an audit entry. The engine refuses a draft until everything is confirmed.

import { useEffect, useMemo, useState } from "react";
import { Contrast } from "./Contrast";
import { PedigreeChart } from "./PedigreeChart";
import { Button, Card, Chip, ErrorBox, H2, Loading, Notice, Num, Prov, cx, inputCls } from "./ui";
import { API_URL, api, getSession } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { Pedigree, Report } from "@/lib/types";

interface DraftPerson {
  id: string;
  name: string;
  sex: string;
  mother: string | null;
  father: string | null;
  mother_name: string | null;
  father_name: string | null;
  heard_status: string | null;
  heard_diagnosis: string | null;
  status: string;
  affected_with: string | null;
  status_source: string | null;
  record_ref?: string | null;
  pregnant?: boolean;
  deceased?: boolean;
  confirmed: boolean;
  added_by?: string;
}

interface DraftUnion {
  a: string | null;
  b: string | null;
  a_name: string | null;
  b_name: string | null;
  confirmed: boolean;
}

interface Draft {
  locus_id: string;
  people: DraftPerson[];
  unions: DraftUnion[];
}

interface Issue {
  code: string;
  severity: "block" | "check";
  person: string | null;
  persons?: string[];
  role?: "mother" | "father";
  message: string;
  heard?: string;
  suggest?: { set_parent?: string; add_unknown_parent?: string; partner_of?: string };
}

interface State {
  draft: Draft;
  issues: Issue[];
  unconfirmed: number;
  ready: boolean;
}

interface Demo extends State {
  recorded: boolean;
  audio_label: string;
  script: string;
  transcript: string;
  asr: { model: string; dialect: string | null };
  drafter: { model: string; latency_s: number; created_at: string; tool_called: boolean; engine_check: string };
}

type Action = Record<string, unknown> & { type: string };

/** A chart-safe pedigree: the layout needs both parents or neither, so half-known parents are hidden. */
function chartPedigree(d: Draft): Pedigree {
  const ids = new Set(d.people.map((p) => p.id));
  return {
    people: d.people.map((p) => {
      const both = p.mother && p.father && ids.has(p.mother) && ids.has(p.father);
      return {
        id: p.id,
        name: p.name,
        sex: p.sex === "female" ? "female" : "male",
        mother: both ? p.mother : null,
        father: both ? p.father : null,
        status: (p.status as "affected" | "unaffected" | "unknown") || "unknown",
        affected_with: p.affected_with,
        pregnant: !!p.pregnant,
        deceased: !!p.deceased,
      };
    }),
    unions: d.unions.filter((u) => u.a && u.b && ids.has(u.a) && ids.has(u.b)).map((u) => ({ a: u.a!, b: u.b! })),
  };
}

function useDemoAudio(): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let revoke: string | null = null;
    const token = getSession()?.token;
    fetch(API_URL + "/api/intake/demo/audio", { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((b) => {
        revoke = URL.createObjectURL(b);
        setSrc(revoke);
      })
      .catch(() => setSrc(null));
    return () => {
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, []);
  return src;
}

function RecordForm({ person, onSave, onCancel }: {
  person: DraftPerson;
  onSave: (a: Action) => void;
  onCancel: () => void;
}) {
  const { t } = usePrefs();
  const [status, setStatus] = useState(person.heard_status || "affected");
  const [dx, setDx] = useState(person.heard_diagnosis || "");
  const [ref, setRef] = useState("");
  const idp = `rec-${person.id}`;
  return (
    <form
      className="mt-2 grid gap-2 rounded-lg border border-line bg-surface-2 p-3 sm:grid-cols-[auto_1fr_1fr_auto] sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ type: "set_status_from_record", person: person.id, status, affected_with: status === "affected" ? dx : null, record_ref: ref });
      }}
    >
      <label className="grid gap-1 text-sm" htmlFor={`${idp}-s`}>
        {t("vi.status")}
        <select id={`${idp}-s`} className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="affected">affected</option>
          <option value="unaffected">unaffected</option>
          <option value="unknown">{t("vi.unknown")}</option>
        </select>
      </label>
      <label className="grid gap-1 text-sm" htmlFor={`${idp}-d`}>
        {t("vi.diagnosis")}
        <input id={`${idp}-d`} className={inputCls} value={dx} disabled={status !== "affected"} onChange={(e) => setDx(e.target.value)} />
      </label>
      <label className="grid gap-1 text-sm" htmlFor={`${idp}-r`}>
        {t("vi.recordRef")}
        <input id={`${idp}-r`} className={inputCls} value={ref} required={status !== "unknown"} onChange={(e) => setRef(e.target.value)} />
      </label>
      <div className="flex gap-2">
        <Button type="submit" size="sm" variant="primary">{t("vi.save")}</Button>
        <Button type="button" size="sm" variant="quiet" onClick={onCancel}>{t("vi.cancel")}</Button>
      </div>
    </form>
  );
}

export function VoiceIntake() {
  const { t, lang } = usePrefs();
  const audio = useDemoAudio();
  const [demo, setDemo] = useState<Demo | null>(null);
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [recordFor, setRecordFor] = useState<string | null>(null);
  const [result, setResult] = useState<{ pedigree: Pedigree; report: Report } | null>(null);
  const [showScript, setShowScript] = useState(false);

  const fetchDemo = () =>
    api<Demo>("/api/intake/demo")
      .then((d) => {
        setDemo(d);
        setState({ draft: d.draft, issues: d.issues, unconfirmed: d.unconfirmed, ready: d.ready });
        setError(null);
        setResult(null);
        setRecordFor(null);
      })
      .catch(setError);
  const load = () => {
    void fetchDemo();
  };
  useEffect(() => void fetchDemo(), []);

  const act = async (action: Action) => {
    if (!state) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setState(await api<State>("/api/intake/apply", { body: { draft: state.draft, action } }));
      setRecordFor(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const compute = async () => {
    if (!state) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api<{ pedigree: Pedigree; report: Report }>("/api/intake/compute", { body: { draft: state.draft, lang } }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const names = useMemo(() => Object.fromEntries((state?.draft.people || []).map((p) => [p.id, p.name])), [state]);
  const ped = useMemo(() => (state ? chartPedigree(state.draft) : null), [state]);

  if (!demo || !state) return error ? <ErrorBox error={error} onRetry={load} /> : <Loading />;

  const issueFix = (i: Issue) => {
    if (i.suggest?.set_parent)
      return act({ type: "set_parent", persons: i.persons || [i.person], role: i.role, parent: i.suggest.set_parent });
    if (i.suggest?.add_unknown_parent)
      return act({ type: "add_unknown_parent", persons: i.persons || [i.person], role: i.role, partner_of: i.suggest.partner_of });
  };
  const sorted = [...state.issues].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "block" ? -1 : 1));
  const index = result?.report.invites?.[0];

  return (
    <div className="grid gap-6 [&>*]:min-w-0">
      <div>
        <p className="max-w-3xl text-ink-2">{t("vi.lead")}</p>
      </div>

      <Card>
        <H2>{t("vi.step1")}</H2>
        <p className="mt-1 text-sm text-muted">{t("vi.audioLabel")}</p>
        {audio ? <audio controls src={audio} className="mt-3 w-full" /> : <Loading />}
        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
          <Chip>{t("vi.asr")}: <bdi dir="ltr" className="ms-1">{demo.asr.model}</bdi></Chip>
          {demo.asr.dialect && <Chip>{t("vi.dialect")}: <bdi dir="ltr" className="ms-1">{demo.asr.dialect}</bdi></Chip>}
          <Button size="sm" variant="quiet" onClick={() => setShowScript((s) => !s)}>
            {showScript ? t("vi.transcript") : t("vi.script")}
          </Button>
        </div>
        <p className="mt-3 rounded-lg bg-surface-2 p-3 leading-loose" dir="rtl" lang="ar">
          {showScript ? demo.script : demo.transcript}
        </p>
      </Card>

      <Card>
        <H2>{t("vi.step2")}</H2>
        <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <div><dt className="inline text-muted">{t("vi.drafter")}: </dt><dd className="inline" dir="ltr">{demo.drafter.model}</dd></div>
          <div><dt className="inline text-muted">{t("vi.latency")}: </dt><dd className="inline"><Num>{demo.drafter.latency_s} s</Num></dd></div>
          <div><dt className="inline text-muted">{t("vi.toolCall")}: </dt><dd className="inline">{demo.drafter.tool_called ? "✓" : "✗"}</dd></div>
          <div className="sm:col-span-2"><dt className="inline text-muted">{t("vi.engineCheck")}: </dt><dd className="inline" dir="auto">{demo.drafter.engine_check}</dd></div>
        </dl>
        <Notice className="mt-3">{t("vi.draftNote")}</Notice>
        {ped && (
          <div className="mt-4">
            <PedigreeChart pedigree={result?.pedigree || ped} report={result?.report} indexId={index?.person_id} />
          </div>
        )}
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <H2>{t("vi.step3")}</H2>
          <Button size="sm" variant="quiet" onClick={load} disabled={busy}>{t("vi.reset")}</Button>
        </div>
        {error ? <div className="mt-3"><ErrorBox error={error} /></div> : null}

        <h3 className="mt-4 text-sm font-semibold">{t("vi.issues")}</h3>
        {sorted.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("vi.noIssues")}</p>
        ) : (
          <ul className="mt-2 grid gap-2" dir="ltr" lang="en">
            {sorted.map((i, k) => (
              <li key={k} className={cx("rounded-lg border p-3 text-sm", i.severity === "block" ? "border-line-strong bg-surface-2" : "border-line")}>
                <div className="flex flex-wrap items-start gap-2">
                  <Chip className={i.severity === "block" ? "border-accent text-accent" : ""}>
                    {i.severity === "block" ? t("vi.block") : t("vi.check")}
                  </Chip>
                  <span className="min-w-0 flex-1" dir="auto">{i.message}</span>
                  {i.suggest && (
                    <Button size="sm" variant="secondary" disabled={busy} onClick={() => issueFix(i)}>{t("vi.applySuggestion")}</Button>
                  )}
                  {i.code === "heard_health_status" && i.person && (
                    <Button size="sm" variant="secondary" disabled={busy} onClick={() => setRecordFor(i.person)}>{t("vi.fromRecord")}</Button>
                  )}
                </div>
                {recordFor && recordFor === i.person && i.code === "heard_health_status" && (
                  <RecordForm
                    person={state.draft.people.find((p) => p.id === i.person)!}
                    onSave={act}
                    onCancel={() => setRecordFor(null)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t("vi.person")}</h3>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted">{t("vi.toConfirm", { n: state.unconfirmed })}</span>
            <Button size="sm" disabled={busy} onClick={() => act({ type: "confirm_all_people" })}>{t("vi.confirmAllPeople")}</Button>
          </div>
        </div>
        <div className="mt-2 overflow-x-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label={t("vi.person")}>
          <table className="w-full min-w-[44rem] text-sm">
            <thead className="bg-surface-2 text-start text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2 text-start">{t("vi.person")}</th>
                <th className="px-3 py-2 text-start">{t("vi.sex")}</th>
                <th className="px-3 py-2 text-start">{t("vi.mother")}</th>
                <th className="px-3 py-2 text-start">{t("vi.father")}</th>
                <th className="px-3 py-2 text-start">{t("vi.health")}</th>
                <th className="px-3 py-2 text-start">{t("vi.flags")}</th>
                <th className="px-3 py-2 text-start"><span className="sr-only">{t("vi.confirm")}</span></th>
              </tr>
            </thead>
            <tbody>
              {state.draft.people.map((p) => (
                <tr key={p.id} className="border-t border-line align-top">
                  <td className="px-3 py-2 font-medium"><bdi>{p.name}</bdi></td>
                  <td className="px-3 py-2">{p.sex}</td>
                  <td className="px-3 py-2">{p.mother ? <bdi>{names[p.mother]}</bdi> : <span className="text-muted">—</span>}</td>
                  <td className="px-3 py-2">{p.father ? <bdi>{names[p.father]}</bdi> : <span className="text-muted">—</span>}</td>
                  <td className="px-3 py-2">
                    {p.status_source === "record" ? (
                      <span className="flex flex-wrap items-center gap-1"><Prov kind="recorded" /> {p.status}{p.affected_with ? ` · ${p.affected_with}` : ""}</span>
                    ) : (
                      <span className="text-muted">{t("vi.unknown")}</span>
                    )}
                    {(p.heard_status || p.heard_diagnosis) && p.status_source !== "record" && (
                      <span className="mt-1 block text-xs text-muted">
                        {t("vi.heard")}: {p.heard_diagnosis || p.heard_status} ({t("vi.notUsed")})
                      </span>
                    )}
                    {recordFor === p.id && !state.issues.some((i) => i.person === p.id && i.code === "heard_health_status") && (
                      <RecordForm person={p} onSave={act} onCancel={() => setRecordFor(null)} />
                    )}
                    {p.status_source !== "record" && !p.heard_status && !p.heard_diagnosis && recordFor !== p.id && (
                      <Button size="sm" variant="quiet" onClick={() => setRecordFor(p.id)}>{t("vi.fromRecord")}</Button>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-col gap-1">
                      {p.sex === "female" && (
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={!!p.pregnant} disabled={busy}
                            onChange={(e) => act({ type: "set_flag", person: p.id, flag: "pregnant", value: e.target.checked })} />
                          {t("vi.pregnant")}
                        </label>
                      )}
                      <label className="flex items-center gap-2">
                        <input type="checkbox" checked={!!p.deceased} disabled={busy}
                          onChange={(e) => act({ type: "set_flag", person: p.id, flag: "deceased", value: e.target.checked })} />
                        {t("vi.deceased")}
                      </label>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-end">
                    {p.confirmed ? (
                      <span className="text-sm font-medium text-accent">✓ {t("vi.confirmed")}</span>
                    ) : (
                      <Button size="sm" disabled={busy} onClick={() => act({ type: "confirm_person", person: p.id })}>{t("vi.confirm")}</Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t("vi.marriages")}</h3>
          <Button size="sm" disabled={busy} onClick={() => act({ type: "confirm_all_unions" })}>{t("vi.confirmAllUnions")}</Button>
        </div>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2">
          {state.draft.unions.map((u, k) => (
            <li key={k} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 text-sm">
              <span><bdi>{(u.a && names[u.a]) || u.a_name}</bdi> — <bdi>{(u.b && names[u.b]) || u.b_name}</bdi></span>
              {u.confirmed ? (
                <span className="font-medium text-accent">✓ {t("vi.confirmed")}</span>
              ) : (
                <Button size="sm" disabled={busy} onClick={() => act({ type: "confirm_union", index: k })}>{t("vi.confirm")}</Button>
              )}
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <H2>{t("vi.step4")}</H2>
        {!state.ready && <p className="mt-2 text-sm text-muted">{t("vi.locked")}</p>}
        <Button className="mt-3" variant="primary" disabled={!state.ready || busy} onClick={compute}>{t("vi.compute")}</Button>
        {result?.report.people && (
          <div className="mt-4 grid gap-3">
            {index && (
              <p className="text-sm">
                <span className="text-muted">{t("vi.firstInvite")}: </span>
                <bdi className="font-semibold">{names[index.person_id]}</bdi>
              </p>
            )}
            <div className="overflow-x-auto rounded-xl border border-line" tabIndex={0} role="region" aria-label={t("vi.carrierChance")}>
              <table className="w-full text-sm">
                <thead className="bg-surface-2 text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-3 py-2 text-start">{t("vi.person")}</th>
                    <th className="px-3 py-2 text-start">{t("vi.carrierChance")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.report.people).map(([pid, r]) => (
                    <tr key={pid} className="border-t border-line">
                      <td className="px-3 py-2"><bdi>{names[pid]}</bdi></td>
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-2"><Prov kind="calculated" /><Num>{(r.computed.p_any_variant * 100).toFixed(1)}%</Num></span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      {result && <Contrast />}
    </div>
  );
}
