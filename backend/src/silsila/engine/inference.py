"""Exact genotype inference on a pedigree by variable elimination.

The pedigree is a Bayesian network over genotypes: founders draw genotypes from
the population prior, every other person's genotype depends on their parents'
genotypes through Mendelian transmission, and phenotypes and test results enter
as likelihoods. Cousin marriages create loops in this network; variable
elimination handles loops exactly (it is not belief propagation).

This is the textbook formulation used by pedigree risk software (Elston and
Stewart 1971; Lauritzen and Sheehan 2003, "Graphical models for genetic
analyses", Statistical Science 18:489-514). The test-suite checks it against a
second exact implementation (pgmpy) and against Monte Carlo gene dropping.
"""

from __future__ import annotations

import functools
import math
import string
from dataclasses import dataclass

import numpy as np

from .locus import Locus
from .pedigree import Pedigree, Phenotype, TestResult


class InconsistentEvidence(ValueError):
    """The recorded results cannot all be true under Mendelian inheritance with
    the stated test detection rates. Common real causes: a sample or recording
    error, a new variant, or misattributed parentage. Always route to a human."""


@dataclass
class Factor:
    vars: tuple[str, ...]
    table: np.ndarray


# ---------------------------------------------------------------- evidence ----
def phenotype_likelihood(locus: Locus, ph: Phenotype) -> np.ndarray:
    pv = locus.phenotype_vector
    if ph.affected_with is None:
        return np.array([0.0 if p in locus.affected_phenotypes else 1.0 for p in pv])
    if ph.affected_with not in locus.affected_phenotypes:
        raise ValueError(
            f"'{ph.affected_with}' is not a condition defined for {locus.gene}. "
            f"Known conditions: {sorted(locus.affected_phenotypes)}"
        )
    return np.array([1.0 if p == ph.affected_with else 0.0 for p in pv])


def test_likelihood(locus: Locus, test: TestResult) -> np.ndarray:
    """P(test reports exactly `test.detected` | genotype).

    Each pathogenic copy is reported with its detection rate and missed
    otherwise. Reference copies are never reported (specificity assumed 1;
    see docs/limitations.md)."""
    idx = locus.allele_index
    for a in test.detected:
        if a not in idx:
            raise ValueError(f"Unknown allele '{a}' for {locus.gene}")
        if not locus.alleles[idx[a]].pathogenic:
            raise ValueError(f"'{a}' is the reference allele and cannot be a detected variant")
    if len(test.detected) > 2:
        raise ValueError("A test can report at most two variants at one locus")
    target = sorted(test.detected)
    out = np.zeros(locus.n_genotypes)
    for k, (i, j) in enumerate(locus.genotypes):
        total = 0.0
        for ci in (True, False):
            for cj in (True, False):
                p = 1.0
                reported = []
                for allele_i, called in ((i, ci), (j, cj)):
                    al = locus.alleles[allele_i]
                    if al.pathogenic:
                        p *= al.detection_rate if called else (1 - al.detection_rate)
                        if called:
                            reported.append(al.id)
                    elif called:
                        p = 0.0  # a reference copy cannot be "called"
                if p > 0 and sorted(reported) == target:
                    total += p
        out[k] = total
    return out


# ------------------------------------------------------------------ factors ---
def _letters(names: list[str]) -> dict[str, str]:
    letters = string.ascii_letters
    if len(names) > len(letters):
        raise ValueError("Too many variables in one factor product")
    return {n: letters[k] for k, n in enumerate(names)}


def _product(factors: list[Factor]) -> Factor:
    names: list[str] = []
    for f in factors:
        for v in f.vars:
            if v not in names:
                names.append(v)
    lt = _letters(names)
    spec = ",".join("".join(lt[v] for v in f.vars) for f in factors) + "->" + "".join(lt[v] for v in names)
    return Factor(tuple(names), np.einsum(spec, *[f.table for f in factors]))


def _sum_out(f: Factor, var: str) -> Factor:
    ax = f.vars.index(var)
    return Factor(tuple(v for v in f.vars if v != var), f.table.sum(axis=ax))


def build_factors(
    ped: Pedigree,
    locus: Locus,
    virtual_children: dict[str, tuple[str, str]] | None = None,
    background_f: float = 0.0,
) -> list[Factor]:
    prior = locus.founder_prior(background_f)
    trans = locus.transmission
    factors: list[Factor] = []
    for pid in ped.topological_order():
        p = ped.people[pid]
        if p.mother is None:
            factors.append(Factor((pid,), prior.copy()))
        else:
            factors.append(Factor((p.mother, p.father, pid), trans))  # type: ignore[arg-type]
        if p.phenotype is not None:
            factors.append(Factor((pid,), phenotype_likelihood(locus, p.phenotype)))
        if p.test is not None:
            factors.append(Factor((pid,), test_likelihood(locus, p.test)))
    for child, (mother, father) in (virtual_children or {}).items():
        factors.append(Factor((mother, father, child), trans))
    return factors


# Largest table the engine will build (entries). 2e7 float64 entries is 160 MB.
MAX_FACTOR_ENTRIES = 20_000_000


class PedigreeTooComplex(ValueError):
    """The family tree is too large or interlinked for exact calculation within
    the memory limit. No number is shown; the case goes to a counsellor."""


def plan_elimination(factors: list[Factor], query: tuple[str, ...], card: int) -> list[str]:
    """Greedy min-fill elimination order on the interaction graph (Kjaerulff
    1990; Koller and Friedman 2009, ch. 9). Raises PedigreeTooComplex before
    any table is built if the order would need a table above the limit.

    The order depends only on the factors' scopes (who is linked to whom), not on their values, so it is
    cached: recomputing a family after a new test result reuses the same order and gives identical numbers."""
    scopes = tuple(sorted({f.vars for f in factors}))
    order, width = _plan_cached(scopes, tuple(query))
    # the size limit is checked on every call (not cached), so a changed limit always applies
    if card ** width > MAX_FACTOR_ENTRIES:
        raise PedigreeTooComplex(
            "This family tree is too large or interlinked for an exact calculation in this version.")
    return list(order)


@functools.lru_cache(maxsize=4096)
def _plan_cached(scopes: tuple[tuple[str, ...], ...], query: tuple[str, ...]) -> tuple[tuple[str, ...], int]:
    """Min-fill order and the largest neighbourhood met while eliminating (the widest table's rank)."""
    adj: dict[str, set[str]] = {}
    for vars_ in scopes:
        for v in vars_:
            adj.setdefault(v, set()).update(u for u in vars_ if u != v)
    remaining = set(adj) - set(query)
    order: list[str] = []
    width = 0
    while remaining:
        best, best_key = None, None
        for v in sorted(remaining):
            nb = adj[v]
            nbl = list(nb)
            fill = sum(1 for i in range(len(nbl)) for j in range(i + 1, len(nbl)) if nbl[j] not in adj[nbl[i]])
            key = (fill, len(nb))
            if best_key is None or key < best_key:
                best, best_key = v, key
        assert best is not None
        width = max(width, len(adj[best]))
        nb = adj.pop(best)
        for u in nb:
            adj[u].discard(best)
            adj[u].update(w for w in nb if w != u)
        order.append(best)
        remaining.discard(best)
    return tuple(order), width


def _product_sum_out(factors: list[Factor], var: str) -> Factor:
    """Multiply factors and sum out `var` in one einsum, without building the
    full product table first."""
    names: list[str] = []
    for f in factors:
        for v in f.vars:
            if v not in names:
                names.append(v)
    keep = [v for v in names if v != var]
    lt = _letters(names)
    spec = ",".join("".join(lt[v] for v in f.vars) for f in factors) + "->" + "".join(lt[v] for v in keep)
    tables = [f.table for f in factors]
    path = _einsum_path(spec, tuple(t.shape for t in tables))
    return Factor(tuple(keep), np.einsum(spec, *tables, optimize=path))


@functools.lru_cache(maxsize=65536)
def _einsum_path(spec: str, shapes: tuple[tuple[int, ...], ...]) -> list:
    """The contraction order numpy would choose for these shapes (optimize=True), cached."""
    dummies = [np.empty(sh) for sh in shapes]
    return np.einsum_path(spec, *dummies, optimize=True)[0]


def eliminate(factors: list[Factor], query: tuple[str, ...]) -> tuple[np.ndarray, float]:
    """Return the normalised joint posterior over `query` (in that order) and
    log P(evidence)."""
    factors = list(factors)
    all_vars = {v for f in factors for v in f.vars}
    missing = [q for q in query if q not in all_vars]
    if missing:
        raise KeyError(f"Unknown people in query: {missing}")
    card = max((f.table.shape[0] for f in factors if f.table.ndim), default=1)
    log_z = 0.0
    for var in plan_elimination(factors, query, card):
        involved = [f for f in factors if var in f.vars]
        rest = [f for f in factors if var not in f.vars]
        new = _product_sum_out(involved, var)
        m = new.table.max()
        if m <= 0:
            raise InconsistentEvidence("The recorded results are not compatible with each other.")
        new.table = new.table / m
        log_z += math.log(m)
        factors = rest + [new]

    joint = _product(factors) if factors else Factor((), np.array(1.0))
    # reorder to query order
    perm = [joint.vars.index(q) for q in query]
    table = np.transpose(joint.table, perm) if query else joint.table
    z = table.sum()
    if z <= 0:
        raise InconsistentEvidence("The recorded results are not compatible with each other.")
    return table / z, log_z + math.log(z)


def marginals(
    ped: Pedigree,
    locus: Locus,
    people: list[str] | None = None,
    background_f: float = 0.0,
) -> dict[str, np.ndarray]:
    factors = build_factors(ped, locus, background_f=background_f)
    out = {}
    for pid in people or list(ped.people):
        table, _ = eliminate(factors, (pid,))
        out[pid] = table
    return out


def couple_joint(
    ped: Pedigree, locus: Locus, female: str, male: str, background_f: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Return (joint posterior over the couple's genotypes,
    posterior over a future child's genotype).

    The child is added as a virtual person so that relatedness between the
    partners (shared ancestors) is accounted for exactly."""
    child = f"__child__{female}__{male}"
    factors = build_factors(ped, locus, {child: (female, male)}, background_f)
    joint, _ = eliminate(factors, (female, male))
    child_post, _ = eliminate(factors, (child,))
    return joint, child_post


def log_evidence(ped: Pedigree, locus: Locus, background_f: float = 0.0) -> float:
    factors = build_factors(ped, locus, background_f=background_f)
    _, lz = eliminate(factors, ())
    return lz
