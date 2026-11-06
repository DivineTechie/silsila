"""Privacy attack run against the API (in-process, synthetic demo data).

Counts how many of a large number of unauthorised requests return anything
other than a refusal, and checks that relatives see only what the index
person chose to disclose, for every combination of disclosure settings.

Run: cd backend && uv run python -m evals.privacy_eval [--n 10000]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import secrets
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    args = ap.parse_args()
    tmp = tempfile.mkdtemp()
    os.environ.update({"SILSILA_DB": f"{tmp}/p.db", "SILSILA_DEMO_FAMILY_PASSWORD": "pw-family-eval",
                       "SILSILA_DEMO_COUNSELLOR_PASSWORD": "pw-counsellor-eval", "SILSILA_DEMO": "1"})
    from fastapi.testclient import TestClient

    from silsila.api import app as app_mod, seed, store as store_mod

    s = store_mod.Store()
    seed.seed(s)
    app_mod._store = s
    c = TestClient(app_mod.app)

    def token(u: str, pw: str) -> dict:
        return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": u, "password": pw}).json()["token"]}

    fam, fam2 = token("mariam", "pw-family-eval"), token("reem", "pw-family-eval")
    cou = token("counsellor", "pw-counsellor-eval")

    # one invitation per disclosure combination, plus one left unapproved
    for who in (fam,):
        c.post("/api/cases/case_cah_demo/consents", json={"scope": "invite", "granted": True}, headers=who)
    combos = [(False, False), (True, False), (False, True), (True, True)]
    targets = ["noura", "khalfan", "hamdan", "maitha"]
    codes = []
    for (cond, sender), person in zip(combos, targets):
        inv = c.post("/api/cases/case_cah_demo/invitations", headers=fam, json={
            "person_id": person, "channel": "anonymous_invite", "disclose_condition": cond,
            "disclose_sender": sender, "sender_name": "Mariam" if sender else None}).json()
        sent = c.post(f"/api/invitations/{inv['id']}/approve", headers=cou).json()
        codes.append((cond, sender, sent["code"]))
    pending = c.post("/api/cases/case_cah_demo/invitations", headers=fam, json={
        "person_id": "shamma", "channel": "clinic_contact"}).json()

    disclosure_checks = []
    for cond, sender, code in codes:
        for lang in ("en", "ar"):
            v = c.get(f"/api/r/{code}?lang={lang}").json()
            msg_text = json.dumps(v["message"], ensure_ascii=False)
            info_text = json.dumps(v["information"], ensure_ascii=False)
            leaks_name = ("Mariam" in msg_text) and not sender
            leaks_condition = (("adrenal" in (msg_text + info_text).lower()) or ("21-hydroxylase" in (msg_text + info_text).lower())) and not cond
            other_people = any(n in json.dumps(v, ensure_ascii=False) for n in ("Ahmed", "Zayed", "Noura", "Khalfan"))
            disclosure_checks.append({"disclose_condition": cond, "disclose_sender": sender, "lang": lang,
                                      "leaks_name": leaks_name, "leaks_condition": leaks_condition,
                                      "names_other_people": other_people})

    rng = random.Random(0)
    attacks = [
        ("guess_invitation_code", lambda: c.get(f"/api/r/{secrets.token_urlsafe(16)}"), {403, 404}),
        ("unsent_invitation_link", lambda: c.get(f"/api/r/{pending['code']}"), {403}),
        ("other_family_case", lambda: c.get("/api/cases/case_hbb_demo", headers=fam), {403}),
        ("other_family_case_2", lambda: c.get("/api/cases/case_cah_demo", headers=fam2), {403}),
        ("family_reads_queue", lambda: c.get("/api/queue", headers=fam), {403}),
        ("family_reads_audit", lambda: c.get("/api/audit", headers=fam), {403}),
        ("family_exports_fhir", lambda: c.get("/api/fhir/cases/case_cah_demo", headers=fam), {403}),
        ("family_reads_messages", lambda: c.get("/api/messages", headers=fam), {403}),
        ("no_token_case", lambda: c.get("/api/cases/case_cah_demo"), {401}),
        ("forged_token", lambda: c.get("/api/cases/case_cah_demo",
                                       headers={"Authorization": "Bearer " + secrets.token_urlsafe(40)}), {401}),
        ("family_approves_own_invite", lambda: c.post(f"/api/invitations/{pending['id']}/approve", headers=fam), {403}),
        ("family_records_result", lambda: c.post(f"/api/invitations/{pending['id']}/result", headers=fam,
                                                 json={"detected": []}), {403}),
        ("other_family_invites", lambda: c.post("/api/cases/case_cah_demo/invitations", headers=fam2,
                                                json={"person_id": "noura", "channel": "anonymous_invite"}), {403}),
        ("bad_password", lambda: c.post("/api/auth/login", json={"username": "counsellor",
                                                                 "password": secrets.token_hex(6)}), {401}),
    ]
    tally: Counter = Counter()
    failures = []
    for _ in range(args.n):
        name, fn, allowed = rng.choice(attacks)
        r = fn()
        tally[name] += 1
        if r.status_code not in allowed:
            failures.append({"attack": name, "status": r.status_code, "body": r.text[:200]})
    chain = s.verify_chain()
    result = {
        "attempts": args.n, "by_attack": dict(tally), "unauthorised_disclosures": len(failures),
        "failures": failures[:20],
        "disclosure_checks": disclosure_checks,
        "disclosure_violations": sum(d["leaks_name"] or d["leaks_condition"] or d["names_other_people"]
                                     for d in disclosure_checks),
        "denied_attempts_in_audit": sum(1 for e in s.audit_events(limit=10**6) if e["outcome"] == "denied"),
        "audit_chain_after_run": chain,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "privacy_api.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k not in ("disclosure_checks", "failures")}, indent=2))


if __name__ == "__main__":
    main()
