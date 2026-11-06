"""The exact engine against two independent methods on random consanguineous
families:

  1. pgmpy's exact VariableElimination on the same Bayesian network, built
     here from scratch (different code, different factor library);
  2. Monte Carlo gene dropping with likelihood weighting.

Random families are generated with cousin and uncle-niece marriages so the
network has loops, and evidence is drawn from simulated true genotypes so it is
always consistent.
"""

from __future__ import annotations

import numpy as np
import pytest

from silsila.engine import Pedigree, Phenotype, TestResult, couple_joint, marginals
from silsila.engine.montecarlo import effective_sample_size, gene_drop, mc_marginal

from .conftest import P, alpha_like, biallelic, hbb_like

try:  # pgmpy renamed its model class across versions
    from pgmpy.models import DiscreteBayesianNetwork as _BN
except ImportError:  # pragma: no cover
    from pgmpy.models import BayesianNetwork as _BN
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination


def random_family(rng: np.random.Generator, generations: int = 3, consanguinity: float = 0.6):
    """Founding couple, then each generation's children marry either a cousin
    from the same generation (probability `consanguinity`) or an outsider."""
    people = [P("g0_f", "F"), P("g0_m", "M")]
    couples = [("g0_f", "g0_m")]
    n = 0
    for gen in range(1, generations + 1):
        kids = []
        for mother, father in couples:
            for _ in range(int(rng.integers(1, 4))):
                n += 1
                sex = "F" if rng.random() < 0.5 else "M"
                pid = f"g{gen}_{n}"
                people.append(P(pid, sex, mother, father))
                kids.append((pid, sex, (mother, father)))
        couples = []
        rng.shuffle(kids)
        used = set()
        for pid, sex, fam in kids:
            if pid in used or rng.random() < 0.25:
                continue
            match = None
            if rng.random() < consanguinity:
                for pid2, sex2, fam2 in kids:
                    if pid2 not in used and pid2 != pid and sex2 != sex and fam2 != fam:
                        match = pid2
                        break
            if match is None:
                n += 1
                match = f"out{n}"
                people.append(P(match, "M" if sex == "F" else "F"))
            used.update({pid, match})
            f, m = (pid, match) if sex == "F" else (match, pid)
            couples.append((f, m))
        if not couples:
            break
    return people, couples


def add_evidence(people, locus, rng, frac=0.4):
    ped = Pedigree.from_people(people)
    genos, _ = gene_drop(ped, locus, n=1, seed=int(rng.integers(1 << 30)))
    for p in people:
        if rng.random() > frac:
            continue
        g = locus.genotypes[int(genos[p.id][0])]
        if rng.random() < 0.5:
            ph = locus.phenotype_of(g)
            p.phenotype = Phenotype(ph if ph in locus.affected_phenotypes else None)
        else:
            detected = tuple(locus.alleles[i].id for i in g if locus.alleles[i].pathogenic)
            p.test = TestResult(detected)
    return Pedigree.from_people(people)


def pgmpy_marginals(ped: Pedigree, locus, extra_child=None):
    from silsila.engine.inference import phenotype_likelihood, test_likelihood

    n = locus.n_genotypes
    prior = locus.founder_prior()
    trans = locus.transmission  # [m, f, c]
    edges, cpds, evidence = [], [], {}
    for pid in ped.topological_order():
        p = ped.people[pid]
        if p.mother is None:
            cpds.append(TabularCPD(pid, n, prior.reshape(n, 1)))
        else:
            edges += [(p.mother, pid), (p.father, pid)]
            cpd = trans.reshape(n * n, n).T  # rows child, columns (m, f) with f fastest
            cpds.append(TabularCPD(pid, n, cpd, evidence=[p.mother, p.father], evidence_card=[n, n]))
        liks = []
        if p.phenotype is not None:
            liks.append(phenotype_likelihood(locus, p.phenotype))
        if p.test is not None:
            liks.append(test_likelihood(locus, p.test))
        for k, lik in enumerate(liks):
            ev = f"ev_{pid}_{k}"
            edges.append((pid, ev))
            table = np.vstack([1 - lik, lik])  # state 1 = "observed as recorded"
            cpds.append(TabularCPD(ev, 2, table, evidence=[pid], evidence_card=[n]))
            evidence[ev] = 1
    if extra_child:
        name, (m, f) = extra_child
        edges += [(m, name), (f, name)]
        cpds.append(TabularCPD(name, n, trans.reshape(n * n, n).T, evidence=[m, f], evidence_card=[n, n]))
    model = _BN(edges)
    for pid in ped.people:
        if pid not in model.nodes():
            model.add_node(pid)
    model.add_cpds(*cpds)
    infer = VariableElimination(model)
    out = {}
    targets = list(ped.people) + ([extra_child[0]] if extra_child else [])
    for pid in targets:
        if pid in evidence:
            continue
        q = infer.query([pid], evidence=evidence, show_progress=False)
        out[pid] = np.asarray(q.values)
    return out


LOCI = [lambda: biallelic(0.08, 0.9), lambda: hbb_like(0.05, 0.08), lambda: alpha_like(0.25, 0.05)]


@pytest.mark.parametrize("seed", range(12))
def test_engine_matches_pgmpy_exactly(seed):
    rng = np.random.default_rng(seed)
    locus = LOCI[seed % len(LOCI)]()
    people, couples = random_family(rng)
    ped = add_evidence(people, locus, rng)
    ours = marginals(ped, locus)
    ref = pgmpy_marginals(ped, locus)
    for pid, post in ref.items():
        np.testing.assert_allclose(ours[pid], post, atol=1e-9, err_msg=f"{pid} seed={seed}")
    if couples:
        f, m = couples[-1]
        _, child = couple_joint(ped, locus, f, m)
        ref_child = pgmpy_marginals(ped, locus, ("vchild", (f, m)))["vchild"]
        np.testing.assert_allclose(child, ref_child, atol=1e-9)


@pytest.mark.parametrize("seed", range(6))
def test_engine_matches_monte_carlo(seed):
    rng = np.random.default_rng(100 + seed)
    locus = LOCI[seed % len(LOCI)]()
    people, _ = random_family(rng, generations=3)
    ped = add_evidence(people, locus, rng, frac=0.25)
    ours = marginals(ped, locus)
    genos, w = gene_drop(ped, locus, n=400_000, seed=seed)
    ess = effective_sample_size(w)
    assert ess > 500, "Monte Carlo too degenerate for a meaningful check"
    for pid in ped.people:
        mc = mc_marginal(genos[pid], w, locus.n_genotypes)
        # binomial standard error at the effective sample size, 5 sigma
        tol = 5 * np.sqrt(np.maximum(ours[pid] * (1 - ours[pid]), 1e-6) / ess)
        assert np.all(np.abs(mc - ours[pid]) <= tol + 1e-9), f"{pid}: mc={mc} exact={ours[pid]}"
