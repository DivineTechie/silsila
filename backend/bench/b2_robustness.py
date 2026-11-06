"""B2 - Input robustness.

Malformed, contradictory and impossible inputs are pushed through the same
path the app uses (build Locus -> Pedigree.from_people -> family_report, and
couple_risk / marginals where the case needs it). For each case:

  expected = "error"   a clear error is required (PedigreeError, ValueError,
                       KeyError) - malformed input;
           = "inconsistent"  InconsistentEvidence is required - results that
                       cannot all be true;
           = "ok"      a valid but unusual input; must NOT raise and must give
                       valid probabilities (checks for false alarms).

Outcomes: pass; SILENT FAILURE (bad input accepted without an error, or
invalid probabilities returned); unclear crash (an exception, but not one of
the documented types); false alarm (a valid input rejected). Every case is
logged with its input, expected and actual outcome and the module that raised.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from silsila import params
from silsila.engine import (
    Allele, InconsistentEvidence, Locus, Pedigree, PedigreeError, Person, Phenotype, Sex, TestResult, Union,
    couple_risk, family_report, marginals,
)

from .common import Timer, provenance, write_csv, write_json

CLEAR = (PedigreeError, ValueError, KeyError)  # InconsistentEvidence is a ValueError subclass


def biallelic(q=0.05, d=1.0, freqs=None):
    fr = freqs or (1 - q, q)
    return Locus("t", "TEST", (Allele("N", "ref", fr[0], False), Allele("a", "path", fr[1], True, d)),
                 {("N", "a"): "carrier", ("a", "a"): "affected"}, frozenset({"affected"}))


def sourced(lid):
    rec = params.load()[lid]
    return rec.locus, rec.background_f


LOCI: dict[str, Callable[[], tuple[Locus, float]]] = {
    "HBB": lambda: sourced("HBB"),
    "CYP21A2": lambda: sourced("CYP21A2"),
    "SMN1": lambda: sourced("SMN1"),
    "test-d1": lambda: (biallelic(0.05, 1.0), 0.0),
}
AFFECTED = {"HBB": "beta-thalassaemia major or intermedia", "CYP21A2": "classic congenital adrenal hyperplasia",
            "SMN1": "spinal muscular atrophy", "test-d1": "affected"}
PATH = {"HBB": "B", "CYP21A2": "c", "SMN1": "del", "test-d1": "a"}
DETECTION_ONE = {"CYP21A2", "test-d1"}   # detection rate 1.0 in the locus definition


def P(pid, sex, mo=None, fa=None, **kw):
    s = sex if not isinstance(sex, str) or sex not in ("F", "M") else (Sex.FEMALE if sex == "F" else Sex.MALE)
    return Person(pid, s, mo, fa, **kw)


# --------------------------------------------------------- family templates --
def nuclear():
    return [P("mum", "F"), P("dad", "M"), P("kid", "F", "mum", "dad"), P("kid2", "M", "mum", "dad")]


def cousins():
    return [P("GM", "F"), P("GF", "M"), P("D1", "F", "GM", "GF"), P("S1", "M", "GM", "GF"), P("H1", "M"), P("W1", "F"),
            P("C1", "F", "D1", "H1"), P("C2", "M", "W1", "S1"), P("kid", "M", "C1", "C2")]


def three_gen():
    return [P("GM", "F"), P("GF", "M"), P("mum", "F", "GM", "GF"), P("aunt", "F", "GM", "GF"), P("dad", "M"),
            P("kid", "F", "mum", "dad"), P("uncle_in_law", "M"), P("cousin", "M", "aunt", "uncle_in_law")]


TEMPLATES = {"nuclear": nuclear, "cousins": cousins, "three_gen": three_gen}


@dataclass
class Case:
    id: str
    category: str
    description: str
    expected: str
    build: Callable[[], dict[str, Any]]
    meta: dict[str, Any] = field(default_factory=dict)


def _find(people, pid):
    return next(p for p in people if p.id == pid)


def generate_cases() -> list[Case]:
    cases: list[Case] = []
    n = 0

    def add(cat, desc, expected, build):
        nonlocal n
        n += 1
        cases.append(Case(f"B2-{n:03d}", cat, desc, expected, build))

    def std(people, lid="HBB", unions=None, action=None, locus=None, bg=None):
        def b():
            loc, f = LOCI[lid]() if locus is None else (locus(), 0.0)
            return {"people": people(), "unions": unions or [], "locus": loc, "locus_name": lid if locus is None else "custom",
                    "bg": f if bg is None else bg, "action": action}
        return b

    # ---------------- structure errors --------------------------------------
    for tname, tmpl in TEMPLATES.items():
        children = [p.id for p in tmpl() if p.mother is not None]
        for cid in children:
            for drop_role in ("mother", "father"):
                def ppl(t=tmpl, c=cid, r=drop_role):
                    pp = t()
                    setattr(_find(pp, c), r, None)
                    return pp
                add("missing_parent", f"{tname}: {cid} has no {drop_role} recorded", "error", std(ppl))
        for cid in children[:2]:
            def ppl(t=tmpl, c=cid):
                pp = t()
                _find(pp, c).mother = "ghost_mother"
                return pp
            add("parent_not_in_tree", f"{tname}: {cid}'s mother is not in the tree", "error", std(ppl))
            def ppl2(t=tmpl, c=cid):
                pp = t()
                p = _find(pp, c)
                p.mother, p.father = p.father, p.mother
                return pp
            add("wrong_sex_parent", f"{tname}: {cid}'s mother and father swapped (wrong sex)", "error", std(ppl2))
            def ppl3(t=tmpl, c=cid):
                pp = t()
                p = _find(pp, c)
                p.father = p.mother
                return pp
            add("wrong_sex_parent", f"{tname}: {cid}'s father is the mother (same person, female)", "error", std(ppl3))
        def cyc(t=tmpl):
            pp = t()
            founder = next(p for p in pp if p.mother is None and p.sex == Sex.FEMALE and any(q.mother == p.id for q in pp))
            kids_f = [q.id for q in pp if q.mother == founder.id and q.sex == Sex.FEMALE]
            kids_m = [q.id for q in pp if q.mother == founder.id and q.sex == Sex.MALE]
            founder.mother = kids_f[0] if kids_f else next(q.id for q in pp if q.sex == Sex.FEMALE and q.id != founder.id)
            founder.father = kids_m[0] if kids_m else next(q.id for q in pp if q.sex == Sex.MALE)
            return pp
        add("cycle", f"{tname}: a founder is made a child of her own descendants", "error", std(cyc))
        def selfpar(t=tmpl):
            pp = t()
            p = next(p for p in pp if p.mother is not None and p.sex == Sex.FEMALE)
            p.mother = p.id
            return pp
        add("cycle", f"{tname}: a woman is her own mother", "error", std(selfpar))
        def dup(t=tmpl):
            pp = t()
            return pp + [P(pp[-1].id, "F")]
        add("duplicate_id", f"{tname}: two people share an id", "error", std(dup))
        add("union_unknown", f"{tname}: couple refers to a person not in the tree", "error",
            std(tmpl, unions=[Union(tmpl()[0].id, "ghost")]))
        females = [p.id for p in tmpl() if p.sex == Sex.FEMALE]
        add("union_same_sex", f"{tname}: couple of two women", "error", std(tmpl, unions=[Union(females[0], females[1])]))
        add("union_self", f"{tname}: a person in a couple with themself", "error", std(tmpl, unions=[Union(females[0], females[0])]))
        add("invalid_sex", f"{tname}: a person's sex is the string 'X'", "error",
            std(lambda t=tmpl: t() + [P("odd", "X")]))
        add("invalid_sex", f"{tname}: a parent's sex is 'unknown'", "error",
            std(lambda t=tmpl: [P(p.id, "unknown", p.mother, p.father) if p.id == next(q.mother for q in t() if q.mother) else p for p in t()]))

    # ---------------- evidence format errors (per locus x template) ---------
    for lid in LOCI:
        for tname, tmpl in TEMPLATES.items():
            def ppl(t=tmpl, l=lid, dets=("X",)):
                pp = t()
                pp[-1].test = TestResult(dets)
                return pp
            add("unknown_allele", f"{lid}/{tname}: test reports allele 'X' not defined for the gene", "error", std(ppl, lid))
            add("unknown_allele", f"{lid}/{tname}: test reports allele id in wrong case", "error",
                std(lambda t=tmpl, l=lid, f=ppl: f(t, l, (PATH[l].upper() if PATH[l].upper() != PATH[l] else PATH[l].lower(),)), lid))
            add("reference_as_variant", f"{lid}/{tname}: test reports the reference allele 'N' as a variant", "error",
                std(lambda t=tmpl, l=lid, f=ppl: f(t, l, ("N",)), lid))
            add("three_alleles", f"{lid}/{tname}: test reports three variants at one locus", "error",
                std(lambda t=tmpl, l=lid, f=ppl: f(t, l, (PATH[l],) * 3), lid))
            def ph(t=tmpl, label="diabetes"):
                pp = t()
                pp[-1].phenotype = Phenotype(label)
                return pp
            add("unknown_condition", f"{lid}/{tname}: phenotype names a condition not defined for the gene", "error", std(ph, lid))
            add("unknown_condition", f"{lid}/{tname}: phenotype 'affected with' a carrier label", "error",
                std(lambda t=tmpl, l=lid, f=ph: f(t, "carrier" if l != "HBB" else "sickle cell trait"), lid))
            add("unknown_condition", f"{lid}/{tname}: phenotype label empty string", "error", std(lambda t=tmpl, f=ph: f(t, ""), lid))

    # ---------------- impossible evidence -----------------------------------
    for lid in LOCI:
        aff, path = AFFECTED[lid], PATH[lid]
        det_one = lid in DETECTION_ONE
        exp_neg = "inconsistent" if det_one else "ok"
        tag = "detection 1.0" if det_one else "detection < 1, so possible but unlikely"

        def neg_parents(t=nuclear, a=aff):
            pp = t()
            _find(pp, "mum").test = TestResult(())
            _find(pp, "dad").test = TestResult(())
            _find(pp, "kid").phenotype = Phenotype(a)
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: affected child of two tested-negative parents ({tag})", exp_neg, std(neg_parents, lid))

        def neg_one_parent(t=nuclear, a=aff, p=path):
            pp = t()
            _find(pp, "mum").test = TestResult(())
            _find(pp, "dad").test = TestResult((p,))
            _find(pp, "kid").phenotype = Phenotype(a)
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: affected child, one parent carrier, other tested negative ({tag})", exp_neg, std(neg_one_parent, lid))

        def aff_neg(t=nuclear, a=aff):
            pp = t()
            _find(pp, "kid").phenotype = Phenotype(a)
            _find(pp, "kid").test = TestResult(())
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: affected person with a negative test ({tag})", exp_neg, std(aff_neg, lid))

        def hom_unaff(t=nuclear, p=path):
            pp = t()
            _find(pp, "kid").phenotype = Phenotype(None)
            _find(pp, "kid").test = TestResult((p, p))
            return pp
        add("impossible_evidence", f"{lid}: tested homozygous for a disease variant but recorded unaffected", "inconsistent", std(hom_unaff, lid))

        def hom_child_neg_parent(t=nuclear, p=path):
            pp = t()
            _find(pp, "kid").test = TestResult((p, p))
            _find(pp, "mum").test = TestResult(())
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: child tested with two variants, mother tested negative ({tag})", exp_neg, std(hom_child_neg_parent, lid))

        def gp_chain(t=three_gen, a=aff):
            pp = t()
            _find(pp, "GM").test = TestResult(())
            _find(pp, "GF").test = TestResult(())
            _find(pp, "dad").test = TestResult(())
            _find(pp, "kid").phenotype = Phenotype(a)
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: affected child; father and both maternal grandparents negative ({tag})", exp_neg, std(gp_chain, lid))

        def cousin_aff(t=cousins, a=aff):
            pp = t()
            for q in ("C1", "C2"):
                _find(pp, q).test = TestResult(())
            _find(pp, "kid").phenotype = Phenotype(a)
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: affected child of tested-negative cousin parents ({tag})", exp_neg, std(cousin_aff, lid))

        def two_aff_sibs_neg(t=nuclear, a=aff):
            pp = t()
            _find(pp, "kid").phenotype = Phenotype(a)
            _find(pp, "kid2").phenotype = Phenotype(a)
            _find(pp, "dad").test = TestResult(())
            return pp
        add("impossible_evidence" if det_one else "valid_unlikely_evidence",
            f"{lid}: two affected siblings, father tested negative ({tag})", exp_neg, std(two_aff_sibs_neg, lid))

    def scd_but_b(t=nuclear):
        pp = t()
        _find(pp, "kid").phenotype = Phenotype("sickle cell disease")
        _find(pp, "kid").test = TestResult(("B",))
        return pp
    add("impossible_evidence", "HBB: sickle cell disease (S/S) but test reports only a beta-thal variant", "inconsistent", std(scd_but_b))

    def unaffected_parents_of_bb_with_s_only(t=nuclear):
        pp = t()
        _find(pp, "kid").phenotype = Phenotype("beta-thalassaemia major or intermedia")
        _find(pp, "mum").test = TestResult(("S",))
        _find(pp, "mum").phenotype = Phenotype(None)
        return pp
    add("impossible_evidence", "HBB: beta-thal major child (B/B) but mother carries only HbS (detection 0.99 cannot hide a B she lacks)",
        "inconsistent", std(unaffected_parents_of_bb_with_s_only))

    # ---------------- probability / parameter errors ------------------------
    bad_loci = [
        ("frequencies_sum", "allele frequencies sum to 0.9", lambda: biallelic(freqs=(0.85, 0.05))),
        ("frequencies_sum", "allele frequencies sum to 1.1", lambda: biallelic(freqs=(0.95, 0.15))),
        ("negative_frequency", "negative allele frequency (-0.1, 1.1)", lambda: biallelic(freqs=(1.1, -0.1))),
        ("negative_frequency", "reference frequency negative (-0.2, 1.2)", lambda: biallelic(freqs=(-0.2, 1.2))),
        ("nan_frequency", "allele frequency NaN", lambda: biallelic(freqs=(float("nan"), 0.05))),
        ("detection_rate", "detection rate 1.5", lambda: biallelic(0.05, 1.5)),
        ("detection_rate", "detection rate -0.2", lambda: biallelic(0.05, -0.2)),
        ("detection_rate", "detection rate NaN", lambda: biallelic(0.05, float("nan"))),
        ("duplicate_allele", "two alleles with the same id",
         lambda: Locus("t", "T", (Allele("N", "r", 0.9, False), Allele("N", "p", 0.1, True)), {}, frozenset())),
        ("missing_phenotype", "a genotype with a variant has no phenotype",
         lambda: Locus("t", "T", (Allele("N", "r", 0.9, False), Allele("a", "p", 0.1, True)), {("N", "a"): "carrier"}, frozenset())),
        ("affected_label_unused", "affected label not used by any genotype",
         lambda: Locus("t", "T", (Allele("N", "r", 0.9, False), Allele("a", "p", 0.1, True)),
                       {("N", "a"): "carrier", ("a", "a"): "affected"}, frozenset({"afected"}))),
    ]
    for tname, tmpl in TEMPLATES.items():
        for cat, desc, mk in bad_loci:
            def ppl(t=tmpl):
                pp = t()
                pp[-1].test = TestResult(())
                return pp
            add(cat, f"{tname}: {desc}", "error", std(ppl, locus=mk))
        for bgv, d in ((-0.1, "negative"), (1.0, "equal to 1"), (float("nan"), "NaN"), (1.5, "above 1")):
            add("background_f", f"{tname}: background inbreeding F {d}", "error", std(tmpl, "HBB", bg=bgv))

    # ---------------- query / couple errors ----------------------------------
    for lid in LOCI:
        add("unknown_query", f"{lid}: risk asked for a person not in the tree", "error",
            std(nuclear, lid, action=("marginals", ["ghost"])))
        add("unknown_query", f"{lid}: couple risk for a person not in the tree", "error",
            std(nuclear, lid, action=("couple", "ghost", "dad")))
        add("couple_same_sex", f"{lid}: couple risk asked for two women", "error", std(nuclear, lid, action=("couple", "mum", "kid")))
        add("couple_self", f"{lid}: couple risk asked for a person with themself", "error", std(nuclear, lid, action=("couple", "mum", "mum")))
        add("couple_parent_child", f"{lid}: couple risk for father and daughter (valid maths, unusual input)", "ok",
            std(nuclear, lid, action=("couple", "kid", "dad")))

    # ---------------- contradictory flags ------------------------------------
    for lid in LOCI:
        def preg_male(t=nuclear):
            pp = t()
            _find(pp, "dad").pregnant = True
            return pp
        add("contradictory_flags", f"{lid}: a man is marked pregnant", "error", std(preg_male, lid))
        def preg_dead(t=nuclear):
            pp = t()
            _find(pp, "mum").pregnant = True
            _find(pp, "mum").deceased = True
            return pp
        add("contradictory_flags", f"{lid}: a woman is marked both deceased and pregnant", "error", std(preg_dead, lid))

    # ---------------- valid edge cases (must not raise) -----------------------
    for lid in LOCI:
        aff, path = AFFECTED[lid], PATH[lid]
        add("valid_edge", f"{lid}: single untested person", "ok", std(lambda: [P("x", "F")], lid))
        add("valid_edge", f"{lid}: empty family tree", "ok", std(lambda: [], lid))
        add("valid_edge", f"{lid}: married couple without children (union only)", "ok",
            std(lambda: [P("w", "F"), P("h", "M")], lid, unions=[Union("w", "h")]))
        add("valid_edge", f"{lid}: first-cousin couple, both tested carriers, pregnant", "ok",
            std(lambda p=path: [P(q.id, q.sex, q.mother, q.father, test=TestResult((p,)) if q.id in ("C1", "C2") else None,
                                  pregnant=q.id == "C1") for q in cousins()], lid))
        add("valid_edge", f"{lid}: affected child of untested parents", "ok",
            std(lambda a=aff: [P(q.id, q.sex, q.mother, q.father, phenotype=Phenotype(a) if q.id == "kid" else None) for q in nuclear()], lid))
        add("valid_edge", f"{lid}: man with two wives (half-siblings)", "ok",
            std(lambda: [P("w1", "F"), P("w2", "F"), P("h", "M"), P("a", "F", "w1", "h"), P("b", "M", "w2", "h")], lid))
        add("valid_edge", f"{lid}: deceased ancestors with no information", "ok",
            std(lambda: [P(q.id, q.sex, q.mother, q.father, deceased=q.mother is None) for q in three_gen()], lid))
        add("valid_edge", f"{lid}: everyone recorded unaffected, some tested negative", "ok",
            std(lambda: [P(q.id, q.sex, q.mother, q.father, phenotype=Phenotype(None), test=TestResult(()) if i % 2 else None)
                         for i, q in enumerate(three_gen())], lid))
        add("valid_edge", f"{lid}: tested carrier marries her first cousin's son (cousin once removed)", "ok",
            std(lambda p=path: [*cousins(), P("x", "F", "C1", "C2"), P("o", "F"), P("y", "M", "o", "kid")] , lid,
                action=("couple", "x", "S1")))
    return cases


# --------------------------------------------------------------- execution --
def _source(exc: BaseException) -> str:
    tb = traceback.extract_tb(exc.__traceback__)
    for fr in reversed(tb):
        if "silsila" in fr.filename:
            mod = fr.filename.split("silsila/")[-1]
            return f"{mod}:{fr.name}"
    return tb[-1].filename.split("/")[-1] + ":" + tb[-1].name if tb else "unknown"


def _valid_probs(x: Any) -> bool:
    vals = []

    def walk(v):
        if isinstance(v, dict):
            for u in v.values():
                walk(u)
        elif isinstance(v, (list, tuple, np.ndarray)):
            for u in v:
                walk(u)
        elif isinstance(v, (float, np.floating)):
            vals.append(float(v))
    walk(x)
    return all(math.isfinite(v) and -1e-12 <= v <= 1 + 1e-12 for v in vals)


def _describe_input(inp: dict[str, Any]) -> str:
    people = []
    for p in inp["people"]:
        d = {"id": p.id, "sex": getattr(p.sex, "value", p.sex), "mother": p.mother, "father": p.father}
        if p.phenotype is not None:
            d["affected_with"] = p.phenotype.affected_with
        if p.test is not None:
            d["test"] = list(p.test.detected)
        if p.pregnant:
            d["pregnant"] = True
        if p.deceased:
            d["deceased"] = True
        people.append(d)
    loc = inp["locus"] if isinstance(inp["locus"], Locus) else None
    return json.dumps({"locus": inp["locus_name"], "background_f": inp["bg"], "people": people,
                       "unions": [[u.a, u.b] for u in inp["unions"]], "action": inp["action"],
                       "allele_freqs": [a.frequency for a in loc.alleles] if loc else None}, default=str)


def run_case(c: Case) -> dict[str, Any]:
    row = {"case_id": c.id, "category": c.category, "description": c.description, "expected": c.expected}
    stage = "build input"
    try:
        inp = c.build()
    except Exception as e:  # locus construction is part of the path under test
        row.update(input=json.dumps({"locus_error_during_build": True}), actual="error", error_type=type(e).__name__,
                   error_message=str(e)[:200], error_source=_source(e))
        return _judge(c, row, e)
    row["input"] = _describe_input(inp)
    try:
        stage = "pedigree"
        ped = Pedigree.from_people(inp["people"], inp["unions"])
        stage = "family_report"
        rep = family_report(ped, inp["locus"], background_f=inp["bg"])
        out: Any = rep.__dict__
        act = inp["action"]
        if act and act[0] == "marginals":
            stage = "marginals"
            out = marginals(ped, inp["locus"], act[1], background_f=inp["bg"])
        elif act and act[0] == "couple":
            stage = "couple_risk"
            out = couple_risk(ped, inp["locus"], act[1], act[2], background_f=inp["bg"]).__dict__
        valid = _valid_probs(out if not hasattr(rep, "people") else [out, [r.__dict__ for r in rep.people.values()],
                                                                     [c_.__dict__ for c_ in rep.couples]])
        row.update(actual="ok" if valid else "invalid_probabilities", error_type="", error_message="",
                   error_source="" if valid else f"output of {stage}")
        return _judge(c, row, None)
    except Exception as e:
        row.update(actual="inconsistent" if isinstance(e, InconsistentEvidence) else "error", error_type=type(e).__name__,
                   error_message=str(e)[:200], error_source=_source(e))
        return _judge(c, row, e)


def _judge(c: Case, row: dict[str, Any], e: BaseException | None) -> dict[str, Any]:
    exp, act = c.expected, row["actual"]
    if exp == "ok":
        outcome = "pass" if act == "ok" else ("false_alarm" if e is not None else "silent_failure")
    elif e is None:
        outcome = "silent_failure"
    elif not isinstance(e, CLEAR):
        outcome = "unclear_crash"
    elif exp == "inconsistent" and not isinstance(e, InconsistentEvidence):
        outcome = "wrong_error_type"
    else:
        outcome = "pass"
    row["outcome"] = outcome
    row["pass"] = outcome == "pass"
    return row


def run(quick: bool = False, seed: int = 0) -> dict:
    tm = Timer()
    cases = generate_cases()
    rows = [run_case(c) for c in cases]
    fields = ["case_id", "category", "description", "expected", "actual", "outcome", "pass", "error_type", "error_source",
              "error_message", "input"]
    write_csv("b2_robustness_cases.csv", rows, fields)
    by_cat: dict[str, dict[str, int]] = {}
    for r in rows:
        d = by_cat.setdefault(r["category"], {"n": 0, "pass": 0, "silent_failure": 0, "false_alarm": 0, "unclear_crash": 0, "wrong_error_type": 0})
        d["n"] += 1
        d[r["outcome"]] += 1
    from silsila.sim.stats import exact_ci
    n_bad = sum(r["expected"] != "ok" for r in rows)
    silent = [r for r in rows if r["outcome"] == "silent_failure"]
    out = {
        "benchmark": "B2 input robustness",
        "provenance": provenance(quick, seed),
        "n_cases": len(rows),
        "n_malformed_or_impossible": n_bad,
        "n_valid_edge_cases": len(rows) - n_bad,
        "n_pass": sum(r["pass"] for r in rows),
        "silent_failures": len(silent),
        "silent_failure_rate_ci95": list(exact_ci(len(silent), n_bad)),
        "false_alarms": sum(r["outcome"] == "false_alarm" for r in rows),
        "unclear_crashes": sum(r["outcome"] == "unclear_crash" for r in rows),
        "wrong_error_type": sum(r["outcome"] == "wrong_error_type" for r in rows),
        "by_category": by_cat,
        "silent_failure_cases": [{k: r[k] for k in ("case_id", "category", "description", "actual", "error_source")} for r in silent],
        "non_pass_cases": [{k: r[k] for k in ("case_id", "category", "description", "expected", "actual", "outcome", "error_type", "error_source")}
                           for r in rows if not r["pass"]],
        "log": "docs/evidence/logs/b2_robustness_cases.csv",
        "runtime_seconds": tm(),
    }
    write_json("b2_robustness.json", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    r = run(ap.parse_args().quick)
    print(json.dumps({k: r[k] for k in ("n_cases", "n_pass", "silent_failures", "false_alarms", "unclear_crashes", "wrong_error_type", "by_category")}, indent=1))
