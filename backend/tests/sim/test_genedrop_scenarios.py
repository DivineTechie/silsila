"""Genetic truth simulation and scenario plumbing."""

from __future__ import annotations

import numpy as np
import pytest

from silsila import params
from silsila.engine import Pedigree, couple_risk
from silsila.sim import scenarios as S
from silsila.sim.genedrop import TruthModel, derive, drop
from silsila.sim.kindred import generate_kindred
from silsila.sim.sources import ahmed, assumption_values, assumptions_doc


def test_founders_reproduce_hardy_weinberg_with_total_f():
    loc = S.nejm_truth_locus(0.0, 1.0)
    for theta, ff in ((0.0, 0.0), (0.0, 0.03), (0.1, 0.0), (0.1, 0.02)):
        m = TruthModel(loc, theta, ff)
        ped, clan, x, _ = S.couple_type_pedigree("other_clan")
        rng = np.random.default_rng(5)
        d = derive(m, drop(ped, clan, m, 400_000, rng), rng)
        q = loc.alleles[1].frequency
        f = m.total_founder_f
        aff = float(np.mean(d.affected[x]))
        assert aff == pytest.approx(q * q + f * q * (1 - q), abs=4 * np.sqrt(aff / 400_000) + 1e-5)


def test_nejm_locus_gives_published_carrier_rate():
    for f in (0.0, 0.05):
        loc = S.nejm_truth_locus(f, 1.0)
        q = loc.alleles[1].frequency
        assert 2 * q * (1 - q) * (1 - f) == pytest.approx(ahmed()["population_bthal_carrier_freq"], rel=1e-12)


@pytest.mark.parametrize("t,phi", [("first_cousin", 1 / 16), ("double_first_cousin", 1 / 8), ("second_cousin", 1 / 64)])
def test_couple_types_match_engine_at_theta_zero(t, phi):
    """At theta = 0 the truth model and the engine agree on child risk."""
    rec = params.load()["SMN1"]
    m = TruthModel(rec.locus, 0.0, 0.0)
    rates = S.couple_type_rates(m, [t], 600_000, 11)[t]
    ped, _, x, y = S.couple_type_pedigree(t)
    exact = couple_risk(ped, rec.locus, x, y).p_child_affected
    q = rec.locus.alleles[1].frequency
    assert exact == pytest.approx(q * q + phi * q * (1 - q), rel=1e-9)
    assert rates["child_affected"] == pytest.approx(exact, abs=5 * np.sqrt(exact / 600_000))


def test_same_clan_founders_are_related_by_theta():
    loc = S.nejm_truth_locus(0.0, 1.0)
    q = loc.alleles[1].frequency
    th = 0.1
    r = S.couple_type_rates(TruthModel(loc, th, 0.0), ["same_clan", "other_clan"], 600_000, 3)
    # child of same-clan founders has inbreeding theta
    exp = q * q + th * q * (1 - q)
    assert r["same_clan"]["child_affected"] == pytest.approx(exp, abs=5 * np.sqrt(exp / 600_000))
    assert r["other_clan"]["child_affected"] == pytest.approx(q * q, abs=5 * np.sqrt(q * q / 600_000))


def test_nejm_worker_reproducible_and_sane():
    a = assumption_values()
    cfg, _ = S.calibrated_config(a, "nejm")
    jobs = S.nejm_jobs(a, cfg, 0.05, "index", 30, 123)
    r1 = S.run(None, S.nejm_worker, jobs)
    r2 = S.run(None, S.nejm_worker, jobs)
    assert r1 == r2 and len(r1) > 0
    for r in r1:
        assert 0 <= r["carriers"] <= r["tested"] <= r["living"]
        assert r["atrisk_identified"] <= r["couples"]
        assert r["affected_living_or_dead"] >= 1  # ascertained through an affected child


def test_uae_worker_strategies_test_the_same_people():
    a = assumption_values()
    cfg, _ = S.calibrated_config(a, "uae")
    rows = S.run(None, S.uae_worker, S.uae_jobs(a, cfg, "HBB", 0.093, 12, 77, 6))
    assert rows
    for r in rows:
        assert r["engine_error"] is None
        if r["ranked"]:
            # same eligible people, uptake and results: totals agree, only order differs
            assert r["ranked"][-1] == r["unranked"][-1]
            assert len(r["ranked"]) == len(r["unranked"])
        assert r["drawn_size"] <= r["kindred_size"]


def test_drawn_tree_is_closed_under_parents():
    a = assumption_values()
    cfg, _ = S.calibrated_config(a, "uae")
    rng = np.random.default_rng(8)
    for _ in range(10):
        k = generate_kindred(cfg, rng)
        young = [p for p in k.pedigree.people if k.generation[p] == k.youngest]
        if not young:
            continue
        idx = young[0]
        m = S.drawn_tree(k, idx, "grandparents")
        assert idx in m
        for pid in m:
            p = k.pedigree.people[pid]
            if p.mother is not None:
                assert p.mother in m and p.father in m


def test_every_assumption_is_labelled():
    for aid, spec in assumptions_doc().items():
        assert spec.get("reason"), aid
        assert spec["kind"] in {"assumption", "calibrated", "proxy", "generator", "display"}, aid
        assert spec.get("used_in"), aid
        if spec["kind"] in ("assumption", "calibrated", "proxy") and not isinstance(spec["value"], (str, bool)) and aid not in (
                "uae_detection_cyp21a2", "nejm_consanguineous_split"):
            assert "range" in spec or "alternatives" in spec, f"{aid} needs a sensitivity range"
