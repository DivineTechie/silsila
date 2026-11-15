"""Family Twin: one fictional, simulated clan used to show the engine at work, live.

* The clan, its marriages and the hidden "true" genotypes come from the same simulator and assumptions as
  benchmark B4 (tribe structure calibrated to Denic 2013, uptake from Ahmed 2002). Nothing here is real.
* The engine never sees the hidden truth. It sees what a clinic would: the affected newborn, the parents'
  test results, and any further results the user records.
* `what_if` recomputes every person's exact carrier chance after new results (exact inference over the
  whole looped pedigree) and reports how long it took.
* The cascade race replays B4's comparison on this one clan: relatives invited in the engine's order
  versus in family order, with the same acceptances and the same hidden results, counting at-risk couples
  found per test. One clan illustrates; the B4 evidence (many clans, confidence intervals) is the claim.
"""

from __future__ import annotations

import functools
import time
from typing import Any

import numpy as np

from . import params
from .engine import InconsistentEvidence, Pedigree, Person, Phenotype, TestResult
from .engine.risk import family_report
from .sim import scenarios as S
from .sim.genedrop import TruthModel, derive, drop
from .sim.kindred import generate_kindred, kinship_matrix
from .sim.sources import assumption_values

LOCUS = "HBB"
SEED = 20261115
FEMALE = ["Mariam", "Noura", "Hessa", "Moza", "Shamma", "Maitha", "Salama", "Fatima", "Aisha", "Latifa", "Alyazia",
          "Mahra", "Roudha", "Hind", "Ghaya", "Afra", "Sheikha", "Amna", "Meera", "Khawla", "Reem", "Sara", "Hamda",
          "Wadha", "Ousha", "Lubna", "Asma", "Mouza", "Hamama", "Shaikha", "Nouf", "Dana", "Jawaher", "Hala", "Basma",
          "Muna", "Najla", "Fakhra", "Zainab", "Kaltham", "Sumaya", "Maryam", "Habiba", "Rawda", "Sana", "Lamya"]
MALE = ["Saeed", "Rashid", "Ahmed", "Khalfan", "Hamdan", "Obaid", "Juma", "Zayed", "Mohammed", "Khalifa", "Sultan",
        "Hamad", "Saif", "Mansour", "Faisal", "Majid", "Thani", "Humaid", "Ali", "Omar", "Abdullah", "Khalid", "Salem",
        "Yousef", "Ibrahim", "Marwan", "Hazza", "Theyab", "Nahyan", "Tahnoun", "Mubarak", "Hilal", "Ghanim", "Jassim",
        "Matar", "Butti", "Suhail", "Nasser", "Khamis", "Eissa", "Musabbah", "Hareb", "Fahad", "Rakan", "Badr"]


def _names(ids_by_sex: list[tuple[str, str]], rng: np.random.Generator) -> dict[str, str]:
    f, m = list(FEMALE), list(MALE)
    rng.shuffle(f)
    rng.shuffle(m)
    out, fi, mi = {}, 0, 0
    for pid, sex in ids_by_sex:
        if sex == "female":
            base = f[fi % len(f)]
            out[pid] = base if fi < len(f) else f"{base} {fi // len(f) + 1}"
            fi += 1
        else:
            base = m[mi % len(m)]
            out[pid] = base if mi < len(m) else f"{base} {mi // len(m) + 1}"
            mi += 1
    return out


def _race(order, partners, positive, accept, pre_tested, couple_ids, exclude, detected=lambda p: []) -> list[dict[str, Any]]:
    """B4's sequential cascade, recording each test as an event."""
    tested = set(pre_tested)
    pos = {p for p in pre_tested if positive(p)}
    found: set[tuple[str, str]] = set()
    events: list[dict[str, Any]] = []

    def test(p: str, via: str) -> None:
        tested.add(p)
        new = []
        if positive(p):
            pos.add(p)
            for c in couple_ids.get(p, ()):
                if c != exclude and c not in found and c[0] in pos and c[1] in pos:
                    found.add(c)
                    new.append(list(c))
        events.append({"person": p, "carrier": positive(p), "detected": detected(p), "via": via, "couples_found": new,
                       "total_couples": len(found)})

    for x in order:
        if x in tested or not accept(x):
            continue
        test(x, "invited")
        if positive(x):
            for y in partners.get(x, ()):
                if y not in tested and accept(y):
                    test(y, "partner of a carrier")
    return events


def _candidate(seed: int) -> dict[str, Any] | None:
    a = assumption_values()
    rng = np.random.default_rng(seed)
    cfg, _ = S.calibrated_config(a, "uae")
    k = generate_kindred(cfg, rng)
    ped = k.pedigree
    rec = S.engine_record(LOCUS)
    bg_f, theta = rec.background_f, float(a["theta_uae"])
    model = TruthModel(S.uae_truth_locus(LOCUS, theta + (1 - theta) * bg_f, None), theta, bg_f)
    R = 400
    al = drop(ped, k.clan, model, R, rng)
    d = derive(model, al, rng)
    youngest = [p for p in ped.people if k.generation[p] == k.youngest]
    loc = model.locus
    for r in range(R):
        affected = [p for p in youngest if d.affected[p][r]]
        if not affected:
            continue
        index = affected[0]
        mother, father = ped.people[index].mother, ped.people[index].father
        members = S.drawn_tree(k, index, a["uae_drawn_tree_scope"])
        if not 40 <= len(members) <= 75:
            return None
        people = []
        for pid in sorted(members, key=lambda x: (k.generation[x], x)):
            src = ped.people[pid]
            p = Person(pid, src.sex, src.mother, src.father, deceased=src.deceased)
            if pid == index:
                p.phenotype = Phenotype(loc.phenotype_vector[int(d.genotype[pid][r])])
            if pid in (mother, father):
                p.test = TestResult(tuple(sorted(loc.alleles[int(x)].id for x, hit in zip(al[pid][r], d.detected[pid][r]) if hit)))
            people.append(p)
        dped = Pedigree.from_people(people)
        order, kmat = kinship_matrix(dped)
        kidx = {p: i for i, p in enumerate(order)}
        couples = [(f, m) for f, m in dped.couples()]
        consang = [(f, m) for f, m in couples if kmat[kidx[f], kidx[m]] > 0]
        living = [(f, m) for f, m in couples if not dped.people[f].deceased and not dped.people[m].deceased]
        true_risk = [c for c in living if c != (mother, father) and d.carrier_any[c[0]][r] and d.carrier_any[c[1]][r]]
        if len(consang) < 3 or len(true_risk) < 3:
            continue
        return {"seed": seed, "replicate": r, "k": k, "ped": dped, "index": index, "mother": mother, "father": father,
                "index_phenotype": loc.phenotype_vector[int(d.genotype[index][r])],
                "al": al, "d": d, "kmat": kmat, "kidx": kidx, "couples": couples, "consang": consang,
                "true_risk": true_risk, "a": a, "rng": rng}
    return None


CLAN_PATH = params.DATA / "demo" / "twin" / "clan.json"


def build() -> dict[str, Any]:
    """Deterministic: scans seeds from SEED and returns the first clan that reads well on screen: at least
    three at-risk couples are findable by the cascade. This choice is stated on the page; the claim about
    strategies rests on benchmark B4 over many clans, not on this one."""
    seed = SEED
    while True:
        c = _candidate(seed)
        seed += 1
        if c is None:
            continue
        out = _assemble(c)
        if out["race"]["ranked"] and out["race"]["ranked"][-1]["total_couples"] >= 3:
            return out


def _assemble(c: dict[str, Any]) -> dict[str, Any]:
    k, ped, d, r, kmat, kidx = c["k"], c["ped"], c["d"], c["replicate"], c["kmat"], c["kidx"]
    index, mother, father = c["index"], c["mother"], c["father"]
    rng = np.random.default_rng(c["seed"] + 1)
    names = _names([(p, ped.people[p].sex.value) for p in ped.topological_order()], rng)

    base_people = []
    for pid in ped.topological_order():
        p = ped.people[pid]
        row = {"id": pid, "name": names[pid], "sex": p.sex.value, "mother": p.mother, "father": p.father,
               "generation": int(k.generation[pid]), "deceased": bool(p.deceased),
               "status": "unknown", "test": None}
        if pid == index:
            row["status"] = "affected"
            row["affected_with"] = c["index_phenotype"]
        if p.test is not None:
            row["test"] = {"detected": list(p.test.detected)}
        base_people.append(row)
    unions = [{"a": f, "b": m, "kinship": float(kmat[kidx[f], kidx[m]])} for f, m in c["couples"]]

    # cascade race (same acceptances and hidden results for both strategies)
    a = c["a"]
    rep = family_report(ped, params.load()[LOCUS].locus, background_f=params.load()[LOCUS].background_f)
    eligible = [p for p in ped.topological_order() if p not in (mother, father, index) and not ped.people[p].deceased
                and k.is_adult(p) and kmat[kidx[p], kidx[index]] > 0]
    partners: dict[str, list[str]] = {}
    couple_ids: dict[str, list[tuple[str, str]]] = {}
    for f, m in c["couples"]:
        if ped.people[f].deceased or ped.people[m].deceased:
            continue
        for x, y in ((f, m), (m, f)):
            partners.setdefault(x, []).append(y)
            couple_ids.setdefault(x, []).append((f, m))
    uptake = float(a["uae_uptake"])
    u = {p: rng.random() for p in sorted(ped.people)}

    def accept(p: str) -> bool:
        return u[p] < uptake

    def positive(p: str) -> bool:
        return bool(d.detected[p][r].any())

    loc = S.uae_truth_locus(LOCUS, 0.0, None)

    def detected(p: str) -> list[str]:
        return sorted(loc.alleles[int(x)].id for x, hit in zip(c["al"][p][r], d.detected[p][r]) if hit)

    ranked = [s.person_id for s in rep.invites if s.person_id in set(eligible)]
    rest = [p for p in eligible if p not in set(ranked)]
    family_order = list(eligible)  # topological: oldest generation first, as a family would usually go
    ranked_order = ranked + rest
    race = {
        "uptake": uptake,
        "ranked": _race(ranked_order, partners, positive, accept, {mother, father}, couple_ids, (mother, father), detected),
        "family_order": _race(family_order, partners, positive, accept, {mother, father}, couple_ids, (mother, father),
                              detected),
        "true_atrisk_couples": [list(x) for x in c["true_risk"]],
    }
    return {
        "locus_id": LOCUS, "seed": c["seed"], "replicate": r, "index": index, "parents": [mother, father],
        "people": base_people, "unions": unions,
        "consanguineous": [list(x) for x in c["consang"]],
        "race": race,
        "truth": {p: bool(d.carrier_any[p][r]) for p in ped.people},  # revealed only through the race
        "note": ("Fictional clan simulated with benchmark B4's model and assumptions. Not real people. Chosen as "
                 "the first seed from 20261115 in which at least three at-risk couples can be found."),
    }


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    import json
    return json.loads(CLAN_PATH.read_text())


def public() -> dict[str, Any]:
    """Everything the page needs except the hidden truth (which only the race reveals, one test at a time)."""
    t = load()
    return {k: v for k, v in t.items() if k != "truth"}


def what_if(results: dict[str, str]) -> dict[str, Any]:
    """Exact carrier chances for everyone after recording extra results: {person_id: 'carrier' | 'clear'}.
    'carrier' records the beta-thalassaemia variant B; 'B' or 'S' a specific variant; 'clear' a negative test
    (the detection rate leaves a small residual chance)."""
    t = load()
    rec = params.load()[LOCUS]
    people = []
    for row in t["people"]:
        p = Person(row["id"], _sex(row["sex"]), row["mother"], row["father"], deceased=row["deceased"])
        if row["status"] == "affected":
            p.phenotype = Phenotype(row["affected_with"])
        if row["test"] is not None:
            p.test = TestResult(tuple(row["test"]["detected"]))
        res = results.get(row["id"])
        if res is not None:
            p.test = TestResult(() if res == "clear" else ("B",) if res == "carrier" else tuple(res.split(",")))
        people.append(p)
    ped = Pedigree.from_people(people)
    t0 = time.perf_counter()
    try:
        rep = family_report(ped, rec.locus, background_f=rec.background_f)
    except InconsistentEvidence:
        return {"status": "inconsistent", "ms": round(1000 * (time.perf_counter() - t0), 1)}
    ms = 1000 * (time.perf_counter() - t0)
    founders = [p["id"] for p in t["people"] if p["mother"] is None and p["father"] is None]
    return {
        "status": "ok", "ms": round(ms, 1), "people_count": len(people),
        "p_carrier": {pid: round(r.p_any_pathogenic, 6) for pid, r in rep.people.items()},
        "founders": sorted(({"id": f, "p": round(rep.people[f].p_any_pathogenic, 6)} for f in founders),
                           key=lambda x: -x["p"]),
        "next_best": [s.person_id for s in rep.invites[:5]],
    }


def _sex(s: str):
    from .engine.pedigree import Sex
    return Sex.FEMALE if s == "female" else Sex.MALE


if __name__ == "__main__":
    import json

    t = build()
    CLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLAN_PATH.write_text(json.dumps(t, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {CLAN_PATH}: seed {t['seed']}, {len(t['people'])} people, {len(t['consanguineous'])} cousin "
          f"marriages, ranked {[e['total_couples'] for e in t['race']['ranked']]}, "
          f"family order {[e['total_couples'] for e in t['race']['family_order']]}")
