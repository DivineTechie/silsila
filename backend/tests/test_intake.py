"""Voice intake: the recorded Jais 3 draft, counsellor actions, and the engine gate."""

from __future__ import annotations

import pytest

from silsila import intake
from silsila.api import seed, service

from .test_api_flow import COUNSELLOR_PW, FAMILY_PW, client, login  # noqa: F401  (fixture)

# Arabic names in the recorded draft (as transcribed, including the ASR misspellings) -> seeded case ids
NAME_TO_SEED = {"مريم": "mariam", "زايد": "zayed", "سعيد": "saeed", "راشد": "rashid", "سلم": "salma",
                "عبيد": "obaid", "موزة": "moza", "أحمد": "ahmed", "حصّة": "hessa", "ميثاء": "maitha",
                "نورة": "noura", "خلفان": "khalfan", "جمعة": "juma", "حمدان": "hamdan", "شمّة": "shamma",
                "سرة": "sara"}


def ids(draft):
    return {p["name"]: p["id"] for p in draft["people"]}


def test_demo_draft_issues_are_all_listed():
    demo = intake.load_demo()
    codes = sorted(i["code"] for i in demo["issues"])
    assert codes == ["heard_health_status", "heard_health_status", "one_parent", "one_parent"]
    n = ids(demo["draft"])
    by_code = {(i["code"], i["person"]): i for i in demo["issues"]}
    # Zayed's missing father: the rule suggests his mother's husband, Ahmed
    assert by_code[("one_parent", n["زايد"])]["suggest"] == {"set_parent": n["أحمد"]}
    # Mariam, Noura and Hamdan share a father and no mother: ONE shared unnamed mother is suggested
    shared = next(i for i in demo["issues"] if i.get("role") == "mother")
    assert sorted(shared["persons"]) == sorted([n["مريم"], n["نورة"], n["حمدان"]])
    # health status heard in speech is never used
    assert all(p["status"] == "unknown" for p in demo["draft"]["people"])


def test_compute_refused_until_confirmed_and_fixed():
    d = intake.load_demo()["draft"]
    with pytest.raises(intake.IntakeError, match="Not yet confirmed"):
        intake.ready_pedigree(d)
    d = intake.apply(d, {"type": "confirm_all_people"})
    d = intake.apply(d, {"type": "confirm_all_unions"})
    with pytest.raises(intake.IntakeError, match="Fix these first"):
        intake.ready_pedigree(d)


def test_status_needs_a_record():
    d = intake.load_demo()["draft"]
    z = ids(d)["زايد"]
    with pytest.raises(intake.IntakeError, match="record"):
        intake.apply(d, {"type": "set_status_from_record", "person": z, "status": "affected"})
    d["people"][[p["id"] for p in d["people"]].index(z)]["status"] = "affected"  # forged, no source
    assert any(i["code"] == "status_without_record" for i in intake.review(d))


def test_edit_clears_confirmation():
    d = intake.load_demo()["draft"]
    d = intake.apply(d, {"type": "confirm_all_people"})
    z = ids(d)["زايد"]
    d = intake.apply(d, {"type": "set_parent", "persons": [z], "role": "father", "parent": ids(d)["أحمد"]})
    assert not next(p for p in d["people"] if p["id"] == z)["confirmed"]


def _counsellor_fixes(c, cou, state):
    def act(action):
        r = c.post("/api/intake/apply", json={"draft": state["draft"], "action": action}, headers=cou)
        assert r.status_code == 200, r.text
        return r.json()

    for issue in [i for i in state["issues"] if "suggest" in i]:
        s = issue["suggest"]
        if "set_parent" in s:
            state = act({"type": "set_parent", "persons": issue["persons"], "role": issue["role"], "parent": s["set_parent"]})
        else:
            state = act({"type": "add_unknown_parent", "persons": issue["persons"], "role": issue["role"],
                         "partner_of": s.get("partner_of")})
    n = ids(state["draft"])
    rec = "Newborn screening record (demo)"
    state = act({"type": "set_status_from_record", "person": n["زايد"], "status": "affected",
                 "affected_with": "classic congenital adrenal hyperplasia", "record_ref": rec})
    for name in ("مريم", "أحمد", "سرة"):
        state = act({"type": "set_status_from_record", "person": n[name], "status": "unaffected", "record_ref": "Clinic record (demo)"})
    state = act({"type": "set_flag", "person": n["نورة"], "flag": "pregnant", "value": True})
    for name in ("عبيد", "موزة"):
        state = act({"type": "set_flag", "person": n[name], "flag": "deceased", "value": True})
    state = act({"type": "confirm_all_people"})
    state = act({"type": "confirm_all_unions"})
    return state


def test_voice_intake_gives_same_numbers_as_the_entered_case(client):  # noqa: F811
    fam = login(client, "mariam", FAMILY_PW)
    assert client.get("/api/intake/demo", headers=fam).status_code == 403  # counsellors only
    cou = login(client, "counsellor", COUNSELLOR_PW)
    state = client.get("/api/intake/demo", headers=cou).json()
    assert state["recorded"] is True and not state["ready"]
    assert client.post("/api/intake/compute", json={"draft": state["draft"]}, headers=cou).status_code == 422

    state = _counsellor_fixes(client, cou, state)
    assert state["ready"], state["issues"]
    r = client.post("/api/intake/compute", json={"draft": state["draft"]}, headers=cou)
    assert r.status_code == 200, r.text
    got = r.json()["report"]
    assert got["status"] == "ok"

    # The seeded case was entered by hand from the same fictional family. After the counsellor's checks the
    # voice-drafted tree must give exactly the same carrier probabilities for every person.
    want = service.compute_report(seed.cah_family())
    names = {p["id"]: p["name"] for p in state["draft"]["people"]}
    compared = 0
    for pid, row in got["people"].items():
        sid = NAME_TO_SEED.get(names[pid])
        if sid is None:  # the counsellor-added unnamed mother corresponds to Aisha
            sid = "aisha"
        assert row["computed"]["p_any_variant"] == pytest.approx(want["people"][sid]["computed"]["p_any_variant"], abs=1e-12), sid
        compared += 1
    assert compared == 17
    assert got["invites"][0]["reason_code"] == "current_pregnancy"

    audit = client.get("/api/audit", headers=cou).json()
    events = [e["action"] for e in audit["events"]]
    assert "intake.compute" in events and "intake.action" in events
