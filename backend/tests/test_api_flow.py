"""End-to-end API flow on the synthetic demo families."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

FAMILY_PW = "test-family-pw"
COUNSELLOR_PW = "test-counsellor-pw"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SILSILA_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("SILSILA_DEMO_FAMILY_PASSWORD", FAMILY_PW)
    monkeypatch.setenv("SILSILA_DEMO_COUNSELLOR_PASSWORD", COUNSELLOR_PW)
    monkeypatch.setenv("SILSILA_DEMO", "1")
    from silsila.api import app as app_mod, seed, store as store_mod
    importlib.reload(app_mod)
    s = store_mod.Store()
    seed.seed(s)
    app_mod._store = s
    return TestClient(app_mod.app)


def login(c, user, pw):
    r = c.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_full_cascade_flow(client):
    fam = login(client, "mariam", FAMILY_PW)
    cou = login(client, "counsellor", COUNSELLOR_PW)

    case = client.get("/api/cases/case_cah_demo", headers=fam).json()
    rep = case["report"]
    assert rep["status"] == "ok"
    # Mariam and Ahmed are unaffected parents of an affected child: obligate carriers
    assert rep["people"]["mariam"]["computed"]["p_any_variant"] == pytest.approx(1.0)
    # Noura is pregnant: her couple is ranked first
    assert rep["invites"][0]["person_id"] in ("noura", "khalfan")
    assert rep["invites"][0]["reason_code"] == "current_pregnancy"
    # every sentence is an approved template part
    assert all(p["type"] == "template" for p in rep["people"]["noura"]["sentence"])

    # inviting needs the 'invite' permission first
    body = {"person_id": "noura", "channel": "anonymous_invite"}
    assert client.post("/api/cases/case_cah_demo/invitations", json=body, headers=fam).status_code == 403
    client.post("/api/cases/case_cah_demo/consents", json={"scope": "invite", "granted": True}, headers=fam)
    inv = client.post("/api/cases/case_cah_demo/invitations", json=body, headers=fam).json()
    assert inv["status"] == "awaiting_counsellor"

    # a family cannot approve; the counsellor does, which also sends it
    assert client.post(f"/api/invitations/{inv['id']}/approve", headers=fam).status_code == 403
    sent = client.post(f"/api/invitations/{inv['id']}/approve", headers=cou).json()
    assert sent["status"] == "sent"
    code = sent["code"]

    # the relative sees no name and no condition, plus the anonymity notice
    view = client.get(f"/api/r/{code}?lang=ar").json()
    ids = [p["id"] for p in view["message"]]
    assert ids == ["invite.anonymous", "invite.anonymity_notice"]
    assert "Mariam" not in str(view) and "adrenal" not in str(view["message"])
    assert all(p["type"] == "source" for p in view["information"])

    tb = {q["id"]: "a" for q in view["teachback"]}
    assert client.post(f"/api/r/{code}/teachback", json={"answers": tb}).json()["passed"]
    assert client.post(f"/api/r/{code}/respond?action=book").json()["status"] == "booked"

    closed = client.post(f"/api/invitations/{inv['id']}/result", json={"detected": []}, headers=cou).json()
    assert closed["status"] == "closed" and closed["closure_evidence"]["type"] == "test_result"
    # CYP21A2 has no published detection rate: the app says so instead of a number
    after = client.get("/api/cases/case_cah_demo", headers=fam).json()["report"]
    assert after["people"]["noura"]["residual_note"][0]["id"] == "result.residual_not_modelled"


def test_privacy_between_families_and_roles(client):
    fam = login(client, "mariam", FAMILY_PW)
    r = client.get("/api/cases/case_hbb_demo", headers=fam)
    assert r.status_code == 403
    assert client.get("/api/queue", headers=fam).status_code == 403
    assert client.get("/api/r/not-a-real-code").status_code == 403
    cou = login(client, "counsellor", COUNSELLOR_PW)
    denied = [e for e in client.get("/api/audit", headers=cou).json()["events"] if e["outcome"] == "denied"]
    assert len(denied) >= 3


def test_messages_are_triaged_and_escalated(client):
    cou = login(client, "counsellor", COUNSELLOR_PW)
    r = client.post("/api/messages", json={"text": "هل يجوز؟ هل نلغي الزواج؟", "lang": "ar"}).json()
    assert r["escalated"] and {"religious", "decision_request"} <= set(r["labels"])
    crisis = client.post("/api/messages", json={"text": "I want to end my life", "lang": "en"}).json()
    assert crisis["reply"][0]["id"] == "reply.crisis"
    q = client.get("/api/queue", headers=cou).json()
    assert q[0]["type"] == "message" and "crisis" in q[0]["reasons"]


def test_inconsistent_and_excluded_cases_show_no_numbers(client):
    cou = login(client, "counsellor", COUNSELLOR_PW)
    hba = client.get("/api/cases/case_hba_demo", headers=cou).json()["report"]
    assert hba["status"] == "not_calculated" and hba["message"][0]["id"] == "result.excluded_locus"
    # Both parents of the affected newborn recorded as testing negative for CYP21A2.
    # No detection rate is published for this gene, so the engine treats tests as
    # complete and the results cannot all be true: no numbers, counsellor review.
    ped = client.get("/api/cases/case_cah_demo", headers=cou).json()["case"]["pedigree"]
    for p in ped["people"]:
        if p["id"] in ("mariam", "ahmed"):
            p["test"] = {"detected": []}
    assert client.put("/api/cases/case_cah_demo/pedigree", json=ped, headers=cou).status_code == 200
    rep = client.get("/api/cases/case_cah_demo", headers=cou).json()["report"]
    assert rep["status"] == "inconsistent" and "people" not in rep
    assert rep["message"][0]["id"] == "result.inconsistent"
    assert any("results_do_not_fit" in i["reasons"] for i in client.get("/api/queue", headers=cou).json())


def test_audit_chain_detects_tampering_and_gate_blocks_injection(client):
    cou = login(client, "counsellor", COUNSELLOR_PW)
    assert client.get("/api/audit", headers=cou).json()["chain"]["intact"]
    inj = client.post("/api/demo/inject", headers=cou).json()
    assert inj["blocked"]
    broken = client.post("/api/demo/tamper?seq=2", headers=cou).json()
    assert broken["intact"] is False and broken["first_broken_seq"] == 2


def test_fhir_bundle_validates_with_invitations(client):
    fam = login(client, "mariam", FAMILY_PW)
    cou = login(client, "counsellor", COUNSELLOR_PW)
    client.post("/api/cases/case_cah_demo/consents", json={"scope": "invite", "granted": True}, headers=fam)
    client.post("/api/cases/case_cah_demo/invitations", json={"person_id": "noura", "channel": "clinic_contact"},
                headers=fam)
    r = client.get("/api/fhir/cases/case_cah_demo", headers=cou)
    assert r.status_code == 200, r.text
    kinds = {e["resource"]["resourceType"] for e in r.json()["entry"]}
    assert {"Patient", "FamilyMemberHistory", "RiskAssessment", "Consent", "Task", "AuditEvent"} <= kinds


def test_bad_family_tree_gets_a_clear_message(client):
    cou = login(client, "counsellor", COUNSELLOR_PW)
    ped = {"people": [{"id": "a", "sex": "female", "mother": "x", "father": None}], "unions": []}
    r = client.put("/api/cases/case_cah_demo/pedigree", json=ped, headers=cou)
    assert r.status_code == 422 and "both parents" in r.json()["detail"]


def test_oversized_family_gets_a_message_not_a_crash(client, monkeypatch):
    from silsila.engine import inference
    monkeypatch.setattr(inference, "MAX_FACTOR_ENTRIES", 10)
    cou = login(client, "counsellor", COUNSELLOR_PW)
    rep = client.get("/api/cases/case_cah_demo", headers=cou).json()["report"]
    assert rep["status"] == "too_complex" and rep["message"][0]["id"] == "result.too_complex"
    assert any("family_tree_too_complex" in i["reasons"] for i in client.get("/api/queue", headers=cou).json())


def test_judge_mode_personas_relative_link_and_reset(client):
    r = client.post("/api/demo/login", json={"persona": "counsellor"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "counsellor"
    cou = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.post("/api/demo/login", json={"persona": "admin"}).status_code == 422

    code = client.post("/api/demo/relative").json()["code"]
    assert client.post("/api/demo/relative").json()["code"] == code  # reused while open
    view = client.get(f"/api/r/{code}?lang=ar").json()
    assert [p["id"] for p in view["message"]] == ["invite.anonymous", "invite.anonymity_notice"]
    events = client.get("/api/audit", headers=cou).json()["events"]
    assert any(e["action"] == "invitation.approved" and e["detail"].get("demo_shortcut") for e in events)

    assert client.post("/api/demo/reset").status_code == 401
    assert client.post("/api/demo/reset", headers=cou).json()["audit"]["intact"]
    assert client.get(f"/api/r/{code}").status_code == 403  # the invitation is gone after reset
    assert client.get("/api/queue", headers=cou).status_code == 200  # the session still works


def test_judge_mode_is_off_outside_demo(client, monkeypatch):
    from silsila.api import app as app_mod
    monkeypatch.setattr(app_mod, "DEMO", False)
    assert client.post("/api/demo/login", json={"persona": "mariam"}).status_code == 404
    assert client.post("/api/demo/relative").status_code == 404


def test_arabic_view_shows_arabic_names_and_keeps_english_on_save(client):
    reem = client.post("/api/demo/login", json={"persona": "reem"}).json()
    h = {"Authorization": f"Bearer {reem['token']}"}
    assert client.get("/api/cases?lang=ar", headers=h).json()[0]["title"].startswith(("الثلاسيميا", "نتيجة"))
    ar = client.get("/api/cases/case_hbb_demo?lang=ar", headers=h).json()
    bride = next(p for p in ar["case"]["pedigree"]["people"] if p["id"] == "bride")
    assert bride["name"] == "ريم" and bride["name_en"] == "Reem"
    # saving the Arabic view must not overwrite the stored English names
    ped = ar["case"]["pedigree"]
    assert client.put("/api/cases/case_hbb_demo/pedigree", json=ped, headers=h).status_code == 200
    en = client.get("/api/cases/case_hbb_demo?lang=en", headers=h).json()
    bride_en = next(p for p in en["case"]["pedigree"]["people"] if p["id"] == "bride")
    assert bride_en["name"] == "Reem" and bride_en["name_ar"] == "ريم" and "name_en" not in bride_en


def test_outcomes_follow_a_full_invitation(client):
    fam = login(client, "mariam", FAMILY_PW)
    cou = login(client, "counsellor", COUNSELLOR_PW)
    assert client.get("/api/outcomes", headers=fam).status_code == 403
    client.post("/api/cases/case_cah_demo/consents", json={"scope": "invite", "granted": True}, headers=fam)
    inv = client.post("/api/cases/case_cah_demo/invitations", json={"person_id": "noura", "channel": "anonymous_invite"},
                      headers=fam).json()
    code = client.post(f"/api/invitations/{inv['id']}/approve", headers=cou).json()["code"]
    view = client.get(f"/api/r/{code}?lang=ar").json()
    client.post(f"/api/r/{code}/teachback", json={"answers": {q["id"]: "a" for q in view["teachback"]}})
    client.post(f"/api/r/{code}/respond?action=book")
    o = client.get("/api/outcomes", headers=cou).json()
    assert o["funnel"]["sent"] == 1 and o["funnel"]["opened"] == 1 and o["funnel"]["booked"] == 1
    assert o["comprehension"] == {"submitted": 1, "passed": 1}
    assert o["by_language"]["ar"] == {"opened": 1, "teachback": 1, "understood": 1, "booked_or_tested": 1}
    assert o["uptake"]["booked_or_tested"] == 1 and o["hours"]["request_to_sent"] is not None
    assert o["privacy"]["audit_chain"]["intact"]
