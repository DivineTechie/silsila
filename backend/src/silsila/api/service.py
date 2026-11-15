"""Case logic: family trees, risk reports, consent, invitations and the
counsellor queue. All person-facing wording goes through silsila.content."""

from __future__ import annotations

import copy

import datetime as dt
import secrets
from typing import Any

from .. import params
from ..content import Message, registry
from ..engine import (
    InconsistentEvidence,
    Pedigree,
    PedigreeTooComplex,
    PedigreeError,
    Person,
    Phenotype,
    Sex,
    TestResult,
    Union,
    family_report,
    one_in,
)
from .store import Store, new_id, now

ENGINE_VERSION = "silsila-engine 0.1 (exact variable elimination)"

# Service targets used to flag overdue steps. These are pilot assumptions to be
# agreed with the programme, not published standards (docs/limitations.md).
SERVICE_TARGETS_DAYS = {"awaiting_counsellor": 2, "sent": 30, "opened": 30, "understood": 30, "booked": 21}

INVITE_FLOW = {
    "awaiting_counsellor": {"approved", "withdrawn"},
    "approved": {"sent", "withdrawn"},
    "sent": {"opened", "tested", "declined_by_relative", "no_response"},
    "opened": {"understood", "booked", "tested", "declined_by_relative", "no_response"},
    "understood": {"booked", "tested", "declined_by_relative", "no_response"},
    "booked": {"tested", "declined_by_relative"},
    "tested": {"closed"},
}
TERMINAL = {"withdrawn", "declined_by_relative", "no_response", "closed"}
CHANNELS = {"self_share_letter", "clinic_contact", "anonymous_invite"}


class Forbidden(PermissionError):
    pass


class Invalid(ValueError):
    pass


# --------------------------------------------------------------- pedigree --
def to_engine(case: dict[str, Any]) -> Pedigree:
    ped = case["pedigree"]
    people = []
    for p in ped["people"]:
        status = p.get("status", "unknown")
        phenotype = None
        if status == "affected":
            phenotype = Phenotype(p.get("affected_with"))
            if phenotype.affected_with is None:
                raise Invalid(f"{p.get('name') or p['id']}: choose which condition the person is affected by")
        elif status == "unaffected":
            phenotype = Phenotype(None)
        test = TestResult(tuple(p["test"]["detected"])) if p.get("test") else None
        people.append(Person(p["id"], Sex(p["sex"]), p.get("mother"), p.get("father"), p.get("name"),
                             phenotype, test, bool(p.get("pregnant")), bool(p.get("deceased"))))
    try:
        return Pedigree.from_people(people, [Union(u["a"], u["b"]) for u in ped.get("unions", [])])
    except PedigreeError as e:
        raise Invalid(str(e)) from e


def _name(case: dict[str, Any], pid: str) -> str:
    for p in case["pedigree"]["people"]:
        if p["id"] == pid:
            return p.get("name") or pid
    return pid


def compute_report(case: dict[str, Any], lang: str = "en") -> dict[str, Any]:
    """Run the engine and return numbers plus approved sentences.

    Every value is labelled 'recorded' (entered by a person or a lab) or
    'computed' (engine output), and every sentence carries its template id."""
    reg = registry()
    loci = params.load()
    out: dict[str, Any] = {"engine": ENGINE_VERSION, "computed_at": now(), "locus_id": case["locus_id"], "lang": lang}
    if case["locus_id"] not in loci:
        excluded = {e["id"]: e for e in params.register().get("excluded_loci", [])}
        e = excluded.get(case["locus_id"])
        msg = reg.template(Message(lang), "result.excluded_locus",
                           {"condition": params.display_for(e, lang) if e else case["locus_id"]})
        out.update(status="not_calculated", message=reg.gate(msg).parts, reason=e["reason"] if e else None)
        return out
    rec = loci[case["locus_id"]]
    out["locus"] = {
        "display": rec.display, "gene": rec.locus.gene, "background_f": rec.background_f,
        "alleles": [{"id": a.id, "label": a.label, "frequency": a.frequency, "detection_rate": a.detection_rate,
                     "pathogenic": a.pathogenic} for a in rec.locus.alleles],
        "derivations": [d.__dict__ for d in rec.derivations],
        "sources": [{"allele": a["id"], **a["source"]} for a in rec.raw["alleles"]],
        "detection_sources": [{"allele": a["id"], **(a.get("detection_source") or {"note": a.get("detection_note")})}
                              for a in rec.raw["alleles"]],
        "content_ids": rec.content_ids, "limitations": rec.raw.get("known_limitations", []),
    }
    try:
        ped = to_engine(case)
        rep = family_report(ped, rec.locus, rec.background_f)
    except InconsistentEvidence:
        msg = reg.template(Message(lang), "result.inconsistent")
        out.update(status="inconsistent", message=reg.gate(msg).parts)
        return out
    except PedigreeTooComplex:
        msg = reg.template(Message(lang), "result.too_complex")
        out.update(status="too_complex", message=reg.gate(msg).parts)
        return out

    gene = rec.locus.gene
    people = {}
    for pid, pr in rep.people.items():
        raw = next(p for p in case["pedigree"]["people"] if p["id"] == pid)
        sentence = None
        if pr.informative and pr.p_affected < 0.999:
            m = reg.template(Message(lang), "result.carrier_probability",
                             {"person": _name(case, pid), "gene": gene, "chance": one_in(pr.p_any_pathogenic, lang)})
            sentence = reg.gate(m).parts
        residual_note = None
        if raw.get("test") is not None and not raw["test"]["detected"] and not all(rec.residual_risk_modelled.values()):
            residual_note = reg.gate(reg.template(Message(lang), "result.residual_not_modelled")).parts
        people[pid] = {
            "recorded": {"status": raw.get("status", "unknown"), "affected_with": raw.get("affected_with"),
                         "test": raw.get("test"), "pregnant": bool(raw.get("pregnant")),
                         "deceased": bool(raw.get("deceased"))},
            "computed": {"p_carrier": pr.p_carrier, "p_affected": pr.p_affected, "p_any_variant": pr.p_any_pathogenic,
                         "chance_text": one_in(pr.p_any_pathogenic, lang), "genotypes": pr.genotype_posterior},
            "informative": pr.informative, "sentence": sentence, "residual_note": residual_note,
        }
    couples = []
    for c in rep.couples:
        affected = {k: v for k, v in c.child_phenotypes.items() if k in rec.locus.affected_phenotypes}
        m = reg.template(Message(lang), "result.couple_child_risk", {
            "a": _name(case, c.female), "b": _name(case, c.male), "condition": params.display_for(rec, lang),
            "chance": one_in(c.p_child_affected, lang), "baseline": one_in(c.baseline_child_affected, lang)})
        couples.append({"female": c.female, "male": c.male, "kinship": c.kinship,
                        "computed": {"p_both_carry": c.p_both_carry, "p_child_affected": c.p_child_affected,
                                     "child_affected_by_condition": affected,
                                     "baseline_child_affected": c.baseline_child_affected},
                        "sentence": reg.gate(m).parts})
    out.update(status="ok", people=people, couples=couples,
               invites=[{**s.__dict__} for s in rep.invites])
    return out


# ------------------------------------------------------------------- cases --
def localise(case: dict[str, Any], lang: str) -> dict[str, Any]:
    """Display copy of a case in the interface language: Arabic titles and names where they exist. The stored
    case is unchanged; `name_en` carries the stored name so a save from the Arabic view can restore it."""
    if lang != "ar":
        return case
    c = copy.deepcopy(case)
    if c.get("title_ar"):
        c["title"] = c["title_ar"]
    for p in c["pedigree"]["people"]:
        if p.get("name_ar"):
            p["name_en"] = p.get("name")
            p["name"] = p["name_ar"]
    return c


def delocalise_pedigree(pedigree: dict[str, Any]) -> dict[str, Any]:
    """Undo `localise` on a tree sent back from the Arabic view. An edited Arabic name becomes the new
    Arabic name; the stored (English) name is kept."""
    for p in pedigree.get("people", []):
        en = p.pop("name_en", None)
        if en is not None:
            if p.get("name") != p.get("name_ar"):
                p["name_ar"] = p.get("name")
            p["name"] = en
    return pedigree


def visible_case(store: Store, user: dict[str, Any], case_id: str) -> dict[str, Any]:
    case = store.get("case", case_id)
    if case is None:
        raise Invalid("Case not found")
    if user["role"] == "counsellor" or (user["role"] == "family" and case.get("family_user_id") == user["id"]):
        return case
    store.audit(user["id"], user["role"], "case.read", case_id=case_id, outcome="denied")
    raise Forbidden("You do not have access to this case")


def require_consent(case: dict[str, Any], scope: str) -> None:
    c = case.get("consents", {}).get(scope)
    if not c or not c.get("granted") or c.get("withdrawn_at"):
        raise Forbidden(f"Permission '{scope}' has not been given")


def set_consent(store: Store, user: dict[str, Any], case: dict[str, Any], scope: str, granted: bool) -> dict[str, Any]:
    if scope not in ("compute", "invite"):
        raise Invalid("Unknown permission")
    if user["role"] != "family" or case.get("family_user_id") != user["id"]:
        raise Forbidden("Only the family member who owns this case can give or withdraw permission")
    consents = case.setdefault("consents", {})
    if granted:
        consents[scope] = {"granted": True, "granted_at": now(), "withdrawn_at": None, "by": user["id"],
                           "wording_template": f"consent.{scope}"}
    else:
        consents.setdefault(scope, {"granted": False})["withdrawn_at"] = now()
        consents[scope]["granted"] = False
    store.put("case", case)
    store.audit(user["id"], user["role"], f"consent.{'grant' if granted else 'withdraw'}", case_id=case["id"],
                entity=scope)
    return case


def update_pedigree(store: Store, user: dict[str, Any], case: dict[str, Any], pedigree: dict[str, Any]) -> dict[str, Any]:
    trial = {**case, "pedigree": pedigree}
    to_engine(trial)  # validates; raises Invalid with a clear message
    case["pedigree"] = pedigree
    store.put("case", case)
    store.audit(user["id"], user["role"], "pedigree.update", case_id=case["id"],
                detail={"people": len(pedigree["people"]), "unions": len(pedigree.get("unions", []))})
    return case


# ------------------------------------------------------------- invitations --
def create_invitation(store: Store, user: dict[str, Any], case: dict[str, Any], person_id: str, channel: str,
                      disclose_condition: bool, disclose_sender: bool, sender_name: str | None) -> dict[str, Any]:
    if user["role"] != "family" or case.get("family_user_id") != user["id"]:
        raise Forbidden("Only the family member who owns this case decides who is told")
    require_consent(case, "invite")
    if channel not in CHANNELS:
        raise Invalid("Unknown way of telling a relative")
    if not any(p["id"] == person_id for p in case["pedigree"]["people"]):
        raise Invalid("That person is not in the family tree")
    if disclose_sender and not sender_name:
        raise Invalid("Give the name you want the relative to see, or choose not to share it")
    open_inv = [i for i in store.list("invitation", case["id"]) if i["person_id"] == person_id and i["status"] not in TERMINAL]
    if open_inv:
        raise Invalid("There is already an open invitation for this relative")
    inv = {"id": new_id("inv"), "case_id": case["id"], "person_id": person_id, "person_name": _name(case, person_id),
           "channel": channel, "disclose_condition": disclose_condition, "disclose_sender": disclose_sender,
           "sender_name": sender_name if disclose_sender else None, "status": "awaiting_counsellor",
           "code": secrets.token_urlsafe(16), "history": [{"status": "awaiting_counsellor", "at": now(), "by": user["id"]}],
           "owner": "counsellor", "teachback": None, "closure_evidence": None}
    store.put("invitation", inv)
    store.audit(user["id"], user["role"], "invitation.create", case_id=case["id"], entity=inv["id"],
                detail={"channel": channel, "disclose_condition": disclose_condition, "disclose_sender": disclose_sender})
    return inv


def transition(store: Store, actor: dict[str, Any], inv: dict[str, Any], new: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    allowed = INVITE_FLOW.get(inv["status"], set())
    if new not in allowed:
        raise Invalid(f"Cannot move an invitation from '{inv['status']}' to '{new}'")
    if new == "approved" and actor["role"] != "counsellor":
        raise Forbidden("Only a genetic counsellor can approve an invitation")
    if new == "closed" and not (detail and detail.get("evidence")):
        raise Invalid("An invitation can only be closed with evidence attached (for example a test result)")
    inv["status"] = new
    inv["history"].append({"status": new, "at": now(), "by": actor["id"], **(detail or {})})
    if new == "closed":
        inv["closure_evidence"] = detail["evidence"]  # type: ignore[index]
    store.put("invitation", inv)
    store.audit(actor["id"], actor["role"], f"invitation.{new}", case_id=inv["case_id"], entity=inv["id"],
                detail={k: v for k, v in (detail or {}).items() if k != "evidence"})
    return inv


def record_test_result(store: Store, counsellor: dict[str, Any], inv: dict[str, Any], detected: list[str]) -> dict[str, Any]:
    if counsellor["role"] != "counsellor":
        raise Forbidden("Only the counselling team records results")
    case = store.get("case", inv["case_id"])
    assert case is not None
    for p in case["pedigree"]["people"]:
        if p["id"] == inv["person_id"]:
            p["test"] = {"detected": detected, "recorded_at": now(), "recorded_by": counsellor["id"]}
    case_trial = dict(case)
    compute = compute_report(case_trial)
    store.put("case", case)
    transition(store, counsellor, inv, "tested", {"detected": detected})
    transition(store, counsellor, inv, "closed", {"evidence": {"type": "test_result", "detected": detected,
                                                               "engine_status": compute["status"]}})
    return inv


def relative_view(store: Store, code: str, lang: str) -> dict[str, Any]:
    """What a relative sees from an invitation link. Contains only what the
    index person chose to disclose."""
    reg = registry()
    inv = next((i for i in store.list("invitation") if i["code"] == code), None)
    if inv is None or inv["status"] in ("awaiting_counsellor", "approved", "withdrawn"):
        store.audit("anonymous", "relative", "invitation.open", outcome="denied", detail={"reason": "unknown or unsent code"})
        raise Forbidden("This link is not valid")
    case = store.get("case", inv["case_id"])
    assert case is not None
    rec = params.load().get(case["locus_id"])
    display = params.display_for(rec, lang) if rec else case["locus_id"]
    msg = Message(lang)
    if inv["disclose_sender"]:
        reg.template(msg, "invite.with_sender", {"sender": inv["sender_name"]})
    elif inv["disclose_condition"]:
        reg.template(msg, "invite.with_condition", {"condition": display})
    else:
        reg.template(msg, "invite.anonymous")
        reg.template(msg, "invite.anonymity_notice")
    info = Message(lang)
    reg.quote(info, "mp:inheritance-patterns:0:3")
    reg.quote(info, "mp:risk-assessment:0:2")
    if inv["disclose_condition"] and rec:
        for cid in rec.content_ids:
            for p in reg.condition_paragraphs(cid, ("Description",))[:2]:
                reg.quote(info, p.id)
    if inv["status"] == "sent":
        inv["relative_lang"] = lang  # for equity reporting by language; no other detail about the relative
        transition(store, {"id": f"relative:{inv['id']}", "role": "relative"}, inv, "opened")
    return {"invitation_id": inv["id"], "status": inv["status"], "message": reg.gate(msg).parts,
            "information": reg.gate(info).parts,
            # Common questions the relative can open; each answer is quoted text (see relative_topic).
            "topics": [{k: t[k] for k in ("id", "title_en", "title_ar")} for t in reg.faq],
            "teachback": [{k: v for k, v in q.items() if k != "options"} | {
                "options": [{"id": o["id"], "en": o["en"], "ar": o["ar"]} for o in q["options"]]} for q in reg.teachback],
            "consent_note": reg.gate(reg.template(Message(lang), "reply.booking")).parts}


def relative_topic(store: Store, code: str, topic_id: str, lang: str) -> dict[str, Any]:
    """A common question opened from an invitation link. The answer is the approved "here is information"
    wording followed by verbatim MedlinePlus paragraphs, through the output gate. Nothing is recommended:
    the reproductive-options topic describes carrier, prenatal and preimplantation testing in the source's
    words and leaves the decision with the reader."""
    reg = registry()
    inv = next((i for i in store.list("invitation") if i["code"] == code), None)
    if inv is None or inv["status"] in ("awaiting_counsellor", "approved", "withdrawn"):
        store.audit("anonymous", "relative", "information.read", outcome="denied", detail={"reason": "unknown or unsent code"})
        raise Forbidden("This link is not valid")
    topic = next((t for t in reg.faq if t["id"] == topic_id), None)
    if topic is None:
        raise Invalid("Unknown topic")
    msg = reg.template(Message(lang), "reply.information")
    for pid in topic["paragraphs"]:
        reg.quote(msg, pid)
    reg.gate(msg)
    store.audit(f"relative:{inv['id']}", "relative", "information.read", case_id=inv["case_id"], entity=inv["id"],
                detail={"topic": topic_id, "lang": lang, "digest": msg.digest})
    return {"id": topic["id"], "title_en": topic["title_en"], "title_ar": topic["title_ar"], "parts": msg.parts}


def score_teachback(answers: dict[str, str]) -> dict[str, Any]:
    reg = registry()
    results = {}
    for q in reg.teachback:
        correct = next(o["id"] for o in q["options"] if o["correct"])
        results[q["id"]] = {"answer": answers.get(q["id"]), "correct": answers.get(q["id"]) == correct,
                            "evidence": q["evidence"]}
    n = sum(r["correct"] for r in results.values())
    return {"score": n, "total": len(results), "passed": n == len(results), "items": results}


# ------------------------------------------------------------------- queue --
def _days_since(ts: str) -> float:
    return (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ts)).total_seconds() / 86400


def queue(store: Store) -> list[dict[str, Any]]:
    """Counsellor work queue. Order: crisis messages, pregnancy-related items,
    other escalations and inconsistent families, overdue steps, then approvals.
    Each item states why it is in the queue."""
    items: list[dict[str, Any]] = []
    cases = {c["id"]: c for c in store.list("case")}
    pregnant_cases = {cid for cid, c in cases.items() if any(p.get("pregnant") for p in c["pedigree"]["people"])}
    for m in store.list("message"):
        # Every message is queued for a person to read; triage only sets the order.
        if not m.get("resolved"):
            if "crisis" in m["labels"]:
                prio = 0
            elif m.get("escalate"):
                prio = 1 if m.get("case_id") in pregnant_cases else 2
            else:
                prio = 5
            items.append({"type": "message", "id": m["id"], "case_id": m.get("case_id"), "priority": prio,
                          "reasons": sorted(m["labels"]) or ["unclassified"], "since": m["created"]})
    for cid, c in cases.items():
        rep = compute_report(c)
        if rep["status"] in ("inconsistent", "too_complex"):
            reason = "results_do_not_fit" if rep["status"] == "inconsistent" else "family_tree_too_complex"
            items.append({"type": "case", "id": cid, "case_id": cid, "priority": 2, "reasons": [reason],
                          "since": c["updated"]})
    for inv in store.list("invitation"):
        if inv["status"] in TERMINAL:
            continue
        last = inv["history"][-1]["at"]
        target = SERVICE_TARGETS_DAYS.get(inv["status"])
        overdue = target is not None and _days_since(last) > target
        reasons = []
        if inv["case_id"] in pregnant_cases:
            reasons.append("pregnancy_in_family")
        if overdue:
            reasons.append("overdue")
        if inv["status"] == "awaiting_counsellor":
            reasons.append("needs_approval")
        if reasons:
            prio = 1 if "pregnancy_in_family" in reasons else (3 if overdue else 4)
            items.append({"type": "invitation", "id": inv["id"], "case_id": inv["case_id"], "priority": prio,
                          "reasons": reasons, "status": inv["status"], "since": last})
    items.sort(key=lambda i: (i["priority"], i["since"]))
    return items


# ---------------------------------------------------------------- outcomes --
def _hours(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    t0, t1 = dt.datetime.fromisoformat(a), dt.datetime.fromisoformat(b)
    return max(0.0, (t1 - t0).total_seconds() / 3600)


def _median(xs: list[float]) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


FUNNEL = ("awaiting_counsellor", "sent", "opened", "understood", "booked", "tested", "closed")


def outcomes(store: Store) -> dict[str, Any]:
    """The challenge statement's measures, computed from what the system recorded: comprehension, uptake,
    time to counselling, privacy and equity across languages. Never marriages or reproductive choices."""
    invs = store.list("invitation")
    cases = {c["id"]: c for c in store.list("case")}

    def reached(inv: dict[str, Any], status: str) -> bool:
        return any(h["status"] == status for h in inv["history"])

    def first_at(inv: dict[str, Any], status: str) -> str | None:
        return next((h["at"] for h in inv["history"] if h["status"] == status), None)

    funnel = {s: sum(reached(i, s) for i in invs) for s in FUNNEL}
    ended = {s: sum(i["status"] == s for i in invs) for s in ("declined_by_relative", "no_response", "withdrawn")}
    tb = [i for i in invs if i.get("teachback")]
    by_lang: dict[str, dict[str, Any]] = {}
    for i in invs:
        lang = i.get("relative_lang")
        if not lang:
            continue
        row = by_lang.setdefault(lang, {"opened": 0, "teachback": 0, "understood": 0, "booked_or_tested": 0})
        row["opened"] += 1
        if i.get("teachback"):
            row["teachback"] += 1
            row["understood"] += bool(i["teachback"].get("passed"))
        row["booked_or_tested"] += reached(i, "booked") or reached(i, "tested")
    first_sent: dict[str, str] = {}
    for i in invs:
        at = first_at(i, "sent")
        if at and (i["case_id"] not in first_sent or at < first_sent[i["case_id"]]):
            first_sent[i["case_id"]] = at
    events = store.audit_events(limit=100000)
    msgs = store.list("message")
    return {
        "invitations": len(invs),
        "funnel": funnel,
        "ended": ended,
        "comprehension": {"submitted": len(tb), "passed": sum(bool(i["teachback"].get("passed")) for i in tb)},
        "uptake": {"opened": funnel["opened"], "booked_or_tested": sum(reached(i, "booked") or reached(i, "tested") for i in invs)},
        "hours": {
            "request_to_sent": _median([_hours(first_at(i, "awaiting_counsellor"), first_at(i, "sent")) for i in invs]),
            "sent_to_opened": _median([_hours(first_at(i, "sent"), first_at(i, "opened")) for i in invs]),
            "opened_to_booked": _median([_hours(first_at(i, "opened"), first_at(i, "booked")) for i in invs]),
            "case_to_first_invitation": _median([_hours(cases[c].get("created"), at) for c, at in first_sent.items()
                                                 if c in cases]),
        },
        "by_language": by_lang,
        "privacy": {
            "denied_requests": sum(e["outcome"] == "denied" for e in events),
            "blocked_outputs": sum(e["action"] == "output_gate.block" for e in events),
            "audit_chain": store.verify_chain(),
        },
        "messages": {
            "total": len(msgs),
            "escalated": sum(bool(m.get("escalate")) for m in msgs),
            "crisis": sum("crisis" in m.get("labels", []) for m in msgs),
            "by_language": {lang: sum(m.get("lang") == lang for m in msgs) for lang in ("en", "ar")},
        },
        "not_measured": "Marriages, cancelled engagements or any reproductive choice are never measured as success.",
    }
