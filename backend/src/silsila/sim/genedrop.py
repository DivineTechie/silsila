"""Genetic 'truth' for synthetic kindreds (SYNTHETIC DATA).

This is deliberately a different model from the one the engine uses, so the
benchmarks measure what happens when the app's assumptions are not exactly
true:

  * Clan (tribe / biradri) structure, Balding-Nichols model (Balding and
    Nichols 1995, Genetica 96:3-12): each clan has its own allele frequencies
    drawn from a Dirichlet distribution centred on the population
    frequencies with dispersion theta (= F_ST, the kinship of two founders
    of the same clan). theta = 0 means no clan structure. The engine does not
    know about clans.
  * Founder inbreeding within the clan: a founder's two alleles are identical
    by descent with probability founder_f (as in engine.montecarlo).
  * Mendelian transmission down the drawn tree.

Everything is vectorised over R replicates of the same family structure.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..engine import Locus, Pedigree


@dataclass(frozen=True)
class TruthModel:
    locus: Locus
    theta: float = 0.0       # clan F_ST
    founder_f: float = 0.0   # founder inbreeding within clan

    @property
    def freqs(self) -> np.ndarray:
        return np.array([a.frequency for a in self.locus.alleles])

    @property
    def total_founder_f(self) -> float:
        """Inbreeding of a founder relative to the whole population."""
        return self.theta + (1 - self.theta) * self.founder_f


def _sample_categorical(p: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Row-wise categorical sampling: p is (R, k), u is (R,) uniforms."""
    cum = np.cumsum(p, axis=1)
    out = (u[:, None] > cum[:, :-1]).sum(axis=1)
    return out


def clan_frequencies(model: TruthModel, r: int, rng: np.random.Generator) -> np.ndarray:
    p = model.freqs
    if model.theta <= 0:
        return np.broadcast_to(p, (r, len(p))).copy()
    alpha = p * (1 - model.theta) / model.theta
    # gamma-based Dirichlet; tiny alphas can underflow to all-zero rows, which
    # are redrawn
    out = rng.dirichlet(alpha, size=r)
    bad = ~np.isfinite(out).all(axis=1) | (out.sum(axis=1) <= 0)
    while bad.any():
        out[bad] = rng.dirichlet(alpha, size=int(bad.sum()))
        bad = ~np.isfinite(out).all(axis=1) | (out.sum(axis=1) <= 0)
    return out


def drop(
    ped: Pedigree,
    clan: dict[str, int],
    model: TruthModel,
    r: int,
    rng: np.random.Generator,
    clan_freqs: dict[int, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """Return allele-index pairs (R, 2) per person.

    `clan` gives each founder's clan id; founders missing from it get their
    own clan. `clan_freqs` may supply pre-drawn clan frequencies (R, k)."""
    cf: dict[int, np.ndarray] = dict(clan_freqs or {})
    alleles: dict[str, np.ndarray] = {}
    rows = np.arange(r)
    own = -1
    for pid in ped.topological_order():
        p = ped.people[pid]
        if p.mother is None:
            c = clan.get(pid)
            if c is None:
                c = own
                own -= 1
            if c not in cf:
                cf[c] = clan_frequencies(model, r, rng)
            pc = cf[c]
            a0 = _sample_categorical(pc, rng.random(r))
            a1 = _sample_categorical(pc, rng.random(r))
            if model.founder_f > 0:
                ibd = rng.random(r) < model.founder_f
                a1 = np.where(ibd, a0, a1)
            alleles[pid] = np.stack([a0, a1], axis=1)
        else:
            m = alleles[p.mother][rows, rng.integers(0, 2, r)]
            f = alleles[p.father][rows, rng.integers(0, 2, r)]  # type: ignore[index]
            alleles[pid] = np.stack([m, f], axis=1)
    return alleles


@dataclass
class Derived:
    """Per-person arrays over replicates derived from allele pairs."""

    genotype: dict[str, np.ndarray]    # genotype index (engine ordering)
    affected: dict[str, np.ndarray]    # bool
    carrier_any: dict[str, np.ndarray]  # >= 1 pathogenic allele (incl. affected)
    detected: dict[str, np.ndarray]    # tuple-free: (R, 2) bool, copy reported by a test


def derive(model: TruthModel, alleles: dict[str, np.ndarray], rng: np.random.Generator) -> Derived:
    loc = model.locus
    n = len(loc.alleles)
    gi = np.full((n, n), -1)
    for k, (i, j) in enumerate(loc.genotypes):
        gi[i, j] = gi[j, i] = k
    aff_vec = np.array([ph in loc.affected_phenotypes for ph in loc.phenotype_vector])
    path = np.array([a.pathogenic for a in loc.alleles])
    det = np.array([a.detection_rate if a.pathogenic else 0.0 for a in loc.alleles])
    g, aff, car, dt = {}, {}, {}, {}
    for pid, a in alleles.items():
        gk = gi[a[:, 0], a[:, 1]]
        g[pid] = gk
        aff[pid] = aff_vec[gk]
        car[pid] = path[a].any(axis=1)
        dt[pid] = rng.random(a.shape) < det[a]
    return Derived(g, aff, car, dt)


def detected_alleles(model: TruthModel, alleles: np.ndarray, detected: np.ndarray) -> tuple[str, ...]:
    """Test report for one replicate: ids of the detected pathogenic copies."""
    loc = model.locus
    return tuple(sorted(loc.alleles[int(a)].id for a, d in zip(alleles, detected) if d))
