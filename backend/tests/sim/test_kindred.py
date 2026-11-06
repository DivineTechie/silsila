"""Synthetic kindred generator: relationships, kinship, achieved mix,
reproducibility."""

from __future__ import annotations

import numpy as np
import pytest

from silsila.engine import Pedigree, Person, Sex
from silsila.sim import scenarios as S
from silsila.sim.kindred import (
    ALL_TYPES, CONSANGUINEOUS, EXPECTED_KINSHIP, KindredConfig, achieved_mix_over, generate_kindred, kinship_matrix, relationship,
)
from silsila.sim.sources import assumption_values, uae_mix


def P(pid, sex, mo=None, fa=None):
    return Person(pid, Sex.FEMALE if sex == "F" else Sex.MALE, mo, fa)


def test_relationship_classification_on_hand_built_families():
    people = [P("GM", "F"), P("GF", "M"), P("D1", "F", "GM", "GF"), P("S1", "M", "GM", "GF"), P("H1", "M"), P("W1", "F"),
              P("C1", "F", "D1", "H1"), P("C2", "M", "W1", "S1"), P("O1", "M"), P("O2", "F"),
              P("G1", "F", "C1", "O1"), P("G2", "M", "O2", "C2"), P("sib", "F", "D1", "H1")]
    ped = Pedigree.from_people(people)
    assert relationship(ped, "C1", "sib") == "sibling"
    assert relationship(ped, "C1", "C2") == "first_cousin"
    assert relationship(ped, "G1", "G2") == "second_cousin"
    assert relationship(ped, "H1", "W1") is None
    dfc = [P("Am", "F"), P("Af", "M"), P("Bm", "F"), P("Bf", "M"), P("A1", "M", "Am", "Af"), P("A2", "M", "Am", "Af"),
           P("B1", "F", "Bm", "Bf"), P("B2", "F", "Bm", "Bf"), P("X", "F", "B1", "A1"), P("Y", "M", "B2", "A2")]
    assert relationship(Pedigree.from_people(dfc), "X", "Y") == "double_first_cousin"


def _kindreds(n=120, seed=3, **kw):
    a = assumption_values()
    cfg, rec = S.calibrated_config(a, "uae")
    cfg = KindredConfig(**{**cfg.__dict__, **kw})
    rng = np.random.default_rng(seed)
    return [generate_kindred(cfg, rng) for _ in range(n)], rec


def test_kinship_matrix_matches_engine_kinship():
    ks, _ = _kindreds(8)
    rng = np.random.default_rng(0)
    for k in ks:
        order, km = kinship_matrix(k.pedigree)
        ids = list(order)
        for _ in range(25):
            i, j = rng.integers(len(ids), size=2)
            assert km[i, j] == pytest.approx(k.pedigree.kinship(ids[i], ids[j]), abs=1e-15)


def test_generated_cousin_couples_have_malecot_kinship():
    """A couple of type t is related at least as closely as t (1/16, 1/8,
    1/64); when the only shared ancestors are the defining ones (all earlier
    marriages outside), kinship equals the textbook value exactly."""
    ks, _ = _kindreds(150)
    exact_seen = {t: 0 for t in EXPECTED_KINSHIP}
    for k in ks:
        for c in k.couples:
            if c.achieved in EXPECTED_KINSHIP:
                assert c.kinship >= EXPECTED_KINSHIP[c.achieved] - 1e-12
                if c.kinship == pytest.approx(EXPECTED_KINSHIP[c.achieved], abs=1e-12):
                    exact_seen[c.achieved] += 1
            elif c.achieved in ("same_clan", "other_clan", "distant_relative"):
                assert c.kinship == 0.0  # outside spouse: no path in the drawn tree
    assert all(v > 0 for v in exact_seen.values()), exact_seen


def test_first_cousin_kinship_exactly_one_sixteenth_without_earlier_consanguinity():
    cfg = KindredConfig(n_generations=4, sibship_mean=4.0, request_mix={"first_cousin": 0.5, "same_clan": 0.5})
    rng = np.random.default_rng(1)
    n = 0
    for _ in range(40):
        k = generate_kindred(cfg, rng)
        for c in k.couples:
            if c.generation == 2 and c.achieved == "first_cousin":
                assert c.kinship == pytest.approx(1 / 16, abs=1e-15)  # generation 1 married only outside
                n += 1
    assert n > 10


def test_achieved_mix_close_to_uae_target():
    ks, rec = _kindreds(300, seed=99)
    ach = achieved_mix_over(ks)
    tgt = uae_mix(assumption_values())
    for t in ALL_TYPES:
        assert ach[t] == pytest.approx(tgt.get(t, 0.0), abs=0.04), (t, ach[t], tgt.get(t))
    cons = sum(ach[t] for t in CONSANGUINEOUS)
    assert cons == pytest.approx(0.505, abs=0.04)


def test_generator_is_reproducible():
    a, _ = _kindreds(5, seed=42)
    b, _ = _kindreds(5, seed=42)
    for x, y in zip(a, b):
        assert sorted((p.id, p.mother, p.father, p.sex, p.deceased) for p in x.pedigree.people.values()) == \
               sorted((p.id, p.mother, p.father, p.sex, p.deceased) for p in y.pedigree.people.values())
        assert [(c.female, c.male, c.achieved) for c in x.couples] == [(c.female, c.male, c.achieved) for c in y.couples]


def test_living_flags_by_generation():
    ks, _ = _kindreds(30)
    for k in ks:
        for pid, p in k.pedigree.people.items():
            off = k.youngest - k.generation[pid]
            if off >= 3:
                assert p.deceased
            if off <= 1:
                assert not p.deceased
            assert k.age[pid] >= 0
