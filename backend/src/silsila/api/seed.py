"""Seed the demo database with FICTIONAL families and demo accounts.

All people below are invented for demonstration. Names are common Emirati
first names chosen so the demo reads naturally; they refer to no real person.
Demo passwords come from environment variables (see backend/.env.example).

Run: uv run python -m silsila.api.seed  (wipes and recreates the demo data)
"""

from __future__ import annotations

import os
from pathlib import Path

from .auth import hash_password
from .store import Store, now


def P(id_, sex, name, mother=None, father=None, **kw):
    return {"id": id_, "sex": sex, "name": name, "mother": mother, "father": father,
            "status": kw.pop("status", "unknown"), **kw}


def cah_family() -> dict:
    """Newborn found to have classic CAH on newborn screening. His parents,
    Mariam and Ahmed, are first cousins. Mariam's sister Noura is married to
    another first cousin, Khalfan, and is pregnant; they married in 2019,
    before premarital genetic screening became mandatory."""
    people = [
        P("obaid", "male", "Obaid (great-grandfather)", deceased=True),
        P("moza", "female", "Moza (great-grandmother)", deceased=True),
        P("saeed", "male", "Saeed (Mariam's father)", "moza", "obaid"),
        P("aisha", "female", "Aisha (Mariam's mother)"),
        P("rashid", "male", "Rashid (Ahmed's father)", "moza", "obaid"),
        P("hessa", "female", "Hessa (Ahmed's mother)"),
        P("salma", "female", "Salma (Khalfan's mother)", "moza", "obaid"),
        P("juma", "male", "Juma (Khalfan's father)"),
        P("mariam", "female", "Mariam", "aisha", "saeed", status="unaffected"),
        P("ahmed", "male", "Ahmed", "hessa", "rashid", status="unaffected"),
        P("noura", "female", "Noura (Mariam's sister)", "aisha", "saeed", pregnant=True),
        P("khalfan", "male", "Khalfan (Noura's husband)", "salma", "juma"),
        P("hamdan", "male", "Hamdan (Mariam's brother)", "aisha", "saeed"),
        P("shamma", "female", "Shamma (Hamdan's wife)"),
        P("maitha", "female", "Maitha (Ahmed's sister)", "hessa", "rashid"),
        P("zayed", "male", "Baby Zayed", "mariam", "ahmed", status="affected",
          affected_with="classic congenital adrenal hyperplasia"),
        P("sara", "female", "Sara (Zayed's sister)", "mariam", "ahmed", status="unaffected"),
    ]
    unions = [{"a": "shamma", "b": "hamdan"}, {"a": "noura", "b": "khalfan"}]
    return {"id": "case_cah_demo", "title": "Newborn screening: classic CAH", "locus_id": "CYP21A2",
            "index_person_id": "zayed", "index_source": "newborn_screen", "family_user_id": "user_family",
            "pedigree": {"people": people, "unions": unions},
            "consents": {"compute": {"granted": True, "granted_at": now(), "withdrawn_at": None,
                                     "by": "user_family", "wording_template": "consent.compute"}}}


def hbb_family() -> dict:
    """Premarital result: a couple of first cousins, both beta-thalassaemia
    carriers. Already married relatives in the wider family are untested."""
    people = [
        P("gf", "male", "Ali (grandfather)"), P("gm", "female", "Mouza (grandmother)"),
        P("f1", "male", "Khalid", "gm", "gf"), P("m1", "female", "Fatima"),
        P("f2", "male", "Sultan", "gm", "gf"), P("m2", "female", "Alia"),
        P("bride", "female", "Reem", "m1", "f1", status="unaffected", test={"detected": ["B"]}),
        P("groom", "male", "Saif", "m2", "f2", status="unaffected", test={"detected": ["B"]}),
        P("rsis", "female", "Latifa (Reem's sister)", "m1", "f1"), P("rsish", "male", "Obaid (Latifa's husband)"),
        P("sbro", "male", "Mohammed (Saif's brother)", "m2", "f2"), P("sbrow", "female", "Hind (Mohammed's wife)"),
    ]
    unions = [{"a": "bride", "b": "groom"}, {"a": "rsis", "b": "rsish"}, {"a": "sbrow", "b": "sbro"}]
    return {"id": "case_hbb_demo", "title": "Premarital result: both partners beta-thalassaemia carriers",
            "locus_id": "HBB", "index_person_id": "bride", "index_source": "premarital_at_risk",
            "family_user_id": "user_family2", "pedigree": {"people": people, "unions": unions},
            "consents": {"compute": {"granted": True, "granted_at": now(), "withdrawn_at": None,
                                     "by": "user_family2", "wording_template": "consent.compute"}}}


def alpha_family() -> dict:
    people = [P("m", "female", "Shaikha"), P("f", "male", "Majid"),
              P("c", "female", "Baby Hamda", "m", "f", status="affected", affected_with="HbH disease")]
    return {"id": "case_hba_demo", "title": "Alpha-thalassaemia (not calculated in this version)",
            "locus_id": "HBA1/HBA2", "index_person_id": "c", "index_source": "diagnosed_child",
            "family_user_id": "user_family2", "pedigree": {"people": people, "unions": []},
            "consents": {"compute": {"granted": True, "granted_at": now(), "withdrawn_at": None,
                                     "by": "user_family2", "wording_template": "consent.compute"}}}


def users() -> list[dict]:
    pw = lambda key: os.environ[key]  # noqa: E731 - fail loudly if a demo password is missing
    return [
        {"id": "user_family", "username": "mariam", "role": "family", "display_name": "Mariam (demo family)",
         "lang": "en", "password_hash": hash_password(pw("SILSILA_DEMO_FAMILY_PASSWORD"))},
        {"id": "user_family2", "username": "reem", "role": "family", "display_name": "Reem (demo family)",
         "lang": "ar", "password_hash": hash_password(pw("SILSILA_DEMO_FAMILY_PASSWORD"))},
        {"id": "user_counsellor", "username": "counsellor", "role": "counsellor",
         "display_name": "Demo genetic counsellor", "lang": "en",
         "password_hash": hash_password(pw("SILSILA_DEMO_COUNSELLOR_PASSWORD"))},
    ]


def load_env_file() -> None:
    env = Path(__file__).resolve().parents[3] / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def seed(store: Store) -> None:
    store.conn.executescript("DELETE FROM docs; DELETE FROM audit;")
    for u in users():
        store.put("user", u)
    for case in (cah_family(), hbb_family(), alpha_family()):
        case["case_id"] = case["id"]
        store.put("case", case)
        store.audit("seed", "system", "case.create", case_id=case["id"], detail={"synthetic": True})


if __name__ == "__main__":
    load_env_file()
    s = Store()
    seed(s)
    print("Seeded", s.path, s.verify_chain())
