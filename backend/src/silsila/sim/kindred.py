"""Synthetic multi-generation kindreds for benchmarking (SYNTHETIC DATA).

A kindred grows down from one founding couple (generation 0). Each couple has
a Poisson number of children; each adult child either stays unmarried or
marries. A marriage is either inside the kindred (double first cousin, first
cousin, second cousin) or to a spouse from outside the drawn tree. Outside
spouses are founders and come from one of three groups:

  * "distant_relative": same clan as the kindred, related further back than
    the drawn tree shows (counted as consanguineous, as surveys do for
    'other relatives');
  * "same_clan": same tribe / biradri, not known to be related;
  * "other_clan": a different tribe / biradri.

Clan membership is what lets the genetic simulation (silsila.sim.genedrop) give
same-clan founders correlated allele frequencies. The engine never sees clans:
for the engine every founder is an unrelated member of the population, exactly
as in the app.

Relationship types for marriages inside the kindred are classified from the
genealogy (shared grandparents, shared great-grandparents), and every couple's
kinship coefficient is also computed so the achieved relationships can be
audited against Malecot's values (1/8, 1/16, 1/64).

Marriage choice: in each generation, adults who marry are visited in random
order; each one draws a requested relationship type from the request mix and
is paired with a random unmarried opposite-sex relative of that type if one
exists, otherwise with a same-clan outside spouse ("fallback"). Because some
types are impossible in early generations (second cousins need three
generations of depth), the request mix that achieves a target mix is found by
`calibrate_request_mix`; the target, the request mix and the ACHIEVED mix are
always reported.

Double first cousins need two siblings who married two siblings. When two
same-sex siblings both marry outside the kindred into the same clan group, the
two spouses are, with probability `exchange_prob` (a generator setting with no
population meaning; it only creates the opportunity), siblings from one outside
family (whose parents are added as founders).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from ..engine import Pedigree, Person, Sex

IN_KINDRED = ("double_first_cousin", "first_cousin", "second_cousin")
OUTSIDE = ("distant_relative", "same_clan", "other_clan")
ALL_TYPES = IN_KINDRED + OUTSIDE
CONSANGUINEOUS = ("double_first_cousin", "first_cousin", "second_cousin", "distant_relative")
# If the requested relative type is not available, the closest other type of
# relative is tried before falling back to a same-clan spouse.
FALLBACK = {
    "first_cousin": ("first_cousin", "second_cousin", "double_first_cousin"),
    "second_cousin": ("second_cousin", "first_cousin", "double_first_cousin"),
    "double_first_cousin": ("double_first_cousin", "first_cousin", "second_cousin"),
}
EXPECTED_KINSHIP = {"double_first_cousin": 1 / 8, "first_cousin": 1 / 16, "second_cousin": 1 / 64}


@dataclass
class KindredConfig:
    n_generations: int = 5                 # generations 0..n-1; the last are children
    sibship_mean: float = 4.0              # Poisson mean children per couple
    marriage_prob: float = 0.85            # adult kindred member marries
    p_living_grandparent_gen: float = 0.7  # living probability, generation n-3
    request_mix: dict[str, float] = field(default_factory=lambda: {"first_cousin": 0.3, "same_clan": 0.4, "other_clan": 0.3})
    exchange_prob: float = 1.0
    in_kindred_fallback: bool = True
    generation_interval_years: float = 28.0  # display only (ages); no effect on genetics

    def normalised_mix(self) -> dict[str, float]:
        tot = sum(self.request_mix.values())
        return {t: self.request_mix.get(t, 0.0) / tot for t in ALL_TYPES}


@dataclass
class CoupleRecord:
    female: str
    male: str
    generation: int
    requested: str
    achieved: str
    kinship: float = 0.0


@dataclass
class Kindred:
    pedigree: Pedigree
    generation: dict[str, int]
    clan: dict[str, int]                 # founders only: 0 = kindred clan, >0 another clan
    blood: set[str]                      # descendants of the founding couple (incl. them)
    age: dict[str, float]
    couples: list[CoupleRecord]
    n_generations: int

    @property
    def youngest(self) -> int:
        return self.n_generations - 1

    def living(self) -> list[str]:
        return [p for p, x in self.pedigree.people.items() if not x.deceased]

    def is_adult(self, pid: str) -> bool:
        return self.generation[pid] < self.youngest

    def counted_couples(self) -> list[CoupleRecord]:
        """Couples in the generations where marriages are chosen by the mix
        (generation >= 2: generation 1 can only marry outside the kindred)."""
        return [c for c in self.couples if c.generation >= 2]

    def achieved_mix(self, couples: list[CoupleRecord] | None = None) -> Counter:
        return Counter(c.achieved for c in (self.counted_couples() if couples is None else couples))


# ------------------------------------------------------------- genealogy ---
def _ancestors_at(ped: Pedigree, pid: str, depth: int) -> frozenset[str]:
    level = {pid}
    for _ in range(depth):
        nxt = set()
        for q in level:
            p = ped.people[q]
            if p.mother is not None:
                nxt.update((p.mother, p.father))  # type: ignore[arg-type]
        level = nxt
    return frozenset(level)


def _classify(a1, b1, a2, b2, a3, b3) -> str | None:
    if a1 and a1 == b1:
        return "sibling"
    if a1 & b1:
        return "half_sibling"
    if len(a2) == 4 and a2 == b2:
        return "double_first_cousin"
    if a2 & b2:
        return "first_cousin"
    if a3 & b3:
        return "second_cousin"
    return None


def relationship(ped: Pedigree, a: str, b: str) -> str | None:
    """Closest genealogical relationship of two people of the same generation:
    'sibling', 'half_sibling', 'double_first_cousin', 'first_cousin',
    'second_cousin' or None (not related within the drawn tree)."""
    anc = [(_ancestors_at(ped, x, 1), _ancestors_at(ped, x, 2), _ancestors_at(ped, x, 3)) for x in (a, b)]
    return _classify(anc[0][0], anc[1][0], anc[0][1], anc[1][1], anc[0][2], anc[1][2])


def kinship_matrix(ped: Pedigree) -> tuple[list[str], np.ndarray]:
    """Full kinship matrix by the standard recursion over a topological order
    (independent of Pedigree.kinship, which tests compare it against)."""
    order = ped.topological_order()
    idx = {p: k for k, p in enumerate(order)}
    n = len(order)
    k = np.zeros((n, n))
    for i, pid in enumerate(order):
        p = ped.people[pid]
        if p.mother is None:
            k[i, i] = 0.5
            continue
        m, f = idx[p.mother], idx[p.father]  # type: ignore[index]
        row = 0.5 * (k[m, :i] + k[f, :i])
        k[i, :i] = row
        k[:i, i] = row
        k[i, i] = 0.5 * (1 + k[m, f])
    return order, k


# -------------------------------------------------------------- generator --
class _Builder:
    def __init__(self, cfg: KindredConfig, rng: np.random.Generator):
        self.cfg, self.rng = cfg, rng
        self.people: dict[str, Person] = {}
        self.gen: dict[str, int] = {}
        self.clan: dict[str, int] = {}
        self.blood: set[str] = set()
        self.couples: list[CoupleRecord] = []
        self.n = 0
        self.next_clan = 1

    def new_id(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n}"

    def add(self, sex: Sex, gen: int, mother=None, father=None, prefix="k", clan=None) -> str:
        pid = self.new_id(prefix)
        self.people[pid] = Person(pid, sex, mother, father)
        self.gen[pid] = gen
        if mother is None and clan is not None:
            self.clan[pid] = clan
        return pid

    def outside_clan(self, kind: str) -> int:
        if kind == "other_clan":
            self.next_clan += 1
            return self.next_clan
        return 0


def _opposite(s: Sex) -> Sex:
    return Sex.MALE if s == Sex.FEMALE else Sex.FEMALE


def generate_kindred(cfg: KindredConfig, rng: np.random.Generator) -> Kindred:
    b = _Builder(cfg, rng)
    mix = cfg.normalised_mix()
    types, probs = list(mix), np.array(list(mix.values()))
    youngest = cfg.n_generations - 1

    f0 = b.add(Sex.FEMALE, 0, clan=0)
    m0 = b.add(Sex.MALE, 0, clan=0)
    b.blood.update((f0, m0))
    current_couples = [(f0, m0)]

    for g in range(1, cfg.n_generations):
        members: list[str] = []
        for mother, father in current_couples:
            for _ in range(int(rng.poisson(cfg.sibship_mean))):
                sex = Sex.FEMALE if rng.random() < 0.5 else Sex.MALE
                c = b.add(sex, g, mother, father)
                b.blood.add(c)
                members.append(c)
        if g == youngest:
            break
        marrying = [c for c in members if rng.random() < cfg.marriage_prob]
        order = list(marrying)
        rng.shuffle(order)
        unpaired = set(marrying)
        ped_now = Pedigree(b.people)
        anc = {x: (_ancestors_at(ped_now, x, 1), _ancestors_at(ped_now, x, 2), _ancestors_at(ped_now, x, 3)) for x in marrying}
        new_couples: list[tuple[str, str]] = []
        outside_requests: list[tuple[str, str, str]] = []   # (member, requested, kind)
        for x in order:
            if x not in unpaired:
                continue
            req = types[int(rng.choice(len(types), p=probs))]
            partner, got = None, req
            if req in IN_KINDRED and g >= 2:
                sx = b.people[x].sex
                ax = anc[x]
                rel = {
                    y: _classify(ax[0], anc[y][0], ax[1], anc[y][1], ax[2], anc[y][2])
                    for y in sorted(unpaired)
                    if y != x and b.people[y].sex != sx
                }
                for t in FALLBACK[req] if cfg.in_kindred_fallback else (req,):
                    cands = [y for y, r in rel.items() if r == t]
                    if cands:
                        partner, got = cands[int(rng.integers(len(cands)))], t
                        break
            unpaired.discard(x)
            if partner is not None:
                unpaired.discard(partner)
                fem, mal = (x, partner) if b.people[x].sex == Sex.FEMALE else (partner, x)
                new_couples.append((fem, mal))
                b.couples.append(CoupleRecord(fem, mal, g, req, got))
            else:
                kind = req if req in OUTSIDE else "same_clan"
                outside_requests.append((x, req, kind))

        # outside spouses; same-sex siblings marrying into the same group may
        # marry two siblings of one outside family (creates double-cousin options)
        by_family: dict[tuple, list[tuple[str, str, str]]] = {}
        for x, req, kind in outside_requests:
            p = b.people[x]
            by_family.setdefault((p.mother, p.father, p.sex, kind), []).append((x, req, kind))
        for (_, _, sex, kind), lst in by_family.items():
            rng.shuffle(lst)
            while lst:
                if len(lst) >= 2 and rng.random() < cfg.exchange_prob:
                    pair, lst = lst[:2], lst[2:]
                    clan = b.outside_clan(kind)
                    of = b.add(Sex.FEMALE, g - 1, prefix="o", clan=clan)
                    om = b.add(Sex.MALE, g - 1, prefix="o", clan=clan)
                    spouses = [b.add(_opposite(sex), g, of, om, prefix="s") for _ in pair]
                else:
                    pair, lst = lst[:1], lst[1:]
                    clan = b.outside_clan(kind)
                    spouses = [b.add(_opposite(sex), g, prefix="s", clan=clan)]
                for (x, req, kind_), s in zip(pair, spouses):
                    fem, mal = (x, s) if sex == Sex.FEMALE else (s, x)
                    new_couples.append((fem, mal))
                    b.couples.append(CoupleRecord(fem, mal, g, req, kind_))
        current_couples = new_couples
        if not current_couples:
            break

    ped = Pedigree(b.people)
    ped.validate()
    order, kmat = kinship_matrix(ped)
    idx = {p: i for i, p in enumerate(order)}
    for c in b.couples:
        c.kinship = float(kmat[idx[c.female], idx[c.male]])

    # living status and ages (ages are display-only)
    age: dict[str, float] = {}
    for pid, p in ped.people.items():
        g = b.gen[pid]
        offset = youngest - g
        if offset >= 3:
            p.deceased = True
        elif offset == 2:
            p.deceased = bool(rng.random() >= cfg.p_living_grandparent_gen)
        age[pid] = float(rng.uniform(0, 18) + offset * cfg.generation_interval_years)
    return Kindred(ped, b.gen, b.clan, b.blood, age, b.couples, cfg.n_generations)


# ------------------------------------------------------- mix calibration ---
def achieved_mix_over(kindreds: list[Kindred]) -> dict[str, float]:
    tot: Counter = Counter()
    for k in kindreds:
        tot.update(k.achieved_mix())
    n = sum(tot.values())
    return {t: tot.get(t, 0) / n if n else 0.0 for t in ALL_TYPES}


def calibrate_request_mix(
    cfg: KindredConfig, target: dict[str, float], seed: int, n_kindreds: int = 200, iterations: int = 12
) -> tuple[dict[str, float], dict[str, float]]:
    """Find a request mix whose ACHIEVED mix (over counted couples) matches
    `target`, by multiplicative fixed-point updates. Returns (request mix,
    achieved mix). This tunes a generator setting, not a population
    parameter; both mixes are reported."""
    tgt = {t: target.get(t, 0.0) for t in ALL_TYPES}
    req = dict(tgt)
    achieved = tgt
    for it in range(iterations):
        rng = np.random.default_rng(seed + it)
        c = KindredConfig(**{**cfg.__dict__, "request_mix": req})
        ks = [generate_kindred(c, rng) for _ in range(n_kindreds)]
        achieved = achieved_mix_over(ks)
        new = {}
        for t in ALL_TYPES:
            if tgt[t] == 0:
                new[t] = 0.0
            else:
                new[t] = req[t] * (tgt[t] / max(achieved[t], 1e-3)) ** 0.8
        s = sum(new.values())
        req = {t: v / s for t, v in new.items()}
    return req, achieved
