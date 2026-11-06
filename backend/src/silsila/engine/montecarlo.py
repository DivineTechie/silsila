"""Monte Carlo gene dropping: an independent check on the exact engine.

Alleles are sampled for founders from population frequencies and passed down
the pedigree by simulated Mendelian transmission. Each simulated family is
weighted by how likely the recorded phenotypes and test results are under its
genotypes (likelihood weighting). Weighted genotype counts then estimate the
same posteriors that the exact engine computes.

This shares only the locus definition and the evidence likelihoods with the
exact engine; the inference method is entirely different, which is the point.
"""

from __future__ import annotations

import numpy as np

from .inference import phenotype_likelihood, test_likelihood
from .locus import Locus
from .pedigree import Pedigree


def gene_drop(
    ped: Pedigree,
    locus: Locus,
    n: int = 200_000,
    seed: int = 0,
    virtual_children: dict[str, tuple[str, str]] | None = None,
    background_f: float = 0.0,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Return (genotype index per person per sample, sample weights).

    With background inbreeding F, a founder's two alleles are identical by
    descent with probability F (one draw, duplicated), otherwise drawn
    independently. This gives P(i,i) = p_i^2 + F p_i (1 - p_i), matching
    Locus.founder_prior."""
    rng = np.random.default_rng(seed)
    freqs = np.array([a.frequency for a in locus.alleles])
    gi = np.full((len(locus.alleles), len(locus.alleles)), -1)
    for k, (i, j) in enumerate(locus.genotypes):
        gi[i, j] = gi[j, i] = k

    alleles: dict[str, np.ndarray] = {}
    order = ped.topological_order()
    rows = np.arange(n)
    for pid in order:
        p = ped.people[pid]
        if p.mother is None:
            pair = rng.choice(len(freqs), size=(n, 2), p=freqs)
            if background_f > 0:
                ibd = rng.random(n) < background_f
                pair[ibd, 1] = pair[ibd, 0]
            alleles[pid] = pair
        else:
            m = alleles[p.mother][rows, rng.integers(0, 2, n)]
            f = alleles[p.father][rows, rng.integers(0, 2, n)]  # type: ignore[index]
            alleles[pid] = np.stack([m, f], axis=1)
    for child, (mother, father) in (virtual_children or {}).items():
        m = alleles[mother][rows, rng.integers(0, 2, n)]
        f = alleles[father][rows, rng.integers(0, 2, n)]
        alleles[child] = np.stack([m, f], axis=1)

    genotypes = {pid: gi[a[:, 0], a[:, 1]] for pid, a in alleles.items()}
    weights = np.ones(n)
    for pid in order:
        p = ped.people[pid]
        if p.phenotype is not None:
            weights *= phenotype_likelihood(locus, p.phenotype)[genotypes[pid]]
        if p.test is not None:
            weights *= test_likelihood(locus, p.test)[genotypes[pid]]
    return genotypes, weights


def mc_marginal(genotypes: np.ndarray, weights: np.ndarray, n_genotypes: int) -> np.ndarray:
    total = weights.sum()
    if total <= 0:
        raise ValueError("No simulated family matched the evidence; increase n")
    return np.bincount(genotypes, weights=weights, minlength=n_genotypes) / total


def effective_sample_size(weights: np.ndarray) -> float:
    s = weights.sum()
    return float(s * s / (weights * weights).sum()) if s > 0 else 0.0
