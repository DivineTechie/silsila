"""Test fixtures. The allele frequencies here are arbitrary test values chosen
to exercise the maths; they are not clinical parameters. Clinical parameters
live in data/params and are sourced."""

from __future__ import annotations

import pytest

from silsila.engine import Allele, Locus, Pedigree, Person, Sex


def biallelic(q: float, detection: float = 1.0) -> Locus:
    return Locus(
        id="test-ar",
        gene="TEST",
        alleles=(
            Allele("N", "reference", 1 - q, False),
            Allele("a", "pathogenic", q, True, detection),
        ),
        phenotypes={("N", "a"): "carrier", ("a", "a"): "affected"},
        affected_phenotypes=frozenset({"affected"}),
    )


def hbb_like(qs: float, qb: float) -> Locus:
    return Locus(
        id="test-hbb",
        gene="HBB",
        alleles=(
            Allele("N", "reference", 1 - qs - qb, False),
            Allele("S", "HbS", qs, True),
            Allele("B", "beta-thal", qb, True),
        ),
        phenotypes={
            ("N", "S"): "sickle cell trait",
            ("B", "N"): "beta-thalassaemia carrier",
            ("S", "S"): "sickle cell disease",
            ("B", "S"): "sickle beta-thalassaemia",
            ("B", "B"): "beta-thalassaemia major",
        },
        affected_phenotypes=frozenset({"sickle cell disease", "sickle beta-thalassaemia", "beta-thalassaemia major"}),
    )


def alpha_like(q1: float, q2: float) -> Locus:
    # "aa" = both alpha genes present on the chromosome; "-a" = one deleted; "--" = both deleted (cis)
    return Locus(
        id="test-hba",
        gene="HBA1/HBA2",
        alleles=(
            Allele("aa", "two genes", 1 - q1 - q2, False),
            Allele("-a", "single deletion", q1, True),
            Allele("--", "double deletion (cis)", q2, True),
        ),
        phenotypes={
            ("-a", "aa"): "silent carrier",
            ("-a", "-a"): "alpha-thalassaemia trait",
            ("--", "aa"): "alpha-thalassaemia trait",
            ("--", "-a"): "HbH disease",
            ("--", "--"): "Hb Bart's hydrops fetalis",
        },
        affected_phenotypes=frozenset({"HbH disease", "Hb Bart's hydrops fetalis"}),
    )


def P(pid, sex, mother=None, father=None, **kw) -> Person:
    return Person(pid, Sex.FEMALE if sex == "F" else Sex.MALE, mother, father, **kw)


def first_cousin_family() -> list[Person]:
    """Grandparents GF+GM; children D1 (F) and S1 (M); D1 marries outsider H1,
    S1 marries outsider W1; their children C1 (F, of D1) and C2 (M, of S1)
    are first cousins and marry each other."""
    return [
        P("GM", "F"), P("GF", "M"),
        P("D1", "F", "GM", "GF"), P("S1", "M", "GM", "GF"),
        P("H1", "M"), P("W1", "F"),
        P("C1", "F", "D1", "H1"), P("C2", "M", "W1", "S1"),
    ]


@pytest.fixture
def cousin_ped() -> Pedigree:
    return Pedigree.from_people(first_cousin_family())
