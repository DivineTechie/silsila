"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { CaseDetail, Channel, InviteSuggestion, Part } from "@/lib/types";
import { Parts } from "./Parts";
import { StatusChip } from "./case";
import { Button, Chip, ErrorBox, Field, H3, Notice, Prov, cx, inputCls } from "./ui";

const TERMINAL = new Set(["withdrawn", "declined_by_relative", "no_response", "closed"]);
const CHANNELS: Channel[] = ["self_share_letter", "clinic_contact", "anonymous_invite"];

export function InformFlow({
  detail,
  onCreated,
  goToPermissions,
}: {
  detail: CaseDetail;
  onCreated: () => void;
  goToPermissions: () => void;
}) {
  const { t, lang } = usePrefs();
  const { case: c, report } = detail;
  const inviteOk = !!c.consents?.invite?.granted && !c.consents?.invite?.withdrawn_at;
  const name = (id: string | null) => c.pedigree.people.find((p) => p.id === id)?.name || id || "";

  const [step, setStep] = useState(0);
  const [pick, setPick] = useState<InviteSuggestion | null>(null);
  const [channel, setChannel] = useState<Channel>("anonymous_invite");
  const [discloseCondition, setDiscloseCondition] = useState(false);
  const [discloseSender, setDiscloseSender] = useState(false);
  const [senderName, setSenderName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [declined, setDeclined] = useState<Record<string, Part[]>>({});
  const [confirmDecline, setConfirmDecline] = useState<string | null>(null);
  const [created, setCreated] = useState(false);

  const steps = ["inform.step.relative", "inform.step.channel", "inform.step.disclosure", "inform.step.preview"] as const;
  const openFor = (pid: string) => detail.invitations.find((i) => i.person_id === pid && !TERMINAL.has(i.status));

  if (report.status !== "ok") {
    return <Parts parts={report.message} />;
  }
  if (!inviteOk) {
    return (
      <Notice>
        <p>{t("inform.needPermission")}</p>
        <Button size="sm" className="mt-3" onClick={goToPermissions}>
          {t("family.permissions")}
        </Button>
      </Notice>
    );
  }

  async function decline(pid: string) {
    setError(null);
    try {
      const r = await api<{ message: Part[] }>(`/api/cases/${c.id}/decline`, {
        method: "POST",
        query: { person_id: pid, lang },
      });
      setDeclined((d) => ({ ...d, [pid]: r.message }));
    } catch (e) {
      setError(e);
    } finally {
      setConfirmDecline(null);
    }
  }

  async function submit() {
    if (!pick) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/cases/${c.id}/invitations`, {
        body: {
          person_id: pick.person_id,
          channel,
          disclose_condition: discloseCondition,
          disclose_sender: discloseSender,
          sender_name: discloseSender ? senderName.trim() : null,
        },
      });
      setCreated(true);
      setStep(0);
      setPick(null);
      onCreated();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const wording = discloseSender
    ? ["invite.with_sender"]
    : discloseCondition
      ? ["invite.with_condition"]
      : ["invite.anonymous", "invite.anonymity_notice"];

  const coupleChance = (s: InviteSuggestion) => {
    if (!s.partner_id) return null;
    const cp = report.couples?.find(
      (x) => (x.female === s.person_id && x.male === s.partner_id) || (x.male === s.person_id && x.female === s.partner_id),
    );
    const v = cp?.sentence?.[0]?.params?.chance;
    return typeof v === "string" ? v : null;
  };

  return (
    <div>
      {created && (
        <Notice className="mb-4" role="status">
          {t("inform.created")}
        </Notice>
      )}
      <ol className="mb-5 flex flex-wrap gap-x-1 gap-y-2 text-sm" aria-label={t("family.inform")}>
        {steps.map((k, i) => (
          <li key={k} className="flex items-center gap-1" aria-current={i === step ? "step" : undefined}>
            <span
              className={cx(
                "grid h-6 w-6 place-items-center rounded-full text-xs font-semibold",
                i < step ? "bg-accent text-accent-ink" : i === step ? "border-2 border-accent text-accent" : "border border-line-strong text-muted",
              )}
            >
              {i + 1}
            </span>
            <span className={cx(i === step ? "font-semibold text-ink" : "text-muted")}>{t(k)}</span>
            {i < steps.length - 1 && <span aria-hidden="true" className="mx-1 h-px w-4 bg-line-strong" />}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <fieldset>
          <legend className="text-base font-semibold">{t("inform.pick")}</legend>
          <p className="mt-1 text-sm text-muted">{t("inform.pickHint")}</p>
          {(report.invites || []).length === 0 && <p className="mt-4 text-sm text-muted">{t("inform.noSuggestions")}</p>}
          <ul className="mt-4 grid gap-3">
            {(report.invites || []).map((s) => {
              const open = openFor(s.person_id);
              const pr = report.people?.[s.person_id];
              const cc = coupleChance(s);
              const selected = pick?.person_id === s.person_id;
              return (
                <li key={s.person_id} className={cx("rounded-xl border bg-surface p-4", selected ? "border-accent ring-2 ring-accent-soft" : "border-line")}>
                  <label className={cx("flex gap-3", open ? "cursor-not-allowed" : "cursor-pointer")}>
                    <input
                      type="radio"
                      name="relative"
                      className="mt-1 h-5 w-5 shrink-0 accent-[var(--accent)]"
                      disabled={!!open || !!declined[s.person_id]}
                      checked={selected}
                      onChange={() => setPick(s)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold">{name(s.person_id)}</span>
                        <Chip>{t(`reason.${s.reason_code}`)}</Chip>
                        <span className="text-xs text-muted">{t("inform.rank", { n: s.rank })}</span>
                      </span>
                      {s.partner_id && <span className="mt-1 block text-sm text-ink-2">{t("inform.partner", { name: name(s.partner_id) })}</span>}
                      <span className="mt-2 grid gap-1 text-sm">
                        {pr && (
                          <span className="flex flex-wrap items-center gap-2">
                            <Prov kind="calculated" />
                            <span className="text-muted">{t("inform.chancePerson")}:</span>
                            <span dir="ltr" className="font-medium">{pr.computed.chance_text}</span>
                          </span>
                        )}
                        {cc && (
                          <span className="flex flex-wrap items-center gap-2">
                            <Prov kind="calculated" />
                            <span className="text-muted">{t("inform.chanceChild")}:</span>
                            <span dir="ltr" className="font-medium">{cc}</span>
                          </span>
                        )}
                      </span>
                      {open && (
                        <span className="mt-2 flex items-center gap-2 text-sm text-ink-2">
                          {t("inform.open", { status: "" })}
                          <StatusChip status={open.status} />
                        </span>
                      )}
                    </span>
                  </label>
                  {declined[s.person_id] ? (
                    <Parts parts={declined[s.person_id]} className="mt-3" compact />
                  ) : (
                    !open && (
                      <div className="mt-3 border-t border-line pt-3">
                        {confirmDecline === s.person_id ? (
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <span>{t("inform.dontInformQ", { name: name(s.person_id) })}</span>
                            <Button size="sm" onClick={() => decline(s.person_id)}>
                              {t("common.confirm")}
                            </Button>
                            <Button size="sm" variant="quiet" onClick={() => setConfirmDecline(null)}>
                              {t("common.cancel")}
                            </Button>
                          </div>
                        ) : (
                          <Button size="sm" variant="quiet" onClick={() => setConfirmDecline(s.person_id)}>
                            {t("inform.dontInform")}
                          </Button>
                        )}
                      </div>
                    )
                  )}
                </li>
              );
            })}
          </ul>
        </fieldset>
      )}

      {step === 1 && (
        <fieldset>
          <legend className="text-base font-semibold">{t("inform.channel")}</legend>
          <div className="mt-4 grid gap-3">
            {CHANNELS.map((ch) => (
              <label
                key={ch}
                className={cx(
                  "flex cursor-pointer gap-3 rounded-xl border bg-surface p-4",
                  channel === ch ? "border-accent ring-2 ring-accent-soft" : "border-line",
                )}
              >
                <input
                  type="radio"
                  name="channel"
                  className="mt-1 h-5 w-5 shrink-0 accent-[var(--accent)]"
                  checked={channel === ch}
                  onChange={() => setChannel(ch)}
                />
                <span>
                  <span className="block font-semibold">{t(`channel.${ch}`)}</span>
                  <span className="mt-0.5 block text-sm text-ink-2">{t(`channel.${ch}.d`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      {step === 2 && (
        <fieldset>
          <legend className="text-base font-semibold">{t("inform.disclosure")}</legend>
          <div className="mt-4 grid gap-3">
            <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
              <input
                type="checkbox"
                className="h-5 w-5 accent-[var(--accent)]"
                checked={discloseCondition}
                onChange={(e) => setDiscloseCondition(e.target.checked)}
              />
              <span>
                {t("inform.nameCondition")}
                {report.locus && <span className="block text-sm text-muted">{report.locus.display}</span>}
              </span>
            </label>
            <label className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3">
              <input
                type="checkbox"
                className="h-5 w-5 accent-[var(--accent)]"
                checked={discloseSender}
                onChange={(e) => setDiscloseSender(e.target.checked)}
              />
              <span>{t("inform.nameMyself")}</span>
            </label>
            {discloseSender && (
              <Field label={t("inform.senderName")} htmlFor="sender-name">
                <input
                  id="sender-name"
                  className={inputCls}
                  maxLength={60}
                  value={senderName}
                  onChange={(e) => setSenderName(e.target.value)}
                  required
                />
              </Field>
            )}
          </div>
        </fieldset>
      )}

      {step === 3 && pick && (
        <div>
          <H3>{t("inform.preview")}</H3>
          <dl className="mt-4 grid gap-2 rounded-xl border border-line bg-surface p-4 text-sm">
            {[
              [t("inform.to"), name(pick.person_id)],
              [t("inform.via"), t(`channel.${channel}`)],
              [t("inform.condition"), discloseCondition ? `${t("common.yes")} · ${report.locus?.display || ""}` : t("common.no")],
              [t("inform.sender"), discloseSender ? `${t("common.yes")} · ${senderName}` : t("common.no")],
            ].map(([k, v]) => (
              <div key={k} className="grid gap-x-3 sm:grid-cols-[8rem_1fr]">
                <dt className="text-muted">{k}</dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
            <div className="grid gap-x-3 sm:grid-cols-[8rem_1fr]">
              <dt className="text-muted">{t("inform.previewWording")}</dt>
              <dd className="flex flex-wrap gap-2">
                {wording.map((w) => (
                  <span key={w} className="inline-flex min-w-0 flex-wrap items-center gap-1.5">
                    <Prov kind="template" />
                    <code className="break-all text-xs">{w}</code>
                  </span>
                ))}
              </dd>
            </div>
          </dl>
          <Parts parts={detail.consent_text.invite} className="mt-4" compact />
          <p className="mt-3 text-sm text-ink-2">{t("inform.previewNote")}</p>
        </div>
      )}

      {error ? <div className="mt-4"><ErrorBox error={error} /></div> : null}

      <div className="mt-6 flex flex-wrap gap-3">
        {step > 0 && (
          <Button onClick={() => setStep(step - 1)} disabled={busy}>
            {t("common.back")}
          </Button>
        )}
        {step < 3 && (
          <Button
            variant="primary"
            disabled={(step === 0 && !pick) || (step === 2 && discloseSender && !senderName.trim())}
            onClick={() => {
              setCreated(false);
              setStep(step + 1);
            }}
          >
            {t("common.continue")}
          </Button>
        )}
        {step === 3 && (
          <Button variant="primary" onClick={submit} disabled={busy}>
            {t("inform.submit")}
          </Button>
        )}
      </div>
    </div>
  );
}
