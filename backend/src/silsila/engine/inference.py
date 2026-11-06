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


def eliminate(factors: list[Factor], query: tuple[str, ...]) -> tuple[np.ndarray, float]:
    """Return the normalised joint posterior over `query` (in that order) and
    log P(evidence)."""
    factors = list(factors)
    all_vars = {v for f in factors for v in f.vars}
    missing = [q for q in query if q not in all_vars]
    if missing:
        raise KeyError(f"Unknown people in query: {missing}")
    to_eliminate = all_vars - set(query)
    log_z = 0.0

    while to_eliminate:
        # greedy min-size heuristic: eliminate the variable whose product is smallest
        def cost(v: str) -> int:
            scope: set[str] = set()
            for f in factors:
                if v in f.vars:
                    scope.update(f.vars)
            return len(scope)

        var = min(sorted(to_eliminate), key=cost)
        involved = [f for f in factors if var in f.vars]
        rest = [f for f in factors if var not in f.vars]
        new = _sum_out(_product(involved), var)
        m = new.table.max()
        if m <= 0:
            raise InconsistentEvidence("The recorded results are not compatible with each other.")
        new.table = new.table / m
        log_z += math.log(m)
        factors = rest + [new]
        to_eliminate.discard(var)

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
