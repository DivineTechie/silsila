"""Locus models for autosomal recessive conditions.

A locus has a set of alleles with population frequencies. A genotype is an
unordered pair of alleles. Each genotype maps to a phenotype label, for example
"unaffected", "carrier" or a named condition such as "sickle cell disease".

The maths here is standard population genetics:
  * Hardy-Weinberg genotype frequencies, optionally with a background
    inbreeding coefficient F (Wright 1922):
        P(i,i) = p_i^2 + F * p_i * (1 - p_i)
        P(i,j) = 2 * p_i * p_j * (1 - F)          for i != j
  * Mendelian transmission: each parent passes one of its two alleles
    with probability 1/2, independently.

No numbers are defined in this module. Allele frequencies, detection rates and
phenotype maps are loaded from the sourced parameter register (data/params).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from itertools import combinations_with_replacement

import numpy as np

UNAFFECTED = "unaffected"


@dataclass(frozen=True)
class Allele:
    """One allele at a locus.

    `pathogenic` is False for the reference (working) allele.
    `detection_rate` is the probability that a carrier test reports this allele
    when a person carries one copy of it (analytical sensitivity). It is 1.0 for
    the reference allele by definition and must be sourced for the others.
    """

    id: str
    label: str
    frequency: float
    pathogenic: bool
    detection_rate: float = 1.0


@dataclass(frozen=True)
class Locus:
    id: str
    gene: str
    alleles: tuple[Allele, ...]
    # Maps a sorted pair of allele ids to a phenotype label. Pairs not listed
    # default to UNAFFECTED for (ref, ref) and must otherwise be listed.
    phenotypes: dict[tuple[str, str], str] = field(default_factory=dict)
    # Phenotype labels that represent being affected by a condition.
    affected_phenotypes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        import math

        if len(self.alleles) < 2 or sum(not a.pathogenic for a in self.alleles) != 1:
            raise ValueError(f"{self.id}: give exactly one reference allele and at least one pathogenic allele")
        for a in self.alleles:
            if not (isinstance(a.frequency, (int, float)) and math.isfinite(a.frequency) and 0 <= a.frequency <= 1):
                raise ValueError(f"{self.id}: frequency of allele {a.id} must be between 0 and 1")
            if not (isinstance(a.detection_rate, (int, float)) and math.isfinite(a.detection_rate)
                    and 0 <= a.detection_rate <= 1):
                raise ValueError(f"{self.id}: detection rate of allele {a.id} must be between 0 and 1")
        total = sum(a.frequency for a in self.alleles)
        if not np.isclose(total, 1.0, atol=1e-9):
            raise ValueError(f"Allele frequencies at {self.id} sum to {total}, expected 1")
        ids = [a.id for a in self.alleles]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate allele ids at {self.id}")
        for g in self.genotypes:
            if self.phenotype_of(g) is None:
                raise ValueError(f"No phenotype defined for genotype {g} at {self.id}")
        unused = set(self.affected_phenotypes) - set(self.phenotype_of(g) for g in self.genotypes)
        if unused:
            raise ValueError(f"{self.id}: affected label(s) {sorted(unused)} are not produced by any genotype")

    # ---- genotype space -------------------------------------------------
    @cached_property
    def allele_index(self) -> dict[str, int]:
        return {a.id: i for i, a in enumerate(self.alleles)}

    @cached_property
    def genotypes(self) -> tuple[tuple[int, int], ...]:
        """All unordered genotypes as sorted index pairs (i <= j)."""
        return tuple(combinations_with_replacement(range(len(self.alleles)), 2))

    @cached_property
    def genotype_index(self) -> dict[tuple[int, int], int]:
        return {g: k for k, g in enumerate(self.genotypes)}

    @property
    def n_genotypes(self) -> int:
        return len(self.genotypes)

    def genotype_label(self, g: tuple[int, int]) -> str:
        return "/".join(self.alleles[i].id for i in g)

    def phenotype_of(self, g: tuple[int, int]) -> str | None:
        a, b = (self.alleles[i].id for i in g)
        key = tuple(sorted((a, b)))
        if key in self.phenotypes:
            return self.phenotypes[key]
        if not self.alleles[g[0]].pathogenic and not self.alleles[g[1]].pathogenic:
            return UNAFFECTED
        return None

    @cached_property
    def phenotype_vector(self) -> tuple[str, ...]:
        return tuple(self.phenotype_of(g) for g in self.genotypes)  # type: ignore[misc]

    def pathogenic_copies(self, g: tuple[int, int]) -> int:
        return sum(1 for i in g if self.alleles[i].pathogenic)

    # ---- probability tables ----------------------------------------------
    def founder_prior(self, background_f: float = 0.0) -> np.ndarray:
        """Genotype frequencies for a founder (Hardy-Weinberg with optional F)."""
        if not 0.0 <= background_f < 1.0:
            raise ValueError("background_f must be in [0, 1)")
        p = np.array([a.frequency for a in self.alleles])
        prior = np.empty(self.n_genotypes)
        for k, (i, j) in enumerate(self.genotypes):
            if i == j:
                prior[k] = p[i] ** 2 + background_f * p[i] * (1 - p[i])
            else:
                prior[k] = 2 * p[i] * p[j] * (1 - background_f)
        return prior / prior.sum()

    @cached_property
    def transmission(self) -> np.ndarray:
        """T[mother_g, father_g, child_g] = P(child genotype | parents)."""
        n = self.n_genotypes
        t = np.zeros((n, n, n))
        for gm, (m1, m2) in enumerate(self.genotypes):
            for gf, (f1, f2) in enumerate(self.genotypes):
                for am in (m1, m2):
                    for af in (f1, f2):
                        child = tuple(sorted((am, af)))
                        t[gm, gf, self.genotype_index[child]] += 0.25
        return t

    def allele_transmission(self) -> np.ndarray:
        """A[g, allele] = P(parent with genotype g transmits allele)."""
        a = np.zeros((self.n_genotypes, len(self.alleles)))
        for k, (i, j) in enumerate(self.genotypes):
            a[k, i] += 0.5
            a[k, j] += 0.5
        return a
