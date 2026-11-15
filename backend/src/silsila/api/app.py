"""Silsila HTTP API (FastAPI). Run: uv run uvicorn silsila.api.app:app --reload"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import intake, params, twin
from ..content import GateError, Message, registry
from ..engine import Pedigree
from ..triage import classify, reply_for
from . import auth, fhir, service
from .store import Store, new_id, now

DEMO = os.environ.get("SILSILA_DEMO", "1") == "1"
EVIDENCE_DIR = Path(__file__).resolve().parents[4] / "docs" / "evidence"

app = FastAPI(title="Silsila API", version="0.1.0",
              description="Consent-led family cascade for inherited disease risk. No AI-written advice.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("SILSILA_CORS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
_store: Store | None = None
_store_lock = threading.Lock()


def store() -> Store:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = Store()
    return _store


@app.exception_handler(service.Forbidden)
async def _forbidden(_: Request, exc: service.Forbidden) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(service.Invalid)
async def _invalid(_: Request, exc: service.Invalid) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(GateError)
async def _gate(_: Request, exc: GateError) -> JSONResponse:
    store().audit("system", "system", "output_gate.block", outcome="blocked", detail={"reason": str(exc)})
    return JSONResponse({"detail": "Blocked by the output gate: " + str(exc)}, status_code=451)


def current_user(authorization: str = Header(default="")) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        store().audit("anonymous", "unknown", "auth.missing_token", outcome="denied")
        raise HTTPException(401, "Sign in first")
    try:
        claims = auth.decode(authorization[7:])
    except Exception:
        store().audit("anonymous", "unknown", "auth.invalid_token", outcome="denied")
        raise HTTPException(401, "Your session has expired; sign in again")
    user = store().get("user", claims["sub"])
    if user is None:
        raise HTTPException(401, "Unknown user")
    return user


def counsellor(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "counsellor":
        store().audit(user["id"], user["role"], "counsellor_area", outcome="denied")
        raise HTTPException(403, "This area is for the genetic counselling team")
    return user


# ------------------------------------------------------------------ models --
class Login(BaseModel):
    username: str
    password: str


class PedigreeIn(BaseModel):
    people: list[dict[str, Any]]
    unions: list[dict[str, str]] = []


class EngineRequest(BaseModel):
    locus_id: str
    pedigree: PedigreeIn
    lang: Literal["en", "ar"] = "en"


class ConsentIn(BaseModel):
    scope: Literal["compute", "invite"]
    granted: bool


class InvitationIn(BaseModel):
    person_id: str
    channel: Literal["self_share_letter", "clinic_contact", "anonymous_invite"]
    disclose_condition: bool = False
    disclose_sender: bool = False
    sender_name: str | None = Field(default=None, max_length=60)


class TransitionIn(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=500)


class ResultIn(BaseModel):
    detected: list[str] = []


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    lang: Literal["en", "ar"] = "en"
    case_id: str | None = None
    invite_code: str | None = None


class TeachbackIn(BaseModel):
    answers: dict[str, str]


class CaseIn(BaseModel):
    locus_id: str
    index_person_id: str
    index_source: Literal["newborn_screen", "premarital_at_risk", "diagnosed_child", "carrier_result"]
    family_user_id: str
    pedigree: PedigreeIn


# ------------------------------------------------------------------ basics --
@app.get("/api/health")
def health() -> dict[str, Any]:
    reg = registry()
    return {"ok": True, "demo_mode": DEMO, "paragraphs": len(reg.paragraphs), "templates": len(reg.templates),
            "loci": list(params.load()), "audit": store().verify_chain()}


@app.post("/api/auth/login")
def login(body: Login) -> dict[str, Any]:
    user = next(iter(store().find("user", username=body.username)), None)
    if user is None or not auth.check_password(body.password, user["password_hash"]):
        store().audit(body.username[:40], "unknown", "auth.login", outcome="denied")
        raise HTTPException(401, "Username or password is not correct")
    store().audit(user["id"], user["role"], "auth.login")
    return {"token": auth.issue(user), "user": {k: user[k] for k in ("id", "role", "display_name", "lang")}}


@app.get("/api/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {k: user[k] for k in ("id", "role", "display_name", "lang")}


# ---------------------------------------------------------------- content --
@app.get("/api/content/loci")
def loci() -> dict[str, Any]:
    reg_doc = params.register()
    return {"background_inbreeding": reg_doc["background_inbreeding"],
            "loci": [{"id": k, "display": r.display, "gene": r.locus.gene,
                      "alleles": [{"id": a.id, "label": a.label, "frequency": a.frequency, "detection_rate": a.detection_rate}
                                  for a in r.locus.alleles],
                      "phenotypes": r.raw["phenotypes"], "derivations": [d.__dict__ for d in r.derivations],
                      "sources": r.raw["alleles"], "limitations": r.raw.get("known_limitations", [])}
                     for k, r in params.load().items()],
            "excluded": reg_doc.get("excluded_loci", [])}


@app.get("/api/content/condition/{content_id}")
def condition(content_id: str, lang: Literal["en", "ar"] = "en") -> dict[str, Any]:
    reg = registry()
    if content_id not in reg.documents:
        raise HTTPException(404, "Unknown condition")
    doc = reg.documents[content_id]
    msg = Message(lang)
    for p in reg.condition_paragraphs(content_id, ("Description", "Frequency", "Causes", "Inheritance")):
        reg.quote(msg, p.id)
    return {"title": doc["title"], "url": doc["url"], "attribution": doc["attribution"], "licence": doc["licence"],
            "retrieved_at": doc["retrieved_at"], "reviewed": doc.get("medlineplus_reviewed"),
            "paragraphs": reg.gate(msg).parts, "translation_status": reg.template_meta["ar_status"] if lang == "ar" else None}


@app.get("/api/content/faq")
def faq() -> list[dict[str, Any]]:
    return [{k: t[k] for k in ("id", "title_en", "title_ar", "paragraphs")} for t in registry().faq]


# ----------------------------------------------------------------- engine --
@app.post("/api/engine/report")
def engine_report(body: EngineRequest) -> dict[str, Any]:
    """Stateless calculation for a family tree (no storage, no audit of content)."""
    case = {"locus_id": body.locus_id, "pedigree": body.pedigree.model_dump(), "id": "adhoc"}
    return service.compute_report(case, body.lang)


# ----------------------------------------------------------------- intake --
class DraftIn(BaseModel):
    locus_id: str = ""
    people: list[dict[str, Any]]
    unions: list[dict[str, Any]] = []


class IntakeAction(BaseModel):
    draft: DraftIn
    action: dict[str, Any]


class IntakeCompute(BaseModel):
    draft: DraftIn
    lang: Literal["en", "ar"] = "en"


def _intake_state(draft: dict[str, Any]) -> dict[str, Any]:
    issues = intake.review(draft)
    unconfirmed = sum(not p.get("confirmed") for p in draft["people"]) + sum(not u.get("confirmed") for u in draft["unions"])
    return {"draft": draft, "issues": issues, "unconfirmed": unconfirmed,
            "ready": unconfirmed == 0 and not any(i["severity"] == "block" for i in issues)}


@app.get("/api/intake/demo")
def intake_demo(user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    """The RECORDED voice-intake demo: synthetic voice, Jais-ASR transcript, Jais 3 draft, review."""
    store().audit(user["id"], user["role"], "intake.demo_open")
    demo = intake.load_demo()
    return {**demo, **_intake_state(demo["draft"])}


@app.get("/api/intake/demo/audio")
def intake_demo_audio(user: dict[str, Any] = Depends(counsellor)) -> FileResponse:
    return FileResponse(intake.demo_audio_path(), media_type="audio/wav")


@app.post("/api/intake/apply")
def intake_apply(body: IntakeAction, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    try:
        draft = intake.apply(body.draft.model_dump(), body.action)
    except intake.IntakeError as e:
        raise service.Invalid(str(e))
    store().audit(user["id"], user["role"], "intake.action", detail={"type": body.action.get("type")})
    return _intake_state(draft)


@app.post("/api/intake/compute")
def intake_compute(body: IntakeCompute, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    """Runs the exact engine on a fully confirmed draft. Refuses anything unconfirmed or blocked."""
    draft = body.draft.model_dump()
    try:
        ped = intake.ready_pedigree(draft)
    except intake.IntakeError as e:
        store().audit(user["id"], user["role"], "intake.compute", outcome="refused")
        raise service.Invalid(str(e))
    if draft["locus_id"] not in params.load():
        raise service.Invalid("Choose the condition (gene) before computing")
    store().audit(user["id"], user["role"], "intake.compute",
                  detail={"people": len(ped["people"]), "unions": len(ped["unions"]), "locus": draft["locus_id"]})
    case = {"locus_id": draft["locus_id"], "pedigree": ped, "id": "intake"}
    return {"pedigree": ped, "report": service.compute_report(case, body.lang)}


# --------------------------------------------------------------- contrast --
CONTRAST_FILE = Path(__file__).resolve().parents[4] / "data" / "demo" / "contrast" / "cah_noura_khalfan.json"


@app.get("/api/contrast")
def contrast() -> dict[str, Any]:
    """RECORDED answers from language models to the demo family's question, beside the engine's exact answer."""
    if not CONTRAST_FILE.exists():
        raise HTTPException(404, "No recorded contrast yet")
    return json.loads(CONTRAST_FILE.read_text())


# ------------------------------------------------------------------- twin --
class TwinWhatIf(BaseModel):
    # "carrier" (variant B), "clear", or the variants found, e.g. "S" or "B,B"
    results: dict[str, Annotated[str, Field(pattern=r"^(carrier|clear|[BS](,[BS])?)$")]] = Field(
        default_factory=dict, max_length=40)


@app.get("/api/twin")
def twin_clan() -> dict[str, Any]:
    """The Family Twin: a fictional simulated clan (no sign-in needed; no real person)."""
    return twin.public()


@app.post("/api/twin/what-if")
def twin_what_if(body: TwinWhatIf) -> dict[str, Any]:
    """Exact carrier chances for the whole clan after recording test results."""
    ids = {p["id"] for p in twin.public()["people"]}
    unknown = sorted(set(body.results) - ids)
    if unknown:
        raise service.Invalid(f"Not in the clan: {', '.join(unknown[:5])}")
    return twin.what_if(body.results)


# ------------------------------------------------------------------ cases --
@app.get("/api/cases")
def list_cases(lang: Literal["en", "ar"] = "en", user: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
    cases = [c for c in store().list("case") if not c.get("story")]
    if user["role"] != "counsellor":
        cases = [c for c in cases if c.get("family_user_id") == user["id"]]
    out = []
    for c in cases:
        invs = store().list("invitation", c["id"])
        title = c.get("title_ar") if lang == "ar" and c.get("title_ar") else c.get("title")
        out.append({"id": c["id"], "title": title, "locus_id": c["locus_id"], "index_source": c["index_source"],
                    "people": len(c["pedigree"]["people"]), "invitations": len(invs),
                    "open_invitations": sum(i["status"] not in service.TERMINAL for i in invs), "updated": c["updated"]})
    return out


@app.post("/api/cases")
def create_case(body: CaseIn, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    case = {"id": new_id("case"), "case_id": None, "locus_id": body.locus_id, "index_person_id": body.index_person_id,
            "index_source": body.index_source, "family_user_id": body.family_user_id,
            "pedigree": body.pedigree.model_dump(), "consents": {}}
    case["case_id"] = case["id"]
    service.to_engine(case)
    store().put("case", case)
    store().audit(user["id"], user["role"], "case.create", case_id=case["id"])
    return case


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, lang: Literal["en", "ar"] = "en", user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    case = service.localise(service.visible_case(store(), user, case_id), lang)
    store().audit(user["id"], user["role"], "case.read", case_id=case_id)
    report = service.compute_report(case, lang) if case.get("consents", {}).get("compute", {}).get("granted") else {
        "status": "awaiting_consent",
        "message": registry().gate(registry().template(Message(lang), "consent.compute")).parts}
    invs = store().list("invitation", case_id)
    if user["role"] != "counsellor":
        invs = [{k: v for k, v in i.items() if k != "code" or i["status"] not in ("awaiting_counsellor",)} for i in invs]
    return {"case": case, "report": report, "invitations": invs,
            "consent_text": {s: registry().gate(registry().template(Message(lang), f"consent.{s}")).parts
                             for s in ("compute", "invite")}}


@app.put("/api/cases/{case_id}/pedigree")
def put_pedigree(case_id: str, body: PedigreeIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    case = service.visible_case(store(), user, case_id)
    return service.update_pedigree(store(), user, case, service.delocalise_pedigree(body.model_dump()))


@app.post("/api/cases/{case_id}/consents")
def consent(case_id: str, body: ConsentIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    case = service.visible_case(store(), user, case_id)
    return service.set_consent(store(), user, case, body.scope, body.granted)["consents"]


@app.post("/api/cases/{case_id}/invitations")
def invite(case_id: str, body: InvitationIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    case = service.visible_case(store(), user, case_id)
    return service.create_invitation(store(), user, case, body.person_id, body.channel, body.disclose_condition,
                                     body.disclose_sender, body.sender_name)


@app.post("/api/cases/{case_id}/decline")
def decline(case_id: str, person_id: str, lang: Literal["en", "ar"] = "en",
            user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    case = service.visible_case(store(), user, case_id)
    if user["role"] != "family":
        raise HTTPException(403, "Only the family decides who is told")
    store().audit(user["id"], user["role"], "invitation.declined_by_index", case_id=case["id"], entity=person_id)
    return {"message": registry().gate(registry().template(Message(lang), "consent.decline_recorded")).parts}


@app.post("/api/invitations/{inv_id}/status")
def set_status(inv_id: str, body: TransitionIn, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    inv = store().get("invitation", inv_id)
    if inv is None:
        raise HTTPException(404, "Invitation not found")
    service.visible_case(store(), user, inv["case_id"])
    if user["role"] == "family" and body.status != "withdrawn":
        raise HTTPException(403, "Families can only withdraw an invitation before it is sent")
    return service.transition(store(), user, inv, body.status, {"note": body.note} if body.note else None)


@app.post("/api/invitations/{inv_id}/result")
def result(inv_id: str, body: ResultIn, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    inv = store().get("invitation", inv_id)
    if inv is None:
        raise HTTPException(404, "Invitation not found")
    return service.record_test_result(store(), user, inv, body.detected)


# --------------------------------------------------------------- relatives --
@app.get("/api/r/{code}")
def relative(code: str, lang: Literal["en", "ar"] = "en") -> dict[str, Any]:
    return service.relative_view(store(), code, lang)


@app.get("/api/r/{code}/topics/{topic_id}")
def relative_topic(code: str, topic_id: str, lang: Literal["en", "ar"] = "en") -> dict[str, Any]:
    """A common question and its answer in quoted source text, for the holder of an invitation link."""
    return service.relative_topic(store(), code, topic_id, lang)


@app.post("/api/r/{code}/teachback")
def teachback(code: str, body: TeachbackIn) -> dict[str, Any]:
    inv = next((i for i in store().list("invitation") if i["code"] == code), None)
    if inv is None:
        raise HTTPException(404, "This link is not valid")
    score = service.score_teachback(body.answers)
    inv["teachback"] = {"at": now(), **score}
    store().put("invitation", inv)
    store().audit(f"relative:{inv['id']}", "relative", "teachback.submit", case_id=inv["case_id"], entity=inv["id"],
                  detail={"score": score["score"], "total": score["total"]})
    if score["passed"] and inv["status"] == "opened":
        service.transition(store(), {"id": f"relative:{inv['id']}", "role": "relative"}, inv, "understood")
    return score


@app.post("/api/r/{code}/respond")
def respond(code: str, action: Literal["book", "decline"]) -> dict[str, Any]:
    inv = next((i for i in store().list("invitation") if i["code"] == code), None)
    if inv is None:
        raise HTTPException(404, "This link is not valid")
    new = "booked" if action == "book" else "declined_by_relative"
    return {"status": service.transition(store(), {"id": f"relative:{inv['id']}", "role": "relative"}, inv, new)["status"]}


# ---------------------------------------------------------------- messages --
@app.post("/api/messages")
def message(body: MessageIn, authorization: str = Header(default="")) -> dict[str, Any]:
    case_id, sender = body.case_id, "anonymous"
    if body.invite_code:
        inv = next((i for i in store().list("invitation") if i["code"] == body.invite_code), None)
        if inv is None:
            raise HTTPException(404, "This link is not valid")
        case_id, sender = inv["case_id"], f"relative:{inv['id']}"
    elif authorization:
        user = current_user(authorization)
        if case_id:
            service.visible_case(store(), user, case_id)
        sender = user["id"]
    result = classify(body.text, body.lang)
    reply = reply_for(result, body.lang)
    doc = {"id": new_id("msg"), "case_id": case_id, "sender": sender, "text": body.text, "lang": body.lang,
           "labels": sorted(result.labels | result.alert_labels), "reply_labels": sorted(result.labels),
           "rule_labels": sorted(result.rule_labels), "ngram_labels": sorted(result.ngram_labels),
           "model_labels": sorted(result.model_labels), "model": result.model_used, "topic": result.topic,
           "reply": reply.parts, "reply_digest": reply.digest, "escalate": reply.escalate, "resolved": False}
    store().put("message", doc)
    store().audit(sender, "relative" if sender.startswith("relative:") else "family", "message.triage",
                  case_id=case_id, entity=doc["id"],
                  detail={"labels": doc["labels"], "escalate": reply.escalate, "reply_digest": reply.digest})
    return {"reply": reply.parts, "escalated": reply.escalate, "labels": doc["labels"]}


@app.get("/api/messages")
def messages(user: dict[str, Any] = Depends(counsellor)) -> list[dict[str, Any]]:
    return list(reversed(store().list("message")))


@app.post("/api/messages/{msg_id}/resolve")
def resolve(msg_id: str, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    m = store().get("message", msg_id)
    if m is None:
        raise HTTPException(404, "Message not found")
    m["resolved"], m["resolved_by"], m["resolved_at"] = True, user["id"], now()
    store().put("message", m)
    store().audit(user["id"], user["role"], "message.resolve", case_id=m.get("case_id"), entity=msg_id)
    return m


# ---------------------------------------------------------- counsellor area --
@app.get("/api/queue")
def work_queue(user: dict[str, Any] = Depends(counsellor)) -> list[dict[str, Any]]:
    return service.queue(store())


@app.get("/api/outcomes")
def outcomes(case_id: str | None = None, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    """Programme measures from the challenge statement, computed live from recorded activity. With
    `case_id`, the measures for that one family."""
    if case_id:
        service.visible_case(store(), user, case_id)
    return service.outcomes(store(), case_id)


@app.post("/api/invitations/{inv_id}/approve")
def approve(inv_id: str, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    inv = store().get("invitation", inv_id)
    if inv is None:
        raise HTTPException(404, "Invitation not found")
    service.transition(store(), user, inv, "approved", {"signed_by": user["display_name"]})
    return service.transition(store(), user, inv, "sent")


@app.get("/api/audit")
def audit(case_id: str | None = None, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    return {"events": store().audit_events(case_id), "chain": store().verify_chain()}


@app.get("/api/fhir/cases/{case_id}")
def fhir_case(case_id: str, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    case = service.visible_case(store(), user, case_id)
    store().audit(user["id"], user["role"], "fhir.export", case_id=case_id)
    return fhir.case_bundle(store(), case)


@app.get("/api/evidence")
def evidence() -> dict[str, Any]:
    out: dict[str, Any] = {}
    if EVIDENCE_DIR.exists():
        for f in sorted(EVIDENCE_DIR.glob("*.json")):
            out[f.stem] = json.loads(f.read_text())
    return out


# --------------------------------------------------------------- demo only --
# Judge mode: in demo mode (fictional families only) anyone can enter as a demo persona without a password,
# open a relative's invitation, and reset the data. Every endpoint returns 404 when SILSILA_DEMO is off.
DEMO_PERSONAS = ("mariam", "reem", "counsellor")
DEMO_RELATIVE = ("case_cah_demo", "hamdan")  # Mariam's brother; Noura is left for the judge to invite


class DemoLoginIn(BaseModel):
    persona: Literal["mariam", "reem", "counsellor"]


def _demo_only() -> None:
    if not DEMO:
        raise HTTPException(404, "Not found")


@app.post("/api/demo/login")
def demo_login(body: DemoLoginIn) -> dict[str, Any]:
    _demo_only()
    user = next(iter(store().find("user", username=body.persona)), None)
    if user is None:
        raise HTTPException(404, "Unknown demo persona")
    store().audit(user["id"], user["role"], "auth.demo_login")
    return {"token": auth.issue(user), "user": {k: user[k] for k in ("id", "role", "display_name", "lang")}}


@app.post("/api/demo/relative")
def demo_relative() -> dict[str, Any]:
    """An invitation link as a relative would receive it. Created through the real flow (Mariam gives
    permission and asks; the counsellor approves and sends), marked as a demo shortcut in the audit log."""
    _demo_only()
    s = store()
    case_id, person = DEMO_RELATIVE
    live = [i for i in s.list("invitation", case_id)
            if i["person_id"] == person and i["status"] in ("sent", "opened", "understood", "booked")]
    if live:
        return {"code": live[0]["code"]}
    case, fam, cou = s.get("case", case_id), s.get("user", "user_family"), s.get("user", "user_counsellor")
    if case is None or fam is None or cou is None:
        raise HTTPException(409, "Demo data is missing; reset the demo")
    if not case.get("consents", {}).get("invite", {}).get("granted"):
        case = service.set_consent(s, fam, case, "invite", True)
    inv = service.create_invitation(s, fam, case, person, "anonymous_invite", False, False, None)
    service.transition(s, cou, inv, "approved", {"signed_by": cou["display_name"], "demo_shortcut": True})
    inv = service.transition(s, cou, inv, "sent", {"demo_shortcut": True})
    return {"code": inv["code"]}


@app.post("/api/demo/story")
def demo_story() -> dict[str, Any]:
    """Start a guided-story run: a fresh copy of the fictional CAH family under its own case id, plus demo
    sessions for Mariam and the counsellor. Each run is isolated, so judges running the story at the same
    time do not interfere. Story copies are hidden from case lists."""
    _demo_only()
    from . import seed as seed_mod
    s = store()
    case = seed_mod.cah_family()
    case_id = new_id("case_story")
    case.update(id=case_id, case_id=case_id, story=True)
    s.put("case", case)
    s.audit("demo", "system", "case.create", case_id=case_id, detail={"synthetic": True, "story": True})
    out: dict[str, Any] = {"case_id": case_id}
    for key, uid in (("family", "user_family"), ("counsellor", "user_counsellor")):
        u = s.get("user", uid)
        if u is None:
            raise HTTPException(409, "Demo data is missing; reset the demo")
        s.audit(u["id"], u["role"], "auth.demo_login", detail={"story": True})
        out[key] = {"token": auth.issue(u), "user": {k: u[k] for k in ("id", "role", "display_name", "lang")}}
    return out


@app.post("/api/demo/reset")
def demo_reset(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    """Recreate the fictional families, accounts and audit log. Signed-in sessions stay valid."""
    _demo_only()
    from . import seed as seed_mod
    seed_mod.seed(store())
    store().audit(user["id"], user["role"], "demo.reset")
    return {"ok": True, "audit": store().verify_chain()}



@app.post("/api/demo/tamper")
def demo_tamper(seq: int, user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    if not DEMO:
        raise HTTPException(404, "Not available")
    store().tamper_for_demo(seq)
    return store().verify_chain()


@app.post("/api/demo/inject")
def demo_inject(lang: Literal["en", "ar"] = "en", case_id: str | None = None,
                user: dict[str, Any] = Depends(counsellor)) -> dict[str, Any]:
    """Show the output gate stopping text that is not approved: render an
    approved reply, then alter it the way an unconstrained model might. `case_id` ties the blocked attempt
    to one family's audit trail (Watch a cascade)."""
    if not DEMO:
        raise HTTPException(404, "Not available")
    if case_id:
        service.visible_case(store(), user, case_id)
    reg = registry()
    msg = reg.template(Message(lang), "reply.decision_request")
    original = msg.parts[0]["text"]
    msg.parts[0]["text"] = ("Based on your results, it would be better not to go ahead with the marriage."
                            if lang == "en" else "بناءً على نتائجكما، من الأفضل عدم إتمام الزواج.")
    try:
        reg.gate(msg)
        blocked, reason = False, None
    except GateError as e:
        blocked, reason = True, str(e)
        store().audit(user["id"], user["role"], "output_gate.block", outcome="blocked", case_id=case_id,
                      detail={"reason": reason, "demo": True})
    return {"attempted": msg.parts[0]["text"], "approved_original": original, "blocked": blocked, "reason": reason}
