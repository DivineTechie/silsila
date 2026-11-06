"""Engine results against closed-form textbook answers.

References for the expected values:
  * Kinship coefficients: Malecot (1948); siblings 1/4, first cousins 1/16,
    double first cousins 1/8, second cousins 1/64, uncle-niece 1/8.
  * Offspring of a consanguineous couple, biallelic locus, Hardy-Weinberg
    founders: P(affected) = q^2 + F q (1 - q) with F = parental kinship
    (Wright 1922; see e.g. Bittles, "Consanguinity in Context", 2012).
  * Unaffected sibling of an affected child (both parents carriers):
    P(carrier) = 2/3 (classic Bayesian risk; Young, "Introduction to Risk
    Calculation in Genetic Counselling", 3rd ed., 2006).
  * Residual risk after a negative carrier test with detection rate d:
    prior carrier probability c becomes c(1-d) / (c(1-d) + (1-c)).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from silsila.engine import (
    InconsistentEvidence,
    Pedigree,
    Phenotype,
    TestResult,
    Union,
    couple_risk,
    family_report,
    marginals,
    one_in,
    person_risks,
)

from .conftest import P, alpha_like, biallelic, first_cousin_family, hbb_like


def carrier(locus, post):
    return sum(post[k] for k, g in enumerate(locus.genotypes) if locus.pathogenic_copies(g) == 1)


# ------------------------------------------------------------------ kinship --
def test_kinship_standard_relationships(cousin_ped):
    ped = cousin_ped
    assert ped.kinship("D1", "S1") == pytest.approx(1 / 4)      # siblings
    assert ped.kinship("C1", "C2") == pytest.approx(1 / 16)     # first cousins
    assert ped.kinship("S1", "C1") == pytest.approx(1 / 8)      # uncle-niece
    assert ped.kinship("GM", "GF") == pytest.approx(0.0)        # unrelated founders
    assert ped.kinship("C1", "C1") == pytest.approx(1 / 2)      # self, not inbred


def test_kinship_double_first_and_second_cousins():
    # Two brothers marry two sisters -> their children are double first cousins.
    people = [
        P("A_m", "F"), P("A_f", "M"), P("B_m", "F"), P("B_f", "M"),
        P("A1", "M", "A_m", "A_f"), P("A2", "M", "A_m", "A_f"),
        P("B1", "F", "B_m", "B_f"), P("B2", "F", "B_m", "B_f"),
        P("X", "F", "B1", "A1"), P("Y", "M", "B2", "A2"),
    ]
    ped = Pedigree.from_people(people)
    assert ped.kinship("X", "Y") == pytest.approx(1 / 8)

    # Second cousins: children of first cousins (each married to an outsider).
    base = first_cousin_family()
    base += [P("O1", "M"), P("O2", "F"), P("G1", "F", "C1", "O1"), P("G2", "M", "O2", "C2")]
    ped2 = Pedigree.from_people(base)
    assert ped2.kinship("G1", "G2") == pytest.approx(1 / 64)


# ---------------------------------------------------------- founders / HWE --
@pytest.mark.parametrize("q", [0.001, 0.02, 0.1, 0.3])
def test_founder_carrier_frequency_is_hardy_weinberg(q):
    loc = biallelic(q)
    ped = Pedigree.from_people([P("x", "F")])
    post = marginals(ped, loc)["x"]
    assert carrier(loc, post) == pytest.approx(2 * q * (1 - q), rel=1e-12)


@pytest.mark.parametrize("q", [0.001, 0.02, 0.1])
def test_first_cousin_offspring_risk_matches_wright_formula(q, cousin_ped):
    loc = biallelic(q)
    cr = couple_risk(cousin_ped, loc, "C1", "C2")
    expected = q * q + (1 / 16) * q * (1 - q)
    assert cr.p_child_affected == pytest.approx(expected, rel=1e-10)
    assert cr.baseline_child_affected == pytest.approx(q * q, rel=1e-10)


# ------------------------------------------------- affected child scenarios --
def nuclear_with_affected_child():
    return [
        P("M", "F"), P("F", "M"),
        P("kid", "M", "M", "F", phenotype=Phenotype("affected")),
        P("sib", "F", "M", "F", phenotype=Phenotype(None)),
    ]


@pytest.mark.parametrize("q", [1e-4, 0.01, 0.1])
def test_parents_of_affected_child_are_obligate_carriers(q):
    loc = biallelic(q)
    ped = Pedigree.from_people(nuclear_with_affected_child())
    m = marginals(ped, loc)
    # Parents are unphenotyped here so could in principle be affected; with an
    # explicit 'unaffected' phenotype they are exactly carriers.
    ped.people["M"].phenotype = Phenotype(None)
    ped.people["F"].phenotype = Phenotype(None)
    m = marginals(ped, loc)
    assert carrier(loc, m["M"]) == pytest.approx(1.0)
    assert carrier(loc, m["F"]) == pytest.approx(1.0)


@pytest.mark.parametrize("q", [1e-4, 0.01, 0.1])
def test_unaffected_sibling_is_two_thirds(q):
    loc = biallelic(q)
    people = nuclear_with_affected_child()
    people[0] = P("M", "F", phenotype=Phenotype(None))
    people[1] = P("F", "M", phenotype=Phenotype(None))
    ped = Pedigree.from_people(people)
    assert carrier(loc, marginals(ped, loc)["sib"]) == pytest.approx(2 / 3)


def test_aunt_of_affected_child_tends_to_one_half_for_rare_alleles():
    loc = biallelic(1e-7)
    people = [
        P("GM", "F", phenotype=Phenotype(None)), P("GF", "M", phenotype=Phenotype(None)),
        P("Mo", "F", "GM", "GF", phenotype=Phenotype(None)),
        P("Aunt", "F", "GM", "GF", phenotype=Phenotype(None)),
        P("Fa", "M", phenotype=Phenotype(None)),
        P("kid", "M", "Mo", "Fa", phenotype=Phenotype("affected")),
    ]
    ped = Pedigree.from_people(people)
    assert carrier(loc, marginals(ped, loc)["Aunt"]) == pytest.approx(0.5, abs=1e-5)


# ---------------------------------------------------------- residual risk --
@pytest.mark.parametrize("q,d", [(0.02, 0.9), (0.05, 0.95), (0.1, 0.99)])
def test_residual_risk_after_negative_test(q, d):
    loc = biallelic(q, detection=d)
    ped = Pedigree.from_people([P("x", "F", phenotype=Phenotype(None), test=TestResult(()))])
    c = 2 * q * (1 - q) / (1 - q * q)  # prior carrier prob given unaffected
    expected = c * (1 - d) / (c * (1 - d) + (1 - c))
    assert carrier(loc, marginals(ped, loc)["x"]) == pytest.approx(expected, rel=1e-10)


def test_perfect_negative_test_rules_out_carrier():
    loc = biallelic(0.05, detection=1.0)
    ped = Pedigree.from_people([P("x", "F", test=TestResult(()))])
    assert carrier(loc, marginals(ped, loc)["x"]) == pytest.approx(0.0, abs=1e-15)


def test_inconsistent_results_are_flagged_not_hidden():
    loc = biallelic(0.05, detection=1.0)
    people = [
        P("M", "F", test=TestResult(())), P("F", "M", test=TestResult(())),
        P("kid", "M", "M", "F", phenotype=Phenotype("affected")),
    ]
    ped = Pedigree.from_people(people)
    with pytest.raises(InconsistentEvidence):
        marginals(ped, loc)


# ------------------------------------------------------------ multi-allele --
def test_hbs_by_beta_thal_couple_child_outcomes():
    loc = hbb_like(0.02, 0.04)
    ped = Pedigree.from_people(
        [P("W", "F", test=TestResult(("S",))), P("H", "M", test=TestResult(("B",)))],
        [Union("W", "H")],
    )
    cr = couple_risk(ped, loc, "W", "H")
    assert cr.p_both_carry == pytest.approx(1.0)
    assert cr.child_phenotypes["sickle beta-thalassaemia"] == pytest.approx(0.25)
    assert cr.child_phenotypes["sickle cell trait"] == pytest.approx(0.25)
    assert cr.child_phenotypes["beta-thalassaemia carrier"] == pytest.approx(0.25)
    assert cr.p_child_affected == pytest.approx(0.25)


def test_alpha_thal_cis_and_trans_carriers():
    loc = alpha_like(0.2, 0.01)
    # --/aa (cis double deletion) x -a/aa -> 1/4 HbH disease, 0 hydrops
    ped = Pedigree.from_people(
        [P("W", "F", test=TestResult(("--",))), P("H", "M", test=TestResult(("-a",)))], [Union("W", "H")]
    )
    cr = couple_risk(ped, loc, "W", "H")
    assert cr.child_phenotypes["HbH disease"] == pytest.approx(0.25)
    assert cr.child_phenotypes.get("Hb Bart's hydrops fetalis", 0) == pytest.approx(0.0)
    # -a/-a (trans) x --/aa -> HbH 1/2, hydrops 0: a trans carrier has no -- to pass on
    ped2 = Pedigree.from_people(
        [P("W", "F", test=TestResult(("-a", "-a"))), P("H", "M", test=TestResult(("--",)))], [Union("W", "H")]
    )
    cr2 = couple_risk(ped2, loc, "W", "H")
    assert cr2.child_phenotypes["HbH disease"] == pytest.approx(0.5)
    assert cr2.child_phenotypes.get("Hb Bart's hydrops fetalis", 0) == pytest.approx(0.0)
    # --/aa x --/aa -> 1/4 hydrops
    ped3 = Pedigree.from_people(
        [P("W", "F", test=TestResult(("--",))), P("H", "M", test=TestResult(("--",)))], [Union("W", "H")]
    )
    assert couple_risk(ped3, loc, "W", "H").child_phenotypes["Hb Bart's hydrops fetalis"] == pytest.approx(0.25)


# ------------------------------------------------------------- invitations --
def test_invites_put_pregnant_couple_first():
    loc = biallelic(0.02)
    people = [
        P("GM", "F", phenotype=Phenotype(None)), P("GF", "M", phenotype=Phenotype(None)),
        P("Mo", "F", "GM", "GF", phenotype=Phenotype(None)), P("Fa", "M", phenotype=Phenotype(None)),
        P("kid", "M", "Mo", "Fa", phenotype=Phenotype("affected")),
        P("Sis", "F", "GM", "GF", pregnant=True), P("SisH", "M"),
        P("Bro", "M", "GM", "GF"), P("BroW", "F"),
    ]
    ped = Pedigree.from_people(people, [Union("Sis", "SisH"), Union("BroW", "Bro")])
    rep = family_report(ped, loc)
    ids = [s.person_id for s in rep.invites]
    assert ids[0] == "Sis" and rep.invites[0].reason_code == "current_pregnancy"
    assert "kid" not in ids                      # affected people are not 'invited'
    assert all(s.rank == k + 1 for k, s in enumerate(rep.invites))


def test_one_in_formatting():
    assert one_in(0.5) == "1 in 2"
    assert one_in(2 / 3) == "2 in 3"
    assert one_in(1 / 8) == "1 in 8"
    assert one_in(0.0123) == "about 1 in 81"
    assert one_in(0.0) == "0"
    assert one_in(0.87) == "about 9 in 10"
    assert one_in(0.31) == "about 3 in 10"
    assert one_in(0.996) == "more than 9 in 10"


def test_probabilities_are_valid_everywhere(cousin_ped):
    loc = hbb_like(0.03, 0.05)
    for pr in person_risks(cousin_ped, loc).values():
        total = sum(pr.genotype_posterior.values())
        assert math.isclose(total, 1.0, rel_tol=1e-12)
        assert 0 <= pr.p_carrier <= 1 and 0 <= pr.p_affected <= 1
    assert np.isfinite(couple_risk(cousin_ped, loc, "C1", "C2").p_child_affected)
