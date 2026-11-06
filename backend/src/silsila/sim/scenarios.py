"""Benchmark scenarios on synthetic kindreds (SYNTHETIC DATA).

(a) Ahmed et al., NEJM 2002 (PMID 12374877) reproduction: Pakistani extended
    families ascertained through a child with beta-thalassaemia major.
(b) UAE projection with the sourced loci in data/params/loci.yaml: cascade
    testing after a newborn diagnosis, ranked by the Silsila engine versus
    unranked, versus testing random couples.

Ascertainment is by rejection sampling: a family structure is generated from
the structural prior, R genotype replicates are dropped through it, and every
replicate that contains an affected child is accepted. This samples exactly
from P(structure, genotypes | at least one affected child) ('complete'
ascertainment), so larger and more consanguineous families and high-frequency
clans are over-represented exactly as in a clinic-ascertained series, with no
approximation. To bound the cost per structure, at most `cap` accepted
replicates are kept and each is weighted by (accepted / kept), which keeps the
estimator unbiased. 'single' ascertainment multiplies the weight by the number
of affected children.

Workers take and return plain dicts so they can run in a process pool.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

import numpy as np

from .. import params
from ..engine import InconsistentEvidence, Locus, Pedigree, Person, Phenotype, TestResult, family_report
from .genedrop import TruthModel, derive, drop
from .kindred import CONSANGUINEOUS, Kindred, KindredConfig, _ancestors_at, calibrate_request_mix, generate_kindred, kinship_matrix
from .sources import ahmed, ahmed_per_family, denic2013, nejm_mix, uae_mix

Mapper = Callable[[Callable, list], list]


# ================================================================== loci ==
def _hetero_entry(lid: str, h: float, detection: float | None, label: str) -> dict[str, Any]:
    return {
        "id": lid,
        "gene": "HBB",
        "display": label,
        "reference_allele": {"id": "N", "label": "typical"},
        "alleles": [{"id": "b", "label": label, "published_measure": "heterozygote_proportion",
                     "published_value": h, "detection_rate": detection}],
        "phenotypes": [
            {"genotype": ["N", "b"], "label": "carrier", "affected": False},
            {"genotype": ["b", "b"], "label": "beta-thalassaemia major", "affected": True},
        ],
    }


def nejm_truth_locus(total_f: float, sensitivity: float) -> Locus:
    """Biallelic beta-thalassaemia locus with the population carrier rate of
    Ahmed 2002 (5%), converted to an allele frequency by the same formula as
    silsila.params, using the founders' total inbreeding so that simulated
    founders show exactly 5% carriers."""
    h = ahmed()["population_bthal_carrier_freq"]
    return params.build_locus(_hetero_entry("NEJM-bthal", h, sensitivity, "beta-thalassaemia variant"), total_f).locus


def denic_truth_locus(total_f: float) -> Locus:
    """Beta-thalassaemia carrier rate of Abu Dhabi premarital couples (Denic 2013: 2.3%)."""
    return params.build_locus(_hetero_entry("DENIC-bthal", denic2013()["bthal_carrier_freq"], 1.0, "beta-thalassaemia variant"), total_f).locus


def uae_truth_locus(locus_id: str, total_f: float, detection_override: float | None = None) -> Locus:
    """Sourced UAE locus, re-derived with the founders' total inbreeding so the
    simulated population reproduces the published carrier rate / incidence."""
    entry = dict(params.register()["loci"][[e["id"] for e in params.register()["loci"]].index(locus_id)])
    if detection_override is not None:
        entry["alleles"] = [dict(a, detection_rate=a.get("detection_rate") or detection_override) for a in entry["alleles"]]
    return params.build_locus(entry, total_f).locus


def engine_record(locus_id: str):
    return params.load()[locus_id]


# ========================================================= couple types ==
def couple_type_pedigree(t: str) -> tuple[Pedigree, dict[str, int], str, str]:
    """Small pedigree for one couple of type t, with founder clans."""
    F, M = "female", "male"
    from ..engine import Sex

    def P(pid, sex, mo=None, fa=None):
        return Person(pid, Sex.FEMALE if sex == F else Sex.MALE, mo, fa)

    if t == "first_cousin":
        people = [P("GM", F), P("GF", M), P("D1", F, "GM", "GF"), P("S1", M, "GM", "GF"), P("H1", M), P("W1", F),
                  P("X", F, "D1", "H1"), P("Y", M, "W1", "S1")]
        clan = {"GM": 0, "GF": 0, "H1": 0, "W1": 0}
    elif t == "double_first_cousin":
        people = [P("Am", F), P("Af", M), P("Bm", F), P("Bf", M), P("A1", M, "Am", "Af"), P("A2", M, "Am", "Af"),
                  P("B1", F, "Bm", "Bf"), P("B2", F, "Bm", "Bf"), P("X", F, "B1", "A1"), P("Y", M, "B2", "A2")]
        clan = {"Am": 0, "Af": 0, "Bm": 0, "Bf": 0}
    elif t == "second_cousin":
        people = [P("GM", F), P("GF", M), P("D1", F, "GM", "GF"), P("S1", M, "GM", "GF"), P("H1", M), P("W1", F),
                  P("C1", F, "D1", "H1"), P("C2", M, "W1", "S1"), P("O1", M), P("O2", F),
                  P("X", F, "C1", "O1"), P("Y", M, "O2", "C2")]
        clan = {"GM": 0, "GF": 0, "H1": 0, "W1": 0, "O1": 0, "O2": 0}
    elif t in ("same_clan", "distant_relative"):
        people = [P("X", F), P("Y", M)]
        clan = {"X": 0, "Y": 0}
    elif t == "other_clan":
        people = [P("X", F), P("Y", M)]
        clan = {"X": 1, "Y": 2}
    else:
        raise ValueError(t)
    return Pedigree.from_people(people), clan, "X", "Y"


def couple_type_rates(model: TruthModel, types: list[str], r: int, seed: int) -> dict[str, dict[str, float]]:
    """Per couple type: P(both carry), P(both test positive), P(woman carries),
    P(child affected), estimated from r simulated couples."""
    out = {}
    for k, t in enumerate(types):
        rng = np.random.default_rng(seed + 7919 * k)
        ped, clan, x, y = couple_type_pedigree(t)
        # add one child of the couple to measure P(child affected)
        from ..engine import Sex
        people = list(ped.people.values()) + [Person("kid", Sex.FEMALE, x, y)]
        ped2 = Pedigree.from_people(people)
        al = drop(ped2, clan, model, r, rng)
        d = derive(model, al, rng)
        pos_x, pos_y = d.detected[x].any(axis=1), d.detected[y].any(axis=1)
        out[t] = {
            "both_carry": float(np.mean(d.carrier_any[x] & d.carrier_any[y])),
            "both_test_positive": float(np.mean(pos_x & pos_y)),
            "woman_carries": float(np.mean(d.carrier_any[x])),
            "child_affected": float(np.mean(d.affected["kid"])),
            "n": r,
        }
    return out


def mix_rates(rates: dict[str, dict[str, float]], mix: dict[str, float]) -> dict[str, float]:
    keys = ["both_carry", "both_test_positive", "woman_carries", "child_affected"]
    tot = sum(mix.values())
    return {k: sum(mix[t] / tot * rates[t][k] for t in mix if mix[t] > 0) for k in keys}


# ===================================================== kindred configs ==
def kindred_config(a: dict[str, Any], scenario: str, request_mix: dict[str, float]) -> KindredConfig:
    return KindredConfig(
        n_generations=int(a["n_generations"]),
        sibship_mean=float(a["sibship_mean_nejm"] if scenario == "nejm" else a["sibship_mean_uae"]),
        marriage_prob=float(a["marriage_prob"]),
        p_living_grandparent_gen=float(a["p_living_grandparent_gen"]),
        request_mix=request_mix,
        exchange_prob=float(a["exchange_prob"]),
        generation_interval_years=float(a["generation_interval_years"]),
    )


def target_mix(a: dict[str, Any], scenario: str) -> dict[str, float]:
    return nejm_mix(a) if scenario == "nejm" else uae_mix(a)


def calibrated_config(a: dict[str, Any], scenario: str, seed: int = 11) -> tuple[KindredConfig, dict[str, Any]]:
    """Kindred config whose achieved couple mix matches the scenario target.
    Returns the config and a record {target, request, achieved}."""
    tgt = target_mix(a, scenario)
    base = kindred_config(a, scenario, tgt)
    req, ach = calibrate_request_mix(base, tgt, seed=seed)
    return kindred_config(a, scenario, req), {"target": tgt, "request": req, "achieved_in_calibration": ach}


def _cfg_dict(cfg: KindredConfig) -> dict[str, Any]:
    return asdict(cfg)


# ============================================================== helpers ==
def _accept(acc: np.ndarray, extra_w: np.ndarray, cap: int, rng: np.random.Generator) -> list[tuple[int, float]]:
    idx = np.flatnonzero(acc)
    if len(idx) == 0:
        return []
    kept = idx if len(idx) <= cap else rng.choice(idx, size=cap, replace=False)
    scale = len(idx) / len(kept)
    return [(int(r), float(scale * extra_w[r])) for r in sorted(kept)]


def _children_map(ped: Pedigree) -> dict[str, list[str]]:
    ch: dict[str, list[str]] = {p: [] for p in ped.people}
    for p in ped.people.values():
        if p.mother is not None:
            ch[p.mother].append(p.id)
            ch[p.father].append(p.id)  # type: ignore[index]
    return ch


# ======================================================== (a) NEJM 2002 ==
def nejm_worker(job: dict[str, Any]) -> list[dict[str, Any]]:
    """One generated structure -> accepted family records (index or control)."""
    rng = np.random.default_rng(job["seed"])
    cfg = KindredConfig(**job["cfg"])
    k = generate_kindred(cfg, rng)
    ped = k.pedigree
    model = TruthModel(nejm_truth_locus(job["theta"] + (1 - job["theta"]) * job["founder_f"], job["sensitivity"]),
                       job["theta"], job["founder_f"])
    R = job["replicates"]
    al = drop(ped, k.clan, model, R, rng)
    d = derive(model, al, rng)
    ids = list(ped.people)
    youngest = [p for p in ids if k.generation[p] == k.youngest]
    if not youngest:
        return []
    aff_y = np.stack([d.affected[p] for p in youngest])           # (ny, R)
    aff_all = np.stack([d.affected[p] for p in ids])
    if job["mode"] == "index":
        acc = aff_y.any(axis=0)
        w = aff_y.sum(axis=0).astype(float) if job["ascertainment"] == "single" else np.ones(R)
    else:
        acc = ~aff_all.any(axis=0)
        w = np.ones(R)
    kept = _accept(acc, w, job["cap"], rng)
    if not kept:
        return []

    living = [p for p in ids if not ped.people[p].deceased]
    couples = [(c.female, c.male, c.achieved) for c in k.couples
               if not ped.people[c.female].deceased and not ped.people[c.male].deceased]
    in_couple = {x for c in couples for x in c[:2]}
    ch = _children_map(ped)
    order, kmat = kinship_matrix(ped)
    kidx = {p: i for i, p in enumerate(order)}
    fracs = job["tested_fractions"]
    out = []
    for r, weight in kept:
        testable = [p for p in living if not d.affected[p][r]]
        frac = fracs[int(rng.integers(len(fracs)))]
        n_test = min(len(testable), int(round(frac * len(living))))
        if job["mode"] == "index" and job["tested_selection"] == "kin_first":
            affected_kids = [p for p in youngest if d.affected[p][r]]
            index = affected_kids[int(rng.integers(len(affected_kids)))]
            tie = rng.random(len(testable))
            keyed = sorted(range(len(testable)), key=lambda i: (-kmat[kidx[testable[i]], kidx[index]], tie[i]))
            tested = {testable[i] for i in keyed[:n_test]}
        else:
            sel = rng.choice(len(testable), size=n_test, replace=False) if n_test else []
            tested = {testable[i] for i in sel}
        pos = {p for p in tested if d.detected[p][r].any()}
        atrisk_true = atrisk_ident = both_tested = consang = 0
        for f, m, typ in couples:
            consang += typ in CONSANGUINEOUS
            if d.carrier_any[f][r] and d.carrier_any[m][r]:
                atrisk_true += 1
            history = any(d.affected[c][r] for c in ch[f] if c in ch[m])
            tested_pos = f in pos and m in pos
            both_tested += (f in tested and m in tested)
            if history or tested_pos:
                atrisk_ident += 1
        out.append({
            "structure": job["seed"], "weight": weight, "mode": job["mode"],
            "living": len(living), "tested": len(tested), "carriers": len(pos),
            "carriers_true_among_tested": int(sum(bool(d.carrier_any[p][r]) for p in tested)),
            "couples": len(couples), "consanguineous_couples": consang,
            "atrisk_identified": atrisk_ident, "atrisk_true": atrisk_true, "couples_both_tested": both_tested,
            "unmarried": len([p for p in living if p not in in_couple]),
            "affected_living_or_dead": int(aff_all[:, r].sum()),
        })
    return out


def nejm_jobs(a: dict[str, Any], cfg: KindredConfig, theta: float, mode: str, n: int, seed: int,
              replicates: int = 60, cap: int = 4) -> list[dict[str, Any]]:
    index_rows, control_rows = ahmed_per_family()
    rows = index_rows if mode == "index" else control_rows
    fracs = [row[4] / row[0] for row in rows]   # tested / living members, per published family
    base = {
        "cfg": _cfg_dict(cfg), "theta": theta, "founder_f": float(a["founder_f_nejm"]),
        "sensitivity": float(a["nejm_test_sensitivity"]), "replicates": replicates, "cap": cap, "mode": mode,
        "tested_selection": a["nejm_tested_selection"], "ascertainment": a["ascertainment"],
        "tested_fractions": fracs,
    }
    return [dict(base, seed=seed + i) for i in range(n)]


def nejm_antenatal(a: dict[str, Any], theta: float, r: int, seed: int) -> dict[str, Any]:
    model = TruthModel(nejm_truth_locus(theta + (1 - theta) * a["founder_f_nejm"], a["nejm_test_sensitivity"]),
                       theta, a["founder_f_nejm"])
    mix = nejm_mix(a)
    types = [t for t in mix if mix[t] > 0]
    rates = couple_type_rates(model, types, r, seed)
    return {"by_type": rates, "mix": mix, "mixed": mix_rates(rates, mix)}


# ================================================= (b) UAE projection ==
def drawn_tree(k: Kindred, index: str, scope: str) -> set[str]:
    """People a family would enter: descendants of the index child's
    grandparents (or great-grandparents), their partners, and every ancestor
    needed to connect them (so drawn consanguinity loops are kept)."""
    ped = k.pedigree
    tops = set(_ancestors_at(ped, index, 2 if scope == "grandparents" else 3))
    ch = _children_map(ped)
    desc: set[str] = set()
    stack = list(tops)
    while stack:
        x = stack.pop()
        for c in ch[x]:
            if c not in desc:
                desc.add(c)
                stack.append(c)
    partners: dict[str, set[str]] = {}
    for c in k.couples:
        partners.setdefault(c.female, set()).add(c.male)
        partners.setdefault(c.male, set()).add(c.female)
    core = set(tops) | desc
    for x in list(core):
        core |= partners.get(x, set())
    out = set(core)
    stack = list(core)
    while stack:
        x = stack.pop()
        p = ped.people[x]
        for par in (p.mother, p.father):
            if par is not None and par not in out:
                out.add(par)
                stack.append(par)
    return out


def _cascade(order, partners, positive, accept, pre_tested, couple_ids, repro, exclude):
    """Sequential testing: each accepted invitee is tested; each positive
    person's living partner is invited next. Returns per-test cumulative
    (at-risk couples found, of which reproductive-age, carriers found)."""
    tested = set(pre_tested)
    pos = {p for p in pre_tested if positive(p)}
    found: set[tuple[str, str]] = set()
    n_rep = n_car = 0
    hist: list[tuple[int, int, int]] = []

    def test(p):
        nonlocal n_rep, n_car
        tested.add(p)
        if positive(p):
            pos.add(p)
            n_car += 1
            for c in couple_ids.get(p, ()):
                if c != exclude and c not in found and c[0] in pos and c[1] in pos:
                    found.add(c)
                    n_rep += c in repro
        hist.append((len(found), n_rep, n_car))

    for x in order:
        if x in tested or not accept(x):
            continue
        test(x)
        if positive(x):
            for y in partners.get(x, ()):
                if y not in tested and accept(y):
                    test(y)
    return hist


def uae_worker(job: dict[str, Any]) -> list[dict[str, Any]]:
    rng = np.random.default_rng(job["seed"])
    cfg = KindredConfig(**job["cfg"])
    k = generate_kindred(cfg, rng)
    ped = k.pedigree
    rec = engine_record(job["locus_id"])
    bg_f = rec.background_f
    theta = job["theta"]
    total_f = theta + (1 - theta) * bg_f
    model = TruthModel(uae_truth_locus(job["locus_id"], total_f, job["detection_override"]), theta, bg_f)
    R = job["replicates"]
    al = drop(ped, k.clan, model, R, rng)
    d = derive(model, al, rng)
    youngest = [p for p in ped.people if k.generation[p] == k.youngest]
    if not youngest:
        return []
    aff_y = np.stack([d.affected[p] for p in youngest])
    acc = aff_y.any(axis=0)
    w = aff_y.sum(axis=0).astype(float) if job["ascertainment"] == "single" else np.ones(R)
    kept = _accept(acc, w, job["cap"], rng)
    out = []
    loc = model.locus
    eng_loc = rec.locus
    for r, weight in kept:
        affected_kids = [p for p in youngest if d.affected[p][r]]
        index = affected_kids[int(rng.integers(len(affected_kids)))]
        mother, father = ped.people[index].mother, ped.people[index].father
        members = drawn_tree(k, index, job["scope"])
        people = []
        for pid in sorted(members, key=lambda x: (k.generation[x], x)):
            src = ped.people[pid]
            p = Person(pid, src.sex, src.mother, src.father, deceased=src.deceased)
            if pid == index:
                p.phenotype = Phenotype(loc.phenotype_vector[int(d.genotype[pid][r])])
            elif job["living_phenotypes_known"] and not src.deceased:
                ph = loc.phenotype_vector[int(d.genotype[pid][r])]
                p.phenotype = Phenotype(ph if ph in loc.affected_phenotypes else None)
            if pid in (mother, father):
                a2 = al[pid][r]
                p.test = TestResult(tuple(sorted(loc.alleles[int(a)].id for a, hit in zip(a2, d.detected[pid][r]) if hit)))
            people.append(p)
        dped = Pedigree.from_people(people)
        t0 = time.perf_counter()
        try:
            rep = family_report(dped, eng_loc, background_f=bg_f)
            err = None
        except InconsistentEvidence as e:  # should not happen with simulated truth
            rep, err = None, str(e)
        t_engine = time.perf_counter() - t0
        _, kmat = kinship_matrix(dped)
        korder = dped.topological_order()
        kidx = {p: i for i, p in enumerate(korder)}
        eligible = [p for p in korder if p not in (mother, father, index)
                    and not dped.people[p].deceased and k.is_adult(p)
                    and kmat[kidx[p], kidx[index]] > 0]
        partners: dict[str, list[str]] = {}
        couple_ids: dict[str, list[tuple[str, str]]] = {}
        repro: set[tuple[str, str]] = set()
        all_couples = []
        for f, m in dped.couples():
            if dped.people[f].deceased or dped.people[m].deceased:
                continue
            c = (f, m)
            all_couples.append(c)
            partners.setdefault(f, []).append(m)
            partners.setdefault(m, []).append(f)
            couple_ids.setdefault(f, []).append(c)
            couple_ids.setdefault(m, []).append(c)
            if k.generation[f] == k.youngest - 1:
                repro.add(c)
        exclude = (mother, father)
        u_accept = {p: rng.random() for p in sorted(members)}

        def accept(p):
            return u_accept[p] < job["uptake"]

        def positive(p):
            return bool(d.detected[p][r].any())

        if rep is not None:
            ranked = [s.person_id for s in rep.invites if s.person_id in set(eligible)]
        else:
            ranked = []
        rest = [p for p in eligible if p not in set(ranked)]
        rest = [rest[i] for i in rng.permutation(len(rest))]
        ranked_order = ranked + rest
        unranked_order = [eligible[i] for i in rng.permutation(len(eligible))]
        pre = {mother, father}
        hist_r = _cascade(ranked_order, partners, positive, accept, pre, couple_ids, repro, exclude)
        hist_u = _cascade(unranked_order, partners, positive, accept, pre, couple_ids, repro, exclude)
        true_all = [c for c in all_couples if c != exclude and d.carrier_any[c[0]][r] and d.carrier_any[c[1]][r]]
        out.append({
            "structure": job["seed"], "weight": weight, "locus": job["locus_id"],
            "kindred_size": len(ped.people), "drawn_size": len(dped.people), "eligible": len(eligible),
            "parents_kinship": float(kmat[kidx[mother], kidx[father]]),
            "true_atrisk_all": len(true_all), "true_atrisk_repro": sum(c in repro for c in true_all),
            "engine_seconds": t_engine, "engine_error": err,
            "ranked": hist_r, "unranked": hist_u,
        })
    return out


def uae_jobs(a: dict[str, Any], cfg: KindredConfig, locus_id: str, theta: float, n: int, seed: int,
             replicates: int, cap: int = 2) -> list[dict[str, Any]]:
    base = {
        "cfg": _cfg_dict(cfg), "locus_id": locus_id, "theta": theta, "replicates": replicates, "cap": cap,
        "ascertainment": a["ascertainment"], "scope": a["uae_drawn_tree_scope"],
        "living_phenotypes_known": bool(a["uae_living_phenotypes_known"]), "uptake": float(a["uae_uptake"]),
        "detection_override": float(a["uae_detection_cyp21a2"]) if locus_id == "CYP21A2" else None,
    }
    return [dict(base, seed=seed + i) for i in range(n)]


def uae_random_couples(a: dict[str, Any], locus_id: str, theta: float, r: int, seed: int) -> dict[str, Any]:
    rec = engine_record(locus_id)
    total_f = theta + (1 - theta) * rec.background_f
    det = float(a["uae_detection_cyp21a2"]) if locus_id == "CYP21A2" else None
    model = TruthModel(uae_truth_locus(locus_id, total_f, det), theta, rec.background_f)
    mix = uae_mix(a)
    types = [t for t in mix if mix[t] > 0]
    rates = couple_type_rates(model, types, r, seed)
    return {"by_type": rates, "mix": mix, "mixed": mix_rates(rates, mix)}


def denic_check(a: dict[str, Any], theta: float, r: int, seed: int) -> dict[str, float]:
    """Random UAE couples, beta-thalassaemia at Denic 2013's carrier rate:
    P(both carriers) under the UAE mix at clan theta."""
    bg = params.register()["background_inbreeding"]["value"]
    total_f = theta + (1 - theta) * bg
    model = TruthModel(denic_truth_locus(total_f), theta, bg)
    mix = uae_mix(a)
    types = [t for t in mix if mix[t] > 0]
    return mix_rates(couple_type_rates(model, types, r, seed), mix)


def run(mapper: Mapper | None, fn: Callable, jobs: list) -> list:
    m = mapper or (lambda f, xs: list(map(f, xs)))
    res = m(fn, jobs)
    return [row for chunk in res for row in chunk]
