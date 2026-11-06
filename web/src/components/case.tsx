"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDate, useHydrated, usePrefs } from "@/lib/prefs";
import type {
  CaseDetail,
  Consent,
  Invitation,
  InvitationStatus,
  MessageReply,
  Part,
  PedPerson,
  Pedigree,
  PersonStatus,
  Report,
  Role,
} from "@/lib/types";
import { Parts } from "./Parts";
import { isCarrier } from "./PedigreeChart";
import { Button, Card, Chip, ErrorBox, Field, H2, H3, Notice, Prov, cx, inputCls } from "./ui";

// ------------------------------------------------------------- role gate --
export function RequireRole({ role, children }: { role: Role; children: React.ReactNode }) {
  const { session, t } = usePrefs();
  // the session lives in sessionStorage: wait for the client before deciding
  const hydrated = useHydrated();
  if (!hydrated) return null;
  if (!session || session.user.role !== role) {
    return (
      <Card>
        <p className="text-ink-2">{t("signin.title")}</p>
        <Link href="/" className="mt-3 inline-flex min-h-11 items-center font-medium text-accent underline underline-offset-4">
          {t("nav.signin")}
        </Link>
      </Card>
    );
  }
  return <>{children}</>;
}

// ------------------------------------------------------------- consents --
export function ConsentCard({
  scope,
  consent,
  text,
  caseId,
  canChange,
  onChanged,
}: {
  scope: "compute" | "invite";
  consent?: Consent;
  text: Part[];
  caseId: string;
  canChange: boolean;
  onChanged: () => void;
}) {
  const { t } = usePrefs();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const granted = !!consent?.granted && !consent?.withdrawn_at;
  async function set(g: boolean) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/cases/${caseId}/consents`, { body: { scope, granted: g } });
      onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <H3>{t(scope === "compute" ? "perm.compute" : "perm.invite")}</H3>
        <span className="flex items-center gap-2 text-sm text-ink-2">
          <Prov kind="recorded" />
          {granted
            ? t("perm.granted", { date: fmtDate(consent?.granted_at, false) })
            : consent?.withdrawn_at
              ? t("perm.withdrawn", { date: fmtDate(consent.withdrawn_at, false) })
              : t("perm.notGranted")}
        </span>
      </div>
      <Parts parts={text} className="mt-3" compact />
      {canChange && (
        <div className="mt-4 flex flex-wrap gap-2">
          {granted ? (
            <Button size="sm" onClick={() => set(false)} disabled={busy}>
              {t("perm.withdraw")}
            </Button>
          ) : (
            <Button size="sm" variant="primary" onClick={() => set(true)} disabled={busy}>
              {t("perm.grant")}
            </Button>
          )}
        </div>
      )}
      {error ? <div className="mt-3"><ErrorBox error={error} /></div> : null}
    </div>
  );
}

// ------------------------------------------------------------- timeline --
const PATH: InvitationStatus[] = ["awaiting_counsellor", "sent", "opened", "understood", "booked", "tested", "closed"];
const OFF_PATH: InvitationStatus[] = ["withdrawn", "declined_by_relative", "no_response"];

export function StatusChip({ status }: { status: InvitationStatus }) {
  const { t } = usePrefs();
  const done = status === "closed" || OFF_PATH.includes(status);
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        done ? "bg-surface-2 text-ink-2" : "bg-accent-soft text-ink",
      )}
    >
      {t(`status.${status}`)}
    </span>
  );
}

export function StatusTimeline({ inv }: { inv: Invitation }) {
  const { t } = usePrefs();
  const at: Partial<Record<InvitationStatus, string>> = {};
  for (const h of inv.history) at[h.status] = h.at;
  const off = OFF_PATH.find((s) => at[s]);
  return (
    <ol className="mt-3 grid gap-0" aria-label={t("rel.currentStatus")}>
      {PATH.map((s, i) => {
        const reached = !!at[s];
        const current = s === inv.status;
        const last = i === PATH.length - 1 && !off;
        return (
          <li key={s} className="relative flex gap-3 pb-2.5" aria-current={current ? "step" : undefined}>
            {!last && (
              <span
                aria-hidden="true"
                className={cx("absolute start-[7px] top-4 h-full w-0.5", reached && at[PATH[i + 1]] ? "bg-accent" : "bg-line")}
              />
            )}
            <span
              aria-hidden="true"
              className={cx(
                "relative z-10 mt-0.5 h-4 w-4 shrink-0 rounded-full border-2",
                reached ? "border-accent bg-accent" : "border-line-strong bg-surface",
                current && "ring-4 ring-accent-soft",
              )}
            />
            <span className={cx("flex flex-1 flex-wrap items-baseline justify-between gap-x-3 text-sm", reached ? "text-ink" : "text-muted")}>
              <span className={cx(current && "font-semibold")}>{t(`status.${s}`)}</span>
              {at[s] && <span className="text-xs text-muted tabular-nums" dir="ltr">{fmtDate(at[s])}</span>}
            </span>
          </li>
        );
      })}
      {off && (
        <li className="relative flex gap-3" aria-current="step">
          <span aria-hidden="true" className="relative z-10 mt-0.5 h-4 w-4 shrink-0 rounded-sm border-2 border-ink-2 bg-surface-2" />
          <span className="flex flex-1 flex-wrap items-baseline justify-between gap-x-3 text-sm font-semibold">
            <span>{t(`status.${off}`)}</span>
            <span className="text-xs font-normal text-muted tabular-nums" dir="ltr">{fmtDate(at[off])}</span>
          </span>
        </li>
      )}
    </ol>
  );
}

// ----------------------------------------------------------- invitations --
export function InvitationCard({
  inv,
  role,
  report,
  onChanged,
}: {
  inv: Invitation;
  role: Role;
  report?: Report;
  onChanged: () => void;
}) {
  const { t } = usePrefs();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [copied, setCopied] = useState(false);
  const [v1, setV1] = useState("");
  const [v2, setV2] = useState("");
  const link = inv.code && typeof window !== "undefined" ? `${window.location.origin}/r/${inv.code}` : null;
  const sentOrLater = !["awaiting_counsellor", "approved", "withdrawn"].includes(inv.status);
  const canRecord = ["sent", "opened", "understood", "booked"].includes(inv.status);
  const pathogenic = (report?.locus?.alleles || []).filter((a) => a.pathogenic);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-xl border border-line bg-surface p-4" aria-label={inv.person_name}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <H3>{inv.person_name}</H3>
          <p className="mt-0.5 text-sm text-ink-2">
            {t(`channel.${inv.channel}`)}
            {" · "}
            {t("inform.condition")}: {inv.disclose_condition ? t("common.yes") : t("common.no")}
            {" · "}
            {t("inform.sender")}: {inv.disclose_sender ? inv.sender_name || t("common.yes") : t("common.no")}
          </p>
        </div>
        <StatusChip status={inv.status} />
      </div>
      <StatusTimeline inv={inv} />
      {inv.teachback && (
        <p className="mt-1 flex items-center gap-2 text-sm text-ink-2">
          <Prov kind="recorded" />
          {t("inform.teachback", { score: inv.teachback.score, total: inv.teachback.total })}
        </p>
      )}
      {inv.closure_evidence && (
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-2">
          <Prov kind="recorded" />
          {t("person.test")}:{" "}
          {Array.isArray(inv.closure_evidence.detected) && (inv.closure_evidence.detected as string[]).length
            ? t("person.testDetected", { alleles: (inv.closure_evidence.detected as string[]).join(", ") })
            : t("person.testNone")}
        </p>
      )}

      {link && sentOrLater && (role === "counsellor" || inv.channel === "self_share_letter") && (
        <div className="mt-3 rounded-lg border border-line bg-surface-2 p-3">
          <p className="text-xs font-semibold text-ink-2">{role === "counsellor" ? t("c.relativeLink") : t("inform.shareLink")}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all text-xs" dir="ltr">{link}</code>
            <Button
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(link);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                } catch {
                  /* clipboard unavailable */
                }
              }}
            >
              {copied ? t("common.copied") : t("common.copy")}
            </Button>
            {role === "counsellor" && (
              <Link href={`/r/${inv.code}`} target="_blank" className="text-sm font-medium text-accent underline underline-offset-4">
                {t("common.open")}
              </Link>
            )}
          </div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {role === "family" && ["awaiting_counsellor", "approved"].includes(inv.status) && (
          <Button size="sm" disabled={busy} onClick={() => act(() => api(`/api/invitations/${inv.id}/status`, { body: { status: "withdrawn" } }))}>
            {t("inform.withdraw")}
          </Button>
        )}
        {role === "counsellor" && inv.status === "awaiting_counsellor" && (
          <Button size="sm" variant="primary" disabled={busy} onClick={() => act(() => api(`/api/invitations/${inv.id}/approve`, { method: "POST" }))}>
            {t("c.approve")}
          </Button>
        )}
      </div>

      {role === "counsellor" && canRecord && (
        <form
          className="mt-4 grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            const detected = [v1, v2].filter(Boolean);
            void act(() => api(`/api/invitations/${inv.id}/result`, { body: { detected } }));
          }}
        >
          <p className="text-sm font-semibold sm:col-span-3">{t("c.record")}</p>
          {[
            [v1, setV1, 1],
            [v2, setV2, 2],
          ].map(([val, set, n]) => (
            <Field key={n as number} label={t("c.variant", { n: n as number })} htmlFor={`v${n}-${inv.id}`}>
              <select
                id={`v${n}-${inv.id}`}
                className={inputCls}
                value={val as string}
                onChange={(e) => (set as (s: string) => void)(e.target.value)}
              >
                <option value="">{t("c.noVariant")}</option>
                {pathogenic.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.id}: {a.label}
                  </option>
                ))}
              </select>
            </Field>
          ))}
          <Button type="submit" variant="primary" disabled={busy}>
            {t("c.record")}
          </Button>
          <p className="text-xs text-muted sm:col-span-3">{t("c.recordHint")}</p>
        </form>
      )}
      {error ? <div className="mt-3"><ErrorBox error={error} /></div> : null}
    </article>
  );
}

// --------------------------------------------------------- person detail --
export function PersonDetail({ person, detail }: { person: PedPerson; detail: CaseDetail }) {
  const { t } = usePrefs();
  const pr = detail.report.people?.[person.id];
  const carrier = isCarrier(person, detail.report.locus);
  return (
    <Card as="aside" className="mt-4" aria-live="polite">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <H3>{person.name || person.id}</H3>
        {person.id === detail.case.index_person_id && <Chip>{t("tree.index")}</Chip>}
      </div>
      <dl className="mt-3 grid gap-2 text-sm">
        <Row label={t("edit.status")} kind="recorded">
          {t(`person.status.${person.status || "unknown"}`)}
          {person.affected_with ? ` · ${t("person.affectedWith", { c: person.affected_with })}` : ""}
        </Row>
        {person.test && (
          <Row label={t("person.test")} kind="recorded">
            {person.test.detected.length ? t("person.testDetected", { alleles: person.test.detected.join(", ") }) : t("person.testNone")}
            {carrier ? ` · ${t("tree.carrier")}` : ""}
          </Row>
        )}
        {person.pregnant && <Row label={t("person.pregnant")} kind="recorded">{t("common.yes")}</Row>}
        {person.deceased && <Row label={t("person.deceased")} kind="recorded">{t("common.yes")}</Row>}
        {pr && person.status !== "affected" && (
          <Row label={t("person.chance")} kind="calculated">
            <span dir="ltr">{pr.computed.chance_text}</span>
          </Row>
        )}
      </dl>
      {pr?.sentence && <Parts parts={pr.sentence} className="mt-4" compact />}
      {pr?.residual_note && <Parts parts={pr.residual_note} className="mt-3" compact />}
      {!pr && detail.report.status === "ok" && <p className="mt-3 text-sm text-muted">{t("person.noCalc")}</p>}
    </Card>
  );
}

function Row({ label, kind, children }: { label: string; kind: "recorded" | "calculated"; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(7rem,auto)_1fr] items-baseline gap-x-3">
      <dt className="text-muted">{label}</dt>
      <dd className="flex flex-wrap items-center gap-2 text-ink">
        <Prov kind={kind} />
        <span>{children}</span>
      </dd>
    </div>
  );
}

// --------------------------------------------------------------- ask box --
export function AskBox({ caseId, inviteCode }: { caseId?: string; inviteCode?: string }) {
  const { t, lang } = usePrefs();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [replies, setReplies] = useState<{ q: string; r: MessageReply }[]>([]);
  const id = `ask-${caseId || inviteCode || "x"}`;
  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<MessageReply>("/api/messages", {
        body: { text: text.trim(), lang, case_id: caseId, invite_code: inviteCode },
        auth: !inviteCode,
      });
      setReplies((xs) => [{ q: text.trim(), r }, ...xs]);
      setText("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <form onSubmit={send} className="grid gap-3">
        <Field label={t("rel.askLabel")} htmlFor={id} hint={t("rel.askHint")}>
          <textarea
            id={id}
            rows={3}
            maxLength={2000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            className={cx(inputCls, "min-h-24 py-2")}
          />
        </Field>
        <div>
          <Button type="submit" variant="primary" disabled={busy || !text.trim()}>
            {t("rel.send")}
          </Button>
        </div>
      </form>
      {error ? <div className="mt-3"><ErrorBox error={error} /></div> : null}
      <div className="mt-4 grid gap-4" aria-live="polite">
        {replies.map(({ q, r }, i) => (
          <div key={i} className="rounded-xl border border-line bg-surface-2/50 p-4">
            <p className="text-sm text-muted">
              <span className="me-2 inline-flex"><Prov kind="recorded" /></span>
              {q}
            </p>
            {r.escalated && (
              <Notice className="mt-3" role="status">
                <strong className="font-semibold">{t("rel.alerted")}</strong>
              </Notice>
            )}
            <Parts parts={r.reply} className="mt-3" compact />
          </div>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------ tree edit --
function slug(s: string): string {
  const base = s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 16) || "person";
  return `${base}_${Math.random().toString(36).slice(2, 6)}`;
}

export function TreeEditor({ caseId, pedigree, onSaved }: { caseId: string; pedigree: Pedigree; onSaved: () => void }) {
  const { t } = usePrefs();
  const people = pedigree.people;
  const [mode, setMode] = useState<"add" | "update">("add");
  const [targetId, setTargetId] = useState(people[0]?.id || "");
  const target = people.find((p) => p.id === targetId);
  const blank = { name: "", sex: "female" as "male" | "female", mother: "", father: "", partner: "", status: "unknown" as PersonStatus, affected_with: "", pregnant: false, deceased: false };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  function loadTarget(id: string) {
    setTargetId(id);
    const p = people.find((x) => x.id === id);
    if (p)
      setForm({
        ...blank,
        name: p.name || "",
        sex: p.sex,
        status: p.status || "unknown",
        affected_with: p.affected_with || "",
        pregnant: !!p.pregnant,
        deceased: !!p.deceased,
      });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    const next: Pedigree = { people: people.map((p) => ({ ...p })), unions: [...(pedigree.unions || [])] };
    const fields = (p: PedPerson) => {
      p.name = form.name.trim() || p.name;
      p.status = form.status;
      p.affected_with = form.status === "affected" ? form.affected_with.trim() || null : null;
      p.pregnant = p.sex === "female" ? form.pregnant : false;
      p.deceased = form.deceased;
    };
    if (mode === "add") {
      const p: PedPerson = { id: slug(form.name), sex: form.sex, mother: form.mother || null, father: form.father || null };
      fields(p);
      next.people.push(p);
      if (form.partner) next.unions.push(form.sex === "female" ? { a: p.id, b: form.partner } : { a: form.partner, b: p.id });
    } else if (target) {
      fields(next.people.find((p) => p.id === target.id)!);
    }
    try {
      await api(`/api/cases/${caseId}/pedigree`, { method: "PUT", body: next });
      setSaved(true);
      if (mode === "add") setForm(blank);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const females = people.filter((p) => p.sex === "female");
  const males = people.filter((p) => p.sex === "male");
  const opposite = people.filter((p) => p.sex !== form.sex);
  const sex = mode === "add" ? form.sex : target?.sex;

  return (
    <details className="rounded-2xl border border-line bg-surface p-4 sm:p-6">
      <summary className="cursor-pointer text-lg font-semibold">{t("edit.title")}</summary>
      <div role="tablist" className="mt-4 inline-flex rounded-lg border border-line-strong p-0.5 text-sm">
        {(["add", "update"] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => {
              setMode(m);
              setSaved(false);
              if (m === "update") loadTarget(targetId);
              else setForm(blank);
            }}
            className={cx("min-h-9 rounded-md px-3", mode === m && "bg-accent-soft font-semibold")}
          >
            {t(m === "add" ? "edit.add" : "edit.update")}
          </button>
        ))}
      </div>
      <form onSubmit={save} className="mt-4 grid gap-4 sm:grid-cols-2">
        {mode === "update" && (
          <Field label={t("edit.person")} htmlFor="ed-target">
            <select id="ed-target" className={inputCls} value={targetId} onChange={(e) => loadTarget(e.target.value)}>
              {people.map((p) => (
                <option key={p.id} value={p.id}>{p.name || p.id}</option>
              ))}
            </select>
          </Field>
        )}
        <Field label={t("edit.name")} htmlFor="ed-name">
          <input id="ed-name" className={inputCls} value={form.name} maxLength={60} required={mode === "add"} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        {mode === "add" && (
          <>
            <Field label={t("edit.sex")} htmlFor="ed-sex">
              <select id="ed-sex" className={inputCls} value={form.sex} onChange={(e) => setForm({ ...form, sex: e.target.value as "male" | "female", partner: "" })}>
                <option value="female">{t("tree.female")}</option>
                <option value="male">{t("tree.male")}</option>
              </select>
            </Field>
            <Field label={t("edit.mother")} htmlFor="ed-mother">
              <select id="ed-mother" className={inputCls} value={form.mother} onChange={(e) => setForm({ ...form, mother: e.target.value })}>
                <option value="">{t("common.none")}</option>
                {females.map((p) => <option key={p.id} value={p.id}>{p.name || p.id}</option>)}
              </select>
            </Field>
            <Field label={t("edit.father")} htmlFor="ed-father">
              <select id="ed-father" className={inputCls} value={form.father} onChange={(e) => setForm({ ...form, father: e.target.value })}>
                <option value="">{t("common.none")}</option>
                {males.map((p) => <option key={p.id} value={p.id}>{p.name || p.id}</option>)}
              </select>
            </Field>
            <Field label={t("edit.partner")} htmlFor="ed-partner">
              <select id="ed-partner" className={inputCls} value={form.partner} onChange={(e) => setForm({ ...form, partner: e.target.value })}>
                <option value="">{t("common.none")}</option>
                {opposite.map((p) => <option key={p.id} value={p.id}>{p.name || p.id}</option>)}
              </select>
            </Field>
          </>
        )}
        <Field label={t("edit.status")} htmlFor="ed-status">
          <select id="ed-status" className={inputCls} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as PersonStatus })}>
            {(["unknown", "unaffected", "affected"] as const).map((s) => (
              <option key={s} value={s}>{t(`person.status.${s}`)}</option>
            ))}
          </select>
        </Field>
        {form.status === "affected" && (
          <Field label={t("edit.affectedWith")} htmlFor="ed-aw">
            <input id="ed-aw" className={inputCls} value={form.affected_with} maxLength={80} required onChange={(e) => setForm({ ...form, affected_with: e.target.value })} />
          </Field>
        )}
        <div className="flex flex-wrap items-center gap-5 sm:col-span-2">
          {sex === "female" && (
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="h-5 w-5 accent-[var(--accent)]" checked={form.pregnant} onChange={(e) => setForm({ ...form, pregnant: e.target.checked })} />
              {t("edit.pregnant")}
            </label>
          )}
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="h-5 w-5 accent-[var(--accent)]" checked={form.deceased} onChange={(e) => setForm({ ...form, deceased: e.target.checked })} />
            {t("edit.deceased")}
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <Button type="submit" variant="primary" disabled={busy}>
            {t(mode === "add" ? "edit.saveAdd" : "edit.saveUpdate")}
          </Button>
          {saved && <span role="status" className="text-sm text-ink-2">{t("edit.saved")}</span>}
        </div>
        {error ? <div className="sm:col-span-2"><ErrorBox error={error} /></div> : null}
      </form>
    </details>
  );
}

export function SectionTitle({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <div className="mb-4">
      <H2 id={id}>{children}</H2>
      <div className="rule-dots mt-2 w-24" aria-hidden="true" />
    </div>
  );
}
