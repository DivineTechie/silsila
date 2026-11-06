"""Pedigree structure, validation and kinship.

A pedigree is a set of people with optional mother and father links. People
without parents in the pedigree are founders and are treated as unrelated
members of the population. Consanguinity is represented exactly by shared
ancestors, so a first-cousin marriage is two people whose parents are siblings.

Kinship coefficients use the standard recursive definition (Malecot 1948):
  phi(i, i) = (1 + F_i) / 2, where F_i = phi(mother_i, father_i)
  phi(i, j) = (phi(mother_i, j) + phi(father_i, j)) / 2, when i is not an
              ancestor of j (recurse on the younger individual).
The inbreeding coefficient of a child equals the kinship of its parents.
For example first cousins have phi = 1/16.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache


class Sex(str, Enum):
    FEMALE = "female"
    MALE = "male"


@dataclass(frozen=True)
class Phenotype:
    """Clinically known phenotype for one locus.

    affected_with: the phenotype label the person is affected with, or None to
    record that the person is known to be unaffected by any condition at the
    locus (full penetrance assumed; see docs/limitations.md).
    """

    affected_with: str | None


@dataclass(frozen=True)
class TestResult:
    """Carrier or diagnostic test result for one locus.

    detected: allele ids reported by the test (0, 1 or 2 entries). An empty
    tuple is a negative test. Undetected pathogenic alleles are modelled with
    each allele's detection rate, which produces residual risk after a
    negative result.
    """

    __test__ = False  # not a pytest test class

    detected: tuple[str, ...] = ()


@dataclass
class Person:
    id: str
    sex: Sex
    mother: str | None = None
    father: str | None = None
    display_name: str | None = None
    phenotype: Phenotype | None = None
    test: TestResult | None = None
    pregnant: bool = False
    deceased: bool = False


@dataclass(frozen=True)
class Union:
    """A couple. Couples with shared children are found automatically; this
    records couples without children in the pedigree (for example a married
    couple planning a first pregnancy)."""

    a: str
    b: str


class PedigreeError(ValueError):
    pass


@dataclass
class Pedigree:
    people: dict[str, Person] = field(default_factory=dict)
    unions: list[Union] = field(default_factory=list)

    @classmethod
    def from_people(cls, people: list[Person], unions: list[Union] | None = None) -> "Pedigree":
        ped = cls({p.id: p for p in people}, list(unions or []))
        if len(ped.people) != len(people):
            raise PedigreeError("Duplicate person ids")
        ped.validate()
        return ped

    # ---- validation -------------------------------------------------------
    def validate(self) -> None:
        for p in self.people.values():
            if not isinstance(p.sex, Sex):
                raise PedigreeError(f"{p.id}: sex must be female or male")
            if p.pregnant and (p.sex != Sex.FEMALE or p.deceased):
                raise PedigreeError(f"{p.id}: only a living woman can be marked as pregnant")
            if (p.mother is None) != (p.father is None):
                raise PedigreeError(
                    f"{p.id}: give both parents or neither. Add the missing parent as a person "
                    "with no details if they are unknown."
                )
            for role, pid, sex in (("mother", p.mother, Sex.FEMALE), ("father", p.father, Sex.MALE)):
                if pid is None:
                    continue
                if pid not in self.people:
                    raise PedigreeError(f"{p.id}: {role} '{pid}' is not in the family tree")
                if self.people[pid].sex != sex:
                    raise PedigreeError(f"{p.id}: {role} '{pid}' must be {sex.value}")
        for u in self.unions:
            for pid in (u.a, u.b):
                if pid not in self.people:
                    raise PedigreeError(f"Couple refers to unknown person '{pid}'")
            if self.people[u.a].sex == self.people[u.b].sex:
                raise PedigreeError(f"Couple {u.a} and {u.b} must be one female and one male")
        self.topological_order()  # raises on cycles

    def topological_order(self) -> list[str]:
        order: list[str] = []
        state: dict[str, int] = {}

        def visit(pid: str) -> None:
            s = state.get(pid, 0)
            if s == 1:
                raise PedigreeError(f"Family tree has a loop through '{pid}' (a person is their own ancestor)")
            if s == 2:
                return
            state[pid] = 1
            p = self.people[pid]
            for parent in (p.mother, p.father):
                if parent:
                    visit(parent)
            state[pid] = 2
            order.append(pid)

        for pid in self.people:
            visit(pid)
        return order

    # ---- structure ----------------------------------------------------------
    def is_founder(self, pid: str) -> bool:
        return self.people[pid].mother is None

    def children_of(self, pid: str) -> list[str]:
        return [c.id for c in self.people.values() if pid in (c.mother, c.father)]

    def couples(self) -> list[tuple[str, str]]:
        """All couples as (female_id, male_id), from shared children and unions."""
        seen: set[tuple[str, str]] = set()
        for p in self.people.values():
            if p.mother and p.father:
                seen.add((p.mother, p.father))
        for u in self.unions:
            a, b = self.people[u.a], self.people[u.b]
            seen.add((a.id, b.id) if a.sex == Sex.FEMALE else (b.id, a.id))
        return sorted(seen)

    def partner_of(self, pid: str) -> list[str]:
        out = []
        for f, m in self.couples():
            if f == pid:
                out.append(m)
            elif m == pid:
                out.append(f)
        return out

    # ---- kinship -------------------------------------------------------------
    def kinship(self, i: str, j: str) -> float:
        order = {pid: k for k, pid in enumerate(self.topological_order())}

        @lru_cache(maxsize=None)
        def phi(a: str, b: str) -> float:
            if a == b:
                pa = self.people[a]
                if pa.mother is None:
                    return 0.5
                return 0.5 * (1 + phi(pa.mother, pa.father))  # type: ignore[arg-type]
            # recurse on the one later in topological order (cannot be an ancestor of the other)
            if order[a] < order[b]:
                a, b = b, a
            pa = self.people[a]
            if pa.mother is None:
                return 0.0
            return 0.5 * (phi(pa.mother, b) + phi(pa.father, b))  # type: ignore[arg-type]

        return phi(i, j)

    def inbreeding_of_offspring(self, female: str, male: str) -> float:
        return self.kinship(female, male)
