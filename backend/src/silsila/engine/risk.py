"""Risk reports built on the exact engine.

Everything here is arithmetic on engine posteriors. The outputs are structured
numbers with the reason for each ordering; they are rendered for people only
through approved text templates (see silsila.content). Nothing in this module
recommends a personal or reproductive decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

from . import inference
from .locus import Locus
from .pedigree import Pedigree


_ONE_IN = {
    "en": {"zero": "0", "certain": "1 in 1 (certain)", "exact": "{n} in {d}", "tenths": "about {t} in 10",
           "over": "more than 9 in 10", "small": "about 1 in {n}"},
    "ar": {"zero": "0", "certain": "1 من 1 (مؤكد)", "exact": "{n} من {d}", "tenths": "حوالي {t} من 10",
           "over": "أكثر من 9 من 10", "small": "حوالي 1 من {n}"},
}


def one_in(p: float, lang: str = "en") -> str:
    """Express a probability for display, in English or Arabic.

    Exact simple fractions (1/2, 2/3, 1/4, 1/8 ...) are shown exactly. Other
    chances of 1 in 5 or more are shown in tenths ("about 9 in 10"), and smaller
    chances as "about 1 in N", the convention used in genetic counselling."""
    w = _ONE_IN["ar" if lang == "ar" else "en"]
    if p <= 0:
        return w["zero"]
    if p >= 1 - 1e-9:
        return w["certain"]
    frac = Fraction(p).limit_denominator(64)
    if abs(float(frac) - p) < 1e-9:
        return w["exact"].format(n=frac.numerator, d=frac.denominator)
    if p >= 0.2:
        tenths = round(p * 10)
        return w["over"] if tenths >= 10 else w["tenths"].format(t=tenths)
    return w["small"].format(n=f"{round(1 / p):,}")


@dataclass
class PersonRisk:
    person_id: str
    p_carrier: float          # carries at least one pathogenic allele and is not affected
    p_affected: float
    p_any_pathogenic: float   # p_carrier + p_affected
    genotype_posterior: dict[str, float]
    tested: bool
    informative: bool         # untested and alive: a test would add information


@dataclass
class CoupleRisk:
    female: str
    male: str
    kinship: float
    p_both_carry: float                     # both partners carry >=1 pathogenic allele
    p_child_affected: float                 # per pregnancy
    child_phenotypes: dict[str, float]
    baseline_child_affected: float          # same locus, two unrelated untested people


@dataclass
class InviteSuggestion:
    person_id: str
    rank: int
    p_carrier: float
    partner_id: str | None
    p_couple_both_carry: float | None
    p_child_affected: float | None
    pregnant_couple: bool
    reason_code: str   # rendered through an approved template, never free text


@dataclass
class FamilyReport:
    locus_id: str
    people: dict[str, PersonRisk] = field(default_factory=dict)
    couples: list[CoupleRisk] = field(default_factory=list)
    invites: list[InviteSuggestion] = field(default_factory=list)


def _summaries(locus: Locus, post: np.ndarray) -> tuple[float, float]:
    affected = sum(post[k] for k, ph in enumerate(locus.phenotype_vector) if ph in locus.affected_phenotypes)
    any_path = sum(post[k] for k, g in enumerate(locus.genotypes) if locus.pathogenic_copies(g) > 0)
    return float(any_path - affected), float(affected)


def person_risks(ped: Pedigree, locus: Locus, background_f: float = 0.0) -> dict[str, PersonRisk]:
    margs = inference.marginals(ped, locus, background_f=background_f)
    out = {}
    for pid, post in margs.items():
        carrier, affected = _summaries(locus, post)
        p = ped.people[pid]
        tested = p.test is not None
        out[pid] = PersonRisk(
            person_id=pid,
            p_carrier=carrier,
            p_affected=affected,
            p_any_pathogenic=carrier + affected,
            genotype_posterior={locus.genotype_label(g): float(post[k]) for k, g in enumerate(locus.genotypes)},
            tested=tested,
            informative=(not tested) and (not p.deceased),
        )
    return out


def couple_risk(ped: Pedigree, locus: Locus, female: str, male: str, background_f: float = 0.0) -> CoupleRisk:
    from .pedigree import PedigreeError, Sex

    for pid, sex in ((female, Sex.FEMALE), (male, Sex.MALE)):
        if pid not in ped.people:
            raise PedigreeError(f"'{pid}' is not in the family tree")
        if ped.people[pid].sex != sex:
            raise PedigreeError(f"A couple is calculated as one woman ({female}) and one man ({male})")
    joint, child = inference.couple_joint(ped, locus, female, male, background_f)
    path = np.array([locus.pathogenic_copies(g) > 0 for g in locus.genotypes], dtype=float)
    p_both = float(path @ joint @ path)
    child_ph: dict[str, float] = {}
    for k, ph in enumerate(locus.phenotype_vector):
        child_ph[ph] = child_ph.get(ph, 0.0) + float(child[k])
    p_aff = sum(v for ph, v in child_ph.items() if ph in locus.affected_phenotypes)
    prior = locus.founder_prior(background_f)
    base_child = locus.transmission.reshape(locus.n_genotypes**2, -1).T @ np.outer(prior, prior).ravel()
    base_aff = sum(base_child[k] for k, ph in enumerate(locus.phenotype_vector) if ph in locus.affected_phenotypes)
    return CoupleRisk(
        female=female,
        male=male,
        kinship=ped.kinship(female, male),
        p_both_carry=p_both,
        p_child_affected=float(p_aff),
        child_phenotypes=child_ph,
        baseline_child_affected=float(base_aff),
    )


def family_report(ped: Pedigree, locus: Locus, background_f: float = 0.0) -> FamilyReport:
    """Carrier probabilities for everyone, risks for every couple, and an
    ordered list of relatives whose testing would be most informative.

    Ordering rule (deterministic, documented in docs/engine.md):
      1. couples with a current pregnancy, because time limits apply;
      2. then by the probability that the couple's child is affected;
      3. then single people by their carrier probability.
    Ties keep family-tree order.
    """
    rep = FamilyReport(locus_id=locus.id)
    rep.people = person_risks(ped, locus, background_f)
    for f, m in ped.couples():
        rep.couples.append(couple_risk(ped, locus, f, m, background_f))
    by_person: dict[str, list[CoupleRisk]] = {}
    for c in rep.couples:
        by_person.setdefault(c.female, []).append(c)
        by_person.setdefault(c.male, []).append(c)

    candidates: list[tuple[tuple, InviteSuggestion]] = []
    order = {pid: k for k, pid in enumerate(ped.topological_order())}
    for pid, pr in rep.people.items():
        p = ped.people[pid]
        if not pr.informative or pr.p_affected > 0.999:
            continue
        if pr.p_any_pathogenic < 1e-6:
            continue
        couples = [c for c in by_person.get(pid, []) if not ped.people[c.female].deceased and not ped.people[c.male].deceased]
        best = max(couples, key=lambda c: c.p_child_affected, default=None)
        pregnant = bool(best and ped.people[best.female].pregnant)
        partner = None if best is None else (best.male if best.female == pid else best.female)
        if best is None:
            reason = "single_carrier_probability"
        elif pregnant:
            reason = "current_pregnancy"
        else:
            reason = "couple_child_risk"
        key = (
            0 if pregnant else 1,
            -(best.p_child_affected if best else 0.0),
            -pr.p_any_pathogenic,
            order[pid],
        )
        candidates.append(
            (
                key,
                InviteSuggestion(
                    person_id=pid,
                    rank=0,
                    p_carrier=pr.p_any_pathogenic,
                    partner_id=partner,
                    p_couple_both_carry=best.p_both_carry if best else None,
                    p_child_affected=best.p_child_affected if best else None,
                    pregnant_couple=pregnant,
                    reason_code=reason,
                ),
            )
        )
    candidates.sort(key=lambda t: t[0])
    for r, (_, s) in enumerate(candidates, start=1):
        s.rank = r
        rep.invites.append(s)
    return rep
