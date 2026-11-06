"""B1 - Engine correctness.

1. Hand-derivable textbook cases (closed-form expected values).
2. Random consanguineous pedigrees with random consistent evidence: the
   engine's exact posteriors against pgmpy's exact VariableElimination on an
   independently built Bayesian network.
3. Monte Carlo gene dropping (likelihood weighting) against the engine:
   z-scores of the difference; about 95% should fall inside +-1.96.

Every case is logged to docs/evidence/logs/b1_*.csv.
"""

from __future__ import annotations

import argparse
import warnings

import numpy as np

from silsila import params
from silsila.engine import (
    Allele, InconsistentEvidence, Locus, Pedigree, Person, Phenotype, Sex, TestResult, Union,
    couple_risk, marginals,
)
from silsila.engine.inference import couple_joint, phenotype_likelihood, test_likelihood
from silsila.engine.montecarlo import effective_sample_size, gene_drop, mc_marginal
from silsila.sim.genedrop import TruthModel, derive, drop
from silsila.sim.kindred import KindredConfig, generate_kindred

from .common import Timer, mapper, provenance, write_csv, write_json

TOL = 1e-9


# ------------------------------------------------------------------ loci --
def biallelic(q: float, d: float = 1.0) -> Locus:
    return Locus("t", "TEST", (Allele("N", "ref", 1 - q, False), Allele("a", "path", q, True, d)),
                 {("N", "a"): "carrier", ("a", "a"): "affected"}, frozenset({"affected"}))


def hbb_like(qs: float, qb: float) -> Locus:
    return Locus("t-hbb", "HBB", (Allele("N", "ref", 1 - qs - qb, False), Allele("S", "HbS", qs, True), Allele("B", "bthal", qb, True)),
                 {("N", "S"): "trait", ("B", "N"): "bthal carrier", ("S", "S"): "SCD", ("B", "S"): "S-bthal", ("B", "B"): "bthal major"},
                 frozenset({"SCD", "S-bthal", "bthal major"}))


def alpha_like(q1: float, q2: float) -> Locus:
    return Locus("t-hba", "HBA", (Allele("aa", "two", 1 - q1 - q2, False), Allele("-a", "single", q1, True), Allele("--", "double", q2, True)),
                 {("-a", "aa"): "silent", ("-a", "-a"): "trait", ("--", "aa"): "trait", ("--", "-a"): "HbH", ("--", "--"): "Barts"},
                 frozenset({"HbH", "Barts"}))


def P(pid, sex, mo=None, fa=None, **kw):
    return Person(pid, Sex.FEMALE if sex == "F" else Sex.MALE, mo, fa, **kw)


def carrier(loc, post):
    return float(sum(post[k] for k, g in enumerate(loc.genotypes) if loc.pathogenic_copies(g) == 1))


def fc_family(extra=()):
    return [P("GM", "F"), P("GF", "M"), P("D1", "F", "GM", "GF"), P("S1", "M", "GM", "GF"), P("H1", "M"), P("W1", "F"),
            P("C1", "F", "D1", "H1"), P("C2", "M", "W1", "S1"), *extra]


def dfc_family():
    return [P("Am", "F"), P("Af", "M"), P("Bm", "F"), P("Bf", "M"), P("A1", "M", "Am", "Af"), P("A2", "M", "Am", "Af"),
            P("B1", "F", "Bm", "Bf"), P("B2", "F", "Bm", "Bf"), P("X", "F", "B1", "A1"), P("Y", "M", "B2", "A2")]


def sc_family():
    return fc_family([P("O1", "M"), P("O2", "F"), P("G1", "F", "C1", "O1"), P("G2", "M", "O2", "C2")])


# ----------------------------------------------------------- textbook --
def textbook_cases() -> list[dict]:
    cases: list[dict] = []

    def add(cid, desc, expected, actual, tol=TOL, ref=""):
        err = abs(expected - actual)
        cases.append({"case_id": cid, "description": desc, "expected": expected, "actual": actual,
                      "abs_error": err, "tolerance": tol, "pass": err <= tol, "reference": ref, "error_source": ""})

    mal = "Malecot 1948 kinship"
    fc = Pedigree.from_people(fc_family())
    add("K01", "kinship siblings", 1 / 4, fc.kinship("D1", "S1"), ref=mal)
    add("K02", "kinship first cousins", 1 / 16, fc.kinship("C1", "C2"), ref=mal)
    add("K03", "kinship uncle-niece", 1 / 8, fc.kinship("S1", "C1"), ref=mal)
    add("K04", "kinship double first cousins", 1 / 8, Pedigree.from_people(dfc_family()).kinship("X", "Y"), ref=mal)
    add("K05", "kinship second cousins", 1 / 64, Pedigree.from_people(sc_family()).kinship("G1", "G2"), ref=mal)
    hs = Pedigree.from_people([P("M1", "F"), P("M2", "F"), P("F", "M"), P("a", "F", "M1", "F"), P("b", "M", "M2", "F")])
    add("K06", "kinship half siblings", 1 / 8, hs.kinship("a", "b"), ref=mal)
    add("K07", "self-kinship, non-inbred", 1 / 2, fc.kinship("C1", "C1"), ref=mal)
    inb = Pedigree.from_people(fc_family([P("Z", "F", "C1", "C2"), P("Z2", "M", "C1", "C2")]))
    add("K08", "self-kinship, child of first cousins (1+1/16)/2", 17 / 32, inb.kinship("Z", "Z"), ref=mal)
    add("K09", "kinship parent-child", 1 / 4, fc.kinship("D1", "C1"), ref=mal)
    add("K10", "kinship grandparent-grandchild", 1 / 8, fc.kinship("GM", "C1"), ref=mal)
    add("K11", "kinship first cousin once removed", 1 / 32, Pedigree.from_people(sc_family()).kinship("C1", "G2"), ref=mal)
    add("K12", "kinship unrelated founders", 0.0, fc.kinship("GM", "GF"), ref=mal)
    add("K13", "inbreeding of offspring of first cousins", 1 / 16, fc.inbreeding_of_offspring("C1", "C2"), ref=mal)
    add("K14", "kinship of siblings whose parents are first cousins (1/4 + 1/32)", 9 / 32, inb.kinship("Z", "Z2"), ref=mal)

    hw = "Hardy-Weinberg"
    for i, q in enumerate([0.001, 0.0256, 0.1, 0.3]):
        post = marginals(Pedigree.from_people([P("x", "F")]), biallelic(q))["x"]
        add(f"H{i+1:02d}", f"founder carrier 2q(1-q), q={q}", 2 * q * (1 - q), carrier(biallelic(q), post), ref=hw)
    for i, (q, f) in enumerate([(0.01, 0.0222), (0.05, 0.0222)]):
        post = marginals(Pedigree.from_people([P("x", "F")]), biallelic(q), background_f=f)["x"]
        add(f"H{5+2*i:02d}", f"founder affected q^2+Fq(1-q), q={q}, F={f}", q * q + f * q * (1 - q), float(post[2]), ref="Wright 1922")
        add(f"H{6+2*i:02d}", f"founder carrier 2q(1-q)(1-F), q={q}, F={f}", 2 * q * (1 - q) * (1 - f), float(post[1]), ref="Wright 1922")

    wr = "Wright 1922: P(affected) = q^2 + phi q(1-q)"
    rels = [("first cousins", fc_family(), "C1", "C2", 1 / 16), ("double first cousins", dfc_family(), "X", "Y", 1 / 8),
            ("second cousins", sc_family(), "G1", "G2", 1 / 64), ("uncle-niece", fc_family(), "C1", "S1", 1 / 8)]
    n = 0
    for name, ppl, a, b, phi in rels:
        ped = Pedigree.from_people(ppl, [Union(a, b)] if name == "uncle-niece" else None)
        for q in (0.001, 0.01, 0.05):
            n += 1
            add(f"W{n:02d}", f"child of {name}, q={q}", q * q + phi * q * (1 - q), couple_risk(ped, biallelic(q), a, b).p_child_affected, ref=wr)
    for q in (0.01, 0.05):
        n += 1
        f = 0.0222
        add(f"W{n:02d}", f"child of first cousins, founders inbred F={f}, q={q}: q^2+(1+F)/16 q(1-q)",
            q * q + (1 + f) / 16 * q * (1 - q), couple_risk(Pedigree.from_people(fc_family()), biallelic(q), "C1", "C2", background_f=f).p_child_affected, ref=wr)

    yg = "Young 2006, Introduction to Risk Calculation in Genetic Counselling"
    for i, q in enumerate([1e-4, 0.01, 0.1]):
        ppl = [P("M", "F", phenotype=Phenotype(None)), P("F", "M", phenotype=Phenotype(None)),
               P("kid", "M", "M", "F", phenotype=Phenotype("affected")), P("sib", "F", "M", "F", phenotype=Phenotype(None))]
        m = marginals(Pedigree.from_people(ppl), biallelic(q))
        add(f"O{i+1:02d}", f"mother of affected child is obligate carrier, q={q}", 1.0, carrier(biallelic(q), m["M"]), ref=yg)
        add(f"S{i+1:02d}", f"unaffected sibling of affected child = 2/3, q={q}", 2 / 3, carrier(biallelic(q), m["sib"]), ref=yg)
    loc = biallelic(1e-7)
    ppl = [P("GM", "F", phenotype=Phenotype(None)), P("GF", "M", phenotype=Phenotype(None)), P("Mo", "F", "GM", "GF", phenotype=Phenotype(None)),
           P("Aunt", "F", "GM", "GF", phenotype=Phenotype(None)), P("Fa", "M", phenotype=Phenotype(None)),
           P("kid", "M", "Mo", "Fa", phenotype=Phenotype("affected"))]
    add("A01", "aunt of affected child -> 1/2 (rare allele limit)", 0.5, carrier(loc, marginals(Pedigree.from_people(ppl), loc)["Aunt"]), tol=1e-5, ref=yg)
    ped = Pedigree.from_people(fc_family([]))
    ped.people["C1"].test = TestResult(("a",))
    add("A02", "first cousin of a tested carrier -> 1/8 (rare allele limit)", 1 / 8, carrier(loc, marginals(ped, loc)["C2"]), tol=1e-5,
        ref="IBD path 1/2 x 1/2 x 1/2")

    rr = "Bayes: c(1-d)/(c(1-d)+(1-c))"
    for i, (q, d) in enumerate([(0.02, 0.9), (0.05, 0.95), (0.1, 0.99), (0.0072, 0.912)]):
        lc = biallelic(q, d)
        c = 2 * q * (1 - q) / (1 - q * q)
        post = marginals(Pedigree.from_people([P("x", "F", phenotype=Phenotype(None), test=TestResult(()))]), lc)["x"]
        add(f"R{i+1:02d}", f"residual carrier risk after negative test, q={q}, d={d}", c * (1 - d) / (c * (1 - d) + (1 - c)), carrier(lc, post), ref=rr)
    add("R05", "negative test with detection 1.0 excludes carrier", 0.0,
        carrier(biallelic(0.05), marginals(Pedigree.from_people([P("x", "F", test=TestResult(()))]), biallelic(0.05))["x"]), ref=rr)

    mend = "Mendel"

    def cr(loc, tw, th, wph=None, hph=None, f=0.0):
        w = P("W", "F", test=tw, phenotype=wph)
        h = P("H", "M", test=th, phenotype=hph)
        return couple_risk(Pedigree.from_people([w, h], [Union("W", "H")]), loc, "W", "H", background_f=f)

    for i, q in enumerate([0.01, 0.05]):
        add(f"M{i+1:02d}", f"tested carrier x untested unrelated: child affected q/2, q={q}", q / 2, cr(biallelic(q), TestResult(("a",)), None).p_child_affected, ref=mend)
        add(f"M{i+3:02d}", f"affected x untested unrelated: child affected q, q={q}", q, cr(biallelic(q), None, None, Phenotype("affected")).p_child_affected, ref=mend)
    c2 = cr(biallelic(0.05), TestResult(("a",)), TestResult(("a",)))
    add("M05", "two tested carriers: child affected 1/4", 0.25, c2.p_child_affected, ref=mend)
    add("M06", "two tested carriers: child carrier 1/2", 0.5, c2.child_phenotypes["carrier"], ref=mend)
    add("M07", "affected x tested carrier: child affected 1/2", 0.5, cr(biallelic(0.05), TestResult(("a",)), None, None, Phenotype("affected")).p_child_affected, ref=mend)
    add("M08", "affected x affected: child affected 1", 1.0, cr(biallelic(0.05), None, None, Phenotype("affected"), Phenotype("affected")).p_child_affected, ref=mend)
    hb = cr(hbb_like(0.02, 0.04), TestResult(("S",)), TestResult(("B",)))
    add("M09", "HbS trait x beta-thal carrier: sickle beta-thal 1/4", 0.25, hb.child_phenotypes["S-bthal"], ref=mend)
    add("M10", "HbS trait x beta-thal carrier: both carry = 1", 1.0, hb.p_both_carry, ref=mend)
    al = alpha_like(0.2, 0.01)
    add("M11", "--/aa x -a/aa: HbH 1/4", 0.25, cr(al, TestResult(("--",)), TestResult(("-a",))).child_phenotypes["HbH"], ref=mend)
    add("M12", "-a/-a x --/aa: HbH 1/2", 0.5, cr(al, TestResult(("-a", "-a")), TestResult(("--",))).child_phenotypes["HbH"], ref=mend)
    add("M13", "--/aa x --/aa: Barts 1/4", 0.25, cr(al, TestResult(("--",)), TestResult(("--",))).child_phenotypes["Barts"], ref=mend)
    add("M14", "unrelated untested couple baseline equals q^2 (F=0)", 0.05 ** 2, cr(biallelic(0.05), None, None).p_child_affected, ref=hw)

    # sourced loci: founders reproduce the published inputs
    reg = params.register()
    for e in reg["loci"]:
        rec = params.load()[e["id"]]
        post = marginals(Pedigree.from_people([P("x", "F")]), rec.locus, background_f=rec.background_f)["x"]
        lc = rec.locus
        for a in e["alleles"]:
            kh = lc.genotype_index[tuple(sorted((0, lc.allele_index[a["id"]])))]
            kk = lc.genotype_index[(lc.allele_index[a["id"]],) * 2]
            if a["published_measure"] == "heterozygote_proportion":
                exp, act = a["published_value"], float(post[kh])
            elif a["published_measure"] == "detected_heterozygote_proportion":
                exp, act = a["published_value"], float(post[kh]) * a["detection_rate"]
            else:
                exp, act = a["published_value"], float(post[kk])
            add(f"P-{e['id']}-{a['id']}", f"{e['id']} founder reproduces published {a['published_measure']}", exp, act, tol=1e-12,
                ref=a["source"]["citation"][:80])
    return cases


# ------------------------------------------------------- pgmpy cross-check --
def pgmpy_posteriors(ped: Pedigree, locus: Locus, targets: list[str], background_f: float, extra_child=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            from pgmpy.models import DiscreteBayesianNetwork as BN
        except ImportError:  # pragma: no cover
            from pgmpy.models import BayesianNetwork as BN
        from pgmpy.factors.discrete import TabularCPD
        from pgmpy.inference import VariableElimination
    n = locus.n_genotypes
    prior = locus.founder_prior(background_f)
    trans = locus.transmission.reshape(n * n, n).T
    edges, cpds, evidence = [], [], {}
    for pid in ped.topological_order():
        p = ped.people[pid]
        if p.mother is None:
            cpds.append(TabularCPD(pid, n, prior.reshape(n, 1)))
        else:
            edges += [(p.mother, pid), (p.father, pid)]
            cpds.append(TabularCPD(pid, n, trans, evidence=[p.mother, p.father], evidence_card=[n, n]))
        liks = []
        if p.phenotype is not None:
            liks.append(phenotype_likelihood(locus, p.phenotype))
        if p.test is not None:
            liks.append(test_likelihood(locus, p.test))
        for k, lik in enumerate(liks):
            ev = f"ev_{pid}_{k}"
            edges.append((pid, ev))
            cpds.append(TabularCPD(ev, 2, np.vstack([1 - lik, lik]), evidence=[pid], evidence_card=[n]))
            evidence[ev] = 1
    if extra_child:
        name, (m, f) = extra_child
        edges += [(m, name), (f, name)]
        cpds.append(TabularCPD(name, n, trans, evidence=[m, f], evidence_card=[n, n]))
    model = BN(edges)
    for pid in ped.people:
        if pid not in model.nodes():
            model.add_node(pid)
    model.add_cpds(*cpds)
    infer = VariableElimination(model)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {t: np.asarray(infer.query([t], evidence=evidence, show_progress=False).values) for t in targets}


RANDOM_CFG = KindredConfig(n_generations=4, sibship_mean=2.3, marriage_prob=0.85, p_living_grandparent_gen=0.7,
                           request_mix={"first_cousin": 0.35, "double_first_cousin": 0.15, "second_cousin": 0.1,
                                        "same_clan": 0.2, "other_clan": 0.2})


def random_locus(rng: np.random.Generator) -> tuple[str, Locus, float]:
    kind = int(rng.integers(6))
    if kind == 0:
        q = float(rng.uniform(0.005, 0.2))
        d = float(rng.choice([1.0, 0.9, 0.95]))
        return f"biallelic(q={q:.4f},d={d})", biallelic(q, d), 0.0
    if kind == 1:
        return "hbb_like(0.05,0.08)", hbb_like(0.05, 0.08), 0.0
    if kind == 2:
        return "alpha_like(0.25,0.05)", alpha_like(0.25, 0.05), 0.0
    lid = ["HBB", "CYP21A2", "SMN1"][kind - 3]
    rec = params.load()[lid]
    return f"{lid}(sourced,F={rec.background_f})", rec.locus, rec.background_f


def make_case(seed: int, max_people: int = 40):
    """A random consanguineous pedigree with random consistent evidence."""
    rng = np.random.default_rng(seed)
    while True:
        k = generate_kindred(RANDOM_CFG, rng)
        if 4 <= len(k.pedigree.people) <= max_people:
            break
    name, loc, f = random_locus(rng)
    ped = k.pedigree
    al = drop(ped, {}, TruthModel(loc, 0.0, f), 1, rng)
    d = derive(TruthModel(loc, 0.0, f), al, rng)
    frac = float(rng.uniform(0.15, 0.5))
    for pid, p in ped.people.items():
        if rng.random() > frac:
            continue
        gk = int(d.genotype[pid][0])
        if rng.random() < 0.5:
            ph = loc.phenotype_vector[gk]
            p.phenotype = Phenotype(ph if ph in loc.affected_phenotypes else None)
        else:
            p.test = TestResult(tuple(sorted(loc.alleles[int(a)].id for a, h in zip(al[pid][0], d.detected[pid][0]) if h)))
    loops = sum(1 for c in k.couples if c.kinship > 0)
    return rng, ped, name, loc, f, loops


def pgmpy_job(seed: int) -> list[dict]:
    rng, ped, name, loc, f, loops = make_case(seed)
    ids = sorted(ped.people)
    targets = [ids[int(i)] for i in rng.choice(len(ids), size=min(2, len(ids)), replace=False)]
    rows = []
    base = {"pedigree_seed": seed, "locus": name, "background_f": f, "n_people": len(ped.people), "consanguineous_loops": loops}
    try:
        ours = marginals(ped, loc, targets, background_f=f)
        ref = pgmpy_posteriors(ped, loc, targets, f)
        for t in targets:
            err = float(np.max(np.abs(ours[t] - ref[t])))
            rows.append({**base, "case_id": f"pg{seed}-{t}", "query": f"marginal {t}", "expected": ref[t].tolist(),
                         "actual": ours[t].tolist(), "abs_error": err, "pass": err <= TOL, "error_source": ""})
        couples = ped.couples()
        if couples:
            fm = couples[int(rng.integers(len(couples)))]
            _, child = couple_joint(ped, loc, fm[0], fm[1], background_f=f)
            refc = pgmpy_posteriors(ped, loc, ["vchild"], f, ("vchild", fm))["vchild"]
            err = float(np.max(np.abs(child - refc)))
            rows.append({**base, "case_id": f"pg{seed}-child", "query": f"future child of {fm[0]} x {fm[1]}", "expected": refc.tolist(),
                         "actual": child.tolist(), "abs_error": err, "pass": err <= TOL, "error_source": ""})
    except InconsistentEvidence as e:  # evidence is simulated, so this would be an engine error
        rows.append({**base, "case_id": f"pg{seed}", "query": "all", "expected": "consistent", "actual": "InconsistentEvidence",
                     "abs_error": float("nan"), "pass": False, "error_source": f"engine: {e}"})
    return rows


def mc_job(seed: int, n: int = 100_000) -> list[dict]:
    rng, ped, name, loc, f, loops = make_case(10_000_000 + seed, max_people=60)
    ours = marginals(ped, loc, background_f=f)
    genos, w = gene_drop(ped, loc, n=n, seed=seed, background_f=f)
    ess = effective_sample_size(w)
    rows = []
    if ess < 200:
        return [{"case_id": f"mc{seed}", "pedigree_seed": 10_000_000 + seed, "locus": name, "n_people": len(ped.people), "ess": ess,
                 "skipped": True}]
    for pid in sorted(ped.people):
        mc = mc_marginal(genos[pid], w, loc.n_genotypes)
        for k in range(loc.n_genotypes):
            p = float(ours[pid][k])
            se = np.sqrt(max(p * (1 - p), 1e-12) / ess)
            if p < 1e-12 or p > 1 - 1e-12:
                z = 0.0 if abs(mc[k] - p) < 1e-12 else float("inf")
                det = True
            else:
                z = float((mc[k] - p) / se)
                det = False
            rows.append({"case_id": f"mc{seed}-{pid}-{k}", "pedigree_seed": 10_000_000 + seed, "locus": name, "n_people": len(ped.people),
                         "ess": ess, "person": pid, "genotype": loc.genotype_label(loc.genotypes[k]), "expected": p,
                         "actual": float(mc[k]), "abs_error": abs(float(mc[k]) - p), "z": z, "deterministic": det,
                         "pass": abs(z) <= 5, "skipped": False})
    return rows


def run(quick: bool, seed: int = 20261106) -> dict:
    tm = Timer()
    cases = textbook_cases()
    write_csv("b1_textbook_cases.csv", cases, ["case_id", "description", "expected", "actual", "abs_error", "tolerance", "pass", "reference", "error_source"])
    n_pg = 400 if quick else 10_000
    pg_rows = [r for chunk in mapper(pgmpy_job, [seed + i for i in range(n_pg)]) for r in chunk]
    write_csv("b1_pgmpy_crosscheck.csv", pg_rows, ["case_id", "pedigree_seed", "locus", "background_f", "n_people", "consanguineous_loops",
                                                    "query", "expected", "actual", "abs_error", "pass", "error_source"])
    n_mc = 40 if quick else 300
    mc_rows = [r for chunk in mapper(mc_job, list(range(n_mc))) for r in chunk]
    write_csv("b1_montecarlo.csv", mc_rows, ["case_id", "pedigree_seed", "locus", "n_people", "ess", "person", "genotype", "expected",
                                             "actual", "abs_error", "z", "deterministic", "pass", "skipped"])
    errs = np.array([r["abs_error"] for r in pg_rows if r["abs_error"] == r["abs_error"]])
    zs = np.array([r["z"] for r in mc_rows if not r.get("skipped") and not r["deterministic"]])
    peds = {r["pedigree_seed"] for r in pg_rows}
    sizes = [r["n_people"] for r in pg_rows]
    loops = [r["consanguineous_loops"] for r in pg_rows]
    from silsila.sim.stats import exact_ci
    n_in = int(np.sum(np.abs(zs) <= 1.96))
    out = {
        "benchmark": "B1 engine correctness",
        "provenance": provenance(quick, seed),
        "textbook": {
            "n_cases": len(cases), "n_pass": sum(c["pass"] for c in cases),
            "max_abs_error": max(c["abs_error"] for c in cases),
            "failures": [c for c in cases if not c["pass"]],
            "log": "docs/evidence/logs/b1_textbook_cases.csv",
        },
        "pgmpy_crosscheck": {
            "n_pedigrees": len(peds), "n_queries": len(pg_rows),
            "pedigree_size_median": float(np.median(sizes)), "pedigree_size_max": int(max(sizes)),
            "pct_pedigrees_with_consanguineous_loop": 100 * float(np.mean([1 if l > 0 else 0 for l in loops])),
            "max_abs_error": float(errs.max()), "median_abs_error": float(np.median(errs)),
            "pct_within_1e-9": 100 * float(np.mean(errs <= TOL)),
            "pct_within_1e-9_ci95": [100 * x for x in exact_ci(int(np.sum(errs <= TOL)), len(errs))],
            "n_engine_errors": sum(1 for r in pg_rows if r["error_source"]),
            "log": "docs/evidence/logs/b1_pgmpy_crosscheck.csv",
        },
        "montecarlo": {
            "n_pedigrees": len({r["pedigree_seed"] for r in mc_rows if not r.get("skipped")}),
            "n_skipped_low_ess": sum(1 for r in mc_rows if r.get("skipped")),
            "draws_per_pedigree": 100_000,
            "n_genotype_probabilities": int(len(zs)),
            "pct_abs_z_le_1.96": 100 * n_in / len(zs), "pct_abs_z_le_1.96_ci95": [100 * x for x in exact_ci(n_in, len(zs))],
            "expected_pct_if_exact": 95.0,
            "max_abs_z": float(np.max(np.abs(zs))), "max_abs_error": float(max(r["abs_error"] for r in mc_rows if not r.get("skipped"))),
            "deterministic_mismatches": sum(1 for r in mc_rows if not r.get("skipped") and r["deterministic"] and not r["pass"]),
            "note": "z = (MC - exact)/sqrt(p(1-p)/ESS). z-scores within one pedigree are correlated, so the coverage interval is approximate.",
            "log": "docs/evidence/logs/b1_montecarlo.csv",
        },
        "runtime_seconds": tm(),
    }
    write_json("b1_engine.json", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    r = run(ap.parse_args().quick)
    print({k: r[k] for k in ("textbook", "pgmpy_crosscheck", "montecarlo")})
