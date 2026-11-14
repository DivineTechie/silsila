"""Deterministic Silsila-Bench item generator (SYNTHETIC, FICTIONAL families).

Implements the "Items" section of PREREGISTRATION.md:

* 150 families from `silsila.sim.kindred.generate_kindred` with fixed seeds: 50 with no cousin marriage
  ("no_loop"), 50 with exactly one first-cousin marriage ("one_loop"), 50 with two or more consanguineous
  marriages ("multiple"; at least `MIN_DOUBLE` of them contain a double-first-cousin marriage).
* Loci HBB, CYP21A2 and SMN1 (round-robin within each family type), parameters from data/params/loci.yaml
  via `silsila.params.load()`.
* One affected index person, everyone else recorded as unaffected, and some recorded carrier results.
* Two questions per family: (a) carrier chance of a named untested relative, (b) chance that a named
  couple's child is affected. Gold answers come from the exact engine with the population background
  inbreeding used by the app; the F = 0 value is stored too as a sensitivity check.

A full kindred is too large to tell as a story, so each family is the part of the kindred a person would
describe: the index child, their parents and some siblings, the parents' siblings with partners and
some cousins, the chosen consanguineous couples, and every ancestor needed to connect them (so drawn
loops are exact). Carrier results are sampled one person at a time from the engine's own posterior
given the evidence so far, so every family is internally consistent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from silsila import params
from silsila.engine import (
    InconsistentEvidence,
    Pedigree,
    PedigreeTooComplex,
    Person,
    Phenotype,
    Sex,
    TestResult,
    Union,
    couple_risk,
    person_risks,
)
from silsila.engine import inference
from silsila.sim.kindred import Kindred, KindredConfig, generate_kindred, relationship

from . import names as N

FAMILY_TYPES = ("no_loop", "one_loop", "multiple")
LOCI = ("HBB", "CYP21A2", "SMN1")
N_PER_TYPE = 50
MIN_DOUBLE = 15                   # "multiple" families that include a double-first-cousin marriage
SEED_BASE = {"no_loop": 1_000_000, "one_loop": 2_000_000, "multiple": 3_000_000}
MAX_ATTEMPTS = 20_000
MIN_PEOPLE, MAX_PEOPLE = 8, 26
REGISTERS = ("en", "msa", "gulf", "arabizi")
TRACK_REGISTERS = {"T1": REGISTERS, "T2": ("en", "gulf"), "T3": ("en", "gulf"), "T5": ("en",)}
BENCH_DIR = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------- data ---
@dataclass
class PersonRec:
    id: str                    # Latin first name, unique in the family; also the engine id
    name_ar: str
    sex: str                   # "female" | "male"
    mother: str | None
    father: str | None
    deceased: bool
    generation: int
    status: str                # "affected" | "unaffected"
    affected_with: str | None
    test_detected: list[str] | None   # None = not tested; [] = tested negative


@dataclass
class Question:
    qid: str                   # "a" (carrier) | "b" (child affected)
    type: str                  # "carrier" | "child_affected"
    person: str | None = None
    couple: tuple[str, str] | None = None   # (female, male)
    couple_has_children: bool = False
    gold: float = 0.0
    gold_f0: float = 0.0       # same question with background inbreeding 0 (sensitivity only)


@dataclass
class Family:
    family_id: str
    family_type: str
    seed: int
    locus: str
    background_f: float
    people: dict[str, PersonRec]
    unions: list[tuple[str, str]]          # couples without a shared child in the drawn tree
    couples: list[tuple[str, str]]         # all couples (female, male), drawn order
    consanguineous: list[dict[str, Any]]   # {female, male, relationship, kinship}
    index: str
    narrator: str
    questions: list[Question] = field(default_factory=list)

    # ---- helpers -------------------------------------------------------
    def pedigree(self) -> Pedigree:
        return gold_pedigree(self)

    def question(self, qid: str) -> Question:
        return next(q for q in self.questions if q.qid == qid)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["questions"] = [asdict(q) for q in self.questions]
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Family":
        d = dict(d)
        d["people"] = {k: PersonRec(**v) for k, v in d["people"].items()}
        d["unions"] = [tuple(u) for u in d["unions"]]
        d["couples"] = [tuple(c) for c in d["couples"]]
        qs = []
        for q in d.pop("questions"):
            q = dict(q)
            if q.get("couple") is not None:
                q["couple"] = tuple(q["couple"])
            qs.append(Question(**q))
        return cls(**d, questions=qs)

    def gold_tree(self) -> dict[str, Any]:
        """Gold family tree in the same JSON shape the model tools use."""
        return {
            "gene": self.locus,
            "people": [
                {"id": p.id, "sex": p.sex, "mother": p.mother, "father": p.father, "status": p.status,
                 "affected_with": p.affected_with, "test_detected": p.test_detected}
                for p in self.people.values()
            ],
            "unions": [{"a": a, "b": b} for a, b in self.unions],
        }

    def name_index(self) -> dict[str, str]:
        """Normalised name in any script -> person id."""
        out: dict[str, str] = {}
        for p in self.people.values():
            out[N.normalise(p.id)] = p.id
            out[N.normalise(p.name_ar)] = p.id
        return out


@dataclass
class Item:
    item_id: str
    track: str
    family_id: str
    family_type: str
    locus: str
    register: str
    qid: str | None            # None for T3 (whole tree)


def gold_pedigree(fam: Family, *, evidence: bool = True) -> Pedigree:
    people = []
    for p in fam.people.values():
        ph = test = None
        if evidence:
            ph = Phenotype(p.affected_with if p.status == "affected" else None)
            test = None if p.test_detected is None else TestResult(tuple(sorted(p.test_detected)))
        people.append(Person(p.id, Sex(p.sex), p.mother, p.father, phenotype=ph, test=test, deceased=p.deceased))
    return Pedigree.from_people(people, [Union(a, b) for a, b in fam.unions])


def gold_answer(fam: Family, q: Question, background_f: float | None = None) -> float:
    rec = params.load()[fam.locus]
    bf = rec.background_f if background_f is None else background_f
    ped = gold_pedigree(fam)
    if q.type == "carrier":
        return person_risks(ped, rec.locus, bf)[q.person].p_carrier  # type: ignore[index]
    f, m = q.couple  # type: ignore[misc]
    return couple_risk(ped, rec.locus, f, m, bf).p_child_affected


# ------------------------------------------------------------ generator ---
def _config(ftype: str, rng: np.random.Generator) -> KindredConfig:
    if ftype == "no_loop":
        return KindredConfig(n_generations=4, sibship_mean=3.0, request_mix={"same_clan": 0.6, "other_clan": 0.4},
                             exchange_prob=0.0)
    if ftype == "one_loop":
        return KindredConfig(n_generations=4, sibship_mean=3.0,
                             request_mix={"first_cousin": 0.35, "same_clan": 0.4, "other_clan": 0.25},
                             exchange_prob=0.0)
    n_gen = 5 if rng.random() < 0.4 else 4
    return KindredConfig(n_generations=n_gen, sibship_mean=3.0,
                         request_mix={"first_cousin": 0.45, "double_first_cousin": 0.25, "second_cousin": 0.1,
                                      "same_clan": 0.2},
                         exchange_prob=1.0)


def _children(k: Kindred) -> dict[str, list[str]]:
    ch: dict[str, list[str]] = {p: [] for p in k.pedigree.people}
    for p in k.pedigree.people.values():
        if p.mother:
            ch[p.mother].append(p.id)
            ch[p.father].append(p.id)  # type: ignore[index]
    return ch


def _siblings(k: Kindred, pid: str, ch: dict[str, list[str]]) -> list[str]:
    p = k.pedigree.people[pid]
    if p.mother is None:
        return []
    return [c for c in ch[p.mother] if c != pid and k.pedigree.people[c].father == p.father]


def _pick(rng: np.random.Generator, xs: list, n: int) -> list:
    xs = sorted(xs)
    if len(xs) <= n:
        return xs
    idx = rng.choice(len(xs), size=n, replace=False)
    return [xs[i] for i in sorted(idx)]


def _closure(k: Kindred, focus: set[str]) -> set[str]:
    out = set(focus)
    stack = list(focus)
    while stack:
        x = stack.pop()
        p = k.pedigree.people[x]
        for par in (p.mother, p.father):
            if par is not None and par not in out:
                out.add(par)
                stack.append(par)
    return out


def _sample_affected_label(rec, rng: np.random.Generator) -> str:
    loc = rec.locus
    prior = loc.founder_prior(0.0)
    labs, w = [], []
    for k, ph in enumerate(loc.phenotype_vector):
        if ph in loc.affected_phenotypes:
            labs.append(ph)
            w.append(prior[k])
    w = np.array(w) / sum(w)
    return labs[int(rng.choice(len(labs), p=w))]


def _sample_test(rec, ped: Pedigree, pid: str, rng: np.random.Generator) -> TestResult:
    """Draw a test result for `pid` from the engine's posterior given the evidence already in `ped`."""
    loc = rec.locus
    post = inference.marginals(ped, loc, [pid], background_f=rec.background_f)[pid]
    g = loc.genotypes[int(rng.choice(len(post), p=post / post.sum()))]
    detected = []
    for ai in g:
        a = loc.alleles[ai]
        if a.pathogenic and rng.random() < a.detection_rate:
            detected.append(a.id)
    return TestResult(tuple(sorted(detected)))


def build_family(ftype: str, seed: int, locus_id: str, family_id: str) -> Family | None:
    """Build one family of the requested type from `seed`, or None if this seed does not give one."""
    rng = np.random.default_rng(seed)
    cfg = _config(ftype, rng)
    k = generate_kindred(cfg, rng)
    kp = k.pedigree
    youngest = [p for p in kp.people if k.generation[p] == k.youngest]
    if not youngest:
        return None
    ch = _children(k)
    cons_all = [c for c in k.couples if c.kinship > 0]

    def cons_parents(x: str) -> bool:
        p = kp.people[x]
        return any(c.female == p.mother and c.male == p.father for c in cons_all)

    prefer = [y for y in youngest if cons_parents(y)]
    pool = prefer if (ftype != "no_loop" and prefer and rng.random() < 0.75) else youngest
    index = sorted(pool)[int(rng.integers(len(pool)))]
    mother, father = kp.people[index].mother, kp.people[index].father

    focus: set[str] = {index, mother, father}  # type: ignore[arg-type]
    focus.update(_pick(rng, _siblings(k, index, ch), 2))
    partners: dict[str, list[str]] = {}
    for c in k.couples:
        partners.setdefault(c.female, []).append(c.male)
        partners.setdefault(c.male, []).append(c.female)
    for par in (mother, father):
        sibs = _pick(rng, _siblings(k, par, ch), 2)  # type: ignore[arg-type]
        focus.update(sibs)
        with_kids = [s for s in sibs if ch[s]]
        if with_kids:
            s = with_kids[int(rng.integers(len(with_kids)))]
            focus.update(_pick(rng, ch[s], 2))
    if ftype != "no_loop":
        extra = [c for c in cons_all if c.generation >= k.youngest - 2 and (c.female, c.male) != (mother, father)]
        n_extra = 0 if ftype == "one_loop" and cons_parents(index) else (1 if ftype == "one_loop" else int(rng.integers(1, 3)))
        for c in _pick(rng, [(c.female, c.male) for c in extra], n_extra):
            focus.update(c)
    for x in list(focus):
        if k.generation[x] < k.youngest:
            focus.update(partners.get(x, []))
    drawn = _closure(k, focus)
    if not (MIN_PEOPLE <= len(drawn) <= MAX_PEOPLE):
        return None

    # drawn pedigree (structure only)
    order = sorted(drawn, key=lambda x: (k.generation[x], x))
    sp = [Person(x, kp.people[x].sex, kp.people[x].mother, kp.people[x].father, deceased=kp.people[x].deceased)
          for x in order]
    with_child = {(kp.people[x].mother, kp.people[x].father) for x in drawn if kp.people[x].mother}
    unions = [(c.female, c.male) for c in k.couples
              if c.female in drawn and c.male in drawn and (c.female, c.male) not in with_child]
    ped = Pedigree.from_people(sp, [Union(a, b) for a, b in unions])
    couples = ped.couples()
    cons = []
    for f, m in couples:
        kin = ped.kinship(f, m)
        if kin > 0:
            cons.append({"female": f, "male": m, "relationship": relationship(ped, f, m) or "other", "kinship": kin})
    if ftype == "no_loop" and cons:
        return None
    if ftype == "one_loop" and not (len(cons) == 1 and cons[0]["relationship"] == "first_cousin"):
        return None
    if ftype == "multiple" and len(cons) < 2:
        return None

    # evidence: index affected, everyone else unaffected, some carrier tests
    rec = params.load()[locus_id]
    label = _sample_affected_label(rec, rng)
    for p in ped.people.values():
        p.phenotype = Phenotype(label if p.id == index else None)
    living_adults = [x for x in order if not ped.people[x].deceased and k.generation[x] < k.youngest]
    tested: list[str] = [x for x in (mother, father) if rng.random() < 0.6]  # type: ignore[misc]
    others = [x for x in living_adults if x not in (mother, father)]
    tested += _pick(rng, others, int(rng.integers(1, 4)))
    if not tested:
        return None
    try:
        for x in sorted(tested, key=lambda x: order.index(x)):
            ped.people[x].test = _sample_test(rec, ped, x, rng)
        risks = person_risks(ped, rec.locus, rec.background_f)
    except (InconsistentEvidence, PedigreeTooComplex):
        return None

    # questions
    def blood(x: str) -> bool:
        return ped.kinship(x, index) > 0

    cand_a = [x for x in order if x not in (index, mother, father) and not ped.people[x].deceased
              and ped.people[x].test is None and 0.005 < risks[x].p_carrier < 0.95]
    if not cand_a:
        return None
    w = np.array([3.0 if blood(x) else 1.0 for x in cand_a])
    target = cand_a[int(rng.choice(len(cand_a), p=w / w.sum()))]

    cons_set = {(c["female"], c["male"]) for c in cons}
    cand_b = []
    for f, m in couples:
        if ped.people[f].deceased or ped.people[m].deceased:
            continue
        cand_b.append((f, m))
    # The index's parents (risk 1 in 4 by definition) are asked about in about 1 family in 10.
    others_b = [c for c in cand_b if c != (mother, father)]
    ask_parents = (mother, father) in cand_b and (not others_b or rng.random() < 0.1)
    cand_b = [(mother, father)] if ask_parents else others_b  # type: ignore[list-item]
    risks_b = {}
    for c in cand_b:
        try:
            risks_b[c] = couple_risk(ped, rec.locus, c[0], c[1], rec.background_f).p_child_affected
        except (InconsistentEvidence, PedigreeTooComplex):
            continue
    cand_b = [c for c in cand_b if risks_b.get(c, 0.0) >= 1e-5]
    if not cand_b:
        return None
    w = np.array([3.0 if (c in cons_set and ftype != "no_loop") else 1.0 for c in cand_b])
    couple = cand_b[int(rng.choice(len(cand_b), p=w / w.sum()))]

    # names (unique per family in both scripts), narrator
    males = [x for x in order if ped.people[x].sex == Sex.MALE]
    females = [x for x in order if ped.people[x].sex == Sex.FEMALE]
    mn = [N.MALE[i] for i in rng.permutation(len(N.MALE))[: len(males)]]
    fn = [N.FEMALE[i] for i in rng.permutation(len(N.FEMALE))[: len(females)]]
    if len(mn) < len(males) or len(fn) < len(females):
        return None
    name = {x: mn[i] for i, x in enumerate(males)} | {x: fn[i] for i, x in enumerate(females)}
    rid = {x: name[x][0] for x in order}
    narrator = mother if rng.random() < 0.5 else father

    people: dict[str, PersonRec] = {}
    for x in order:
        p = ped.people[x]
        people[rid[x]] = PersonRec(
            id=rid[x], name_ar=name[x][1], sex=p.sex.value,
            mother=rid[p.mother] if p.mother else None, father=rid[p.father] if p.father else None,
            deceased=p.deceased, generation=k.generation[x],
            status="affected" if x == index else "unaffected",
            affected_with=label if x == index else None,
            test_detected=None if p.test is None else list(p.test.detected),
        )
    fam = Family(
        family_id=family_id, family_type=ftype, seed=seed, locus=locus_id, background_f=rec.background_f,
        people=people, unions=[(rid[a], rid[b]) for a, b in unions],
        couples=[(rid[f], rid[m]) for f, m in couples],
        consanguineous=[{**c, "female": rid[c["female"]], "male": rid[c["male"]]} for c in cons],
        index=rid[index], narrator=rid[narrator],  # type: ignore[index]
    )
    qa = Question("a", "carrier", person=rid[target])
    qb = Question("b", "child_affected", couple=(rid[couple[0]], rid[couple[1]]),
                  couple_has_children=couple in with_child)
    for q in (qa, qb):
        q.gold = gold_answer(fam, q)
        q.gold_f0 = gold_answer(fam, q, background_f=0.0)
    fam.questions = [qa, qb]
    return fam


@lru_cache(maxsize=1)
def generate_families() -> tuple[Family, ...]:
    """The 150 pre-registered families, in a fixed order (deterministic)."""
    fams: list[Family] = []
    for ftype in FAMILY_TYPES:
        got: list[Family] = []
        n_double = 0
        seed = SEED_BASE[ftype]
        attempts = 0
        while len(got) < N_PER_TYPE:
            attempts += 1
            if attempts > MAX_ATTEMPTS:
                raise RuntimeError(f"Could not generate {N_PER_TYPE} '{ftype}' families")
            i = len(got)
            locus = LOCI[i % len(LOCI)]
            fid = f"{ftype}-{i + 1:02d}"
            fam = build_family(ftype, seed, locus, fid)
            seed += 1
            if fam is None:
                continue
            if ftype == "multiple":
                has_double = any(c["relationship"] == "double_first_cousin" for c in fam.consanguineous)
                remaining = N_PER_TYPE - len(got)
                if not has_double and (MIN_DOUBLE - n_double) >= remaining:
                    continue
                n_double += has_double
            got.append(fam)
        fams.extend(got)
    return tuple(fams)


def family_map() -> dict[str, Family]:
    return {f.family_id: f for f in generate_families()}


def t5_families() -> list[Family]:
    """50 families for T5 (every third family, so the three family types are balanced)."""
    return [f for i, f in enumerate(generate_families()) if i % 3 == 0]


def build_items(track: str) -> list[Item]:
    fams = generate_families()
    out: list[Item] = []
    if track == "T1" or track == "T2":
        for f in fams:
            for q in ("a", "b"):
                for r in TRACK_REGISTERS[track]:
                    out.append(Item(f"{track}:{f.family_id}:{q}:{r}", track, f.family_id, f.family_type, f.locus, r, q))
    elif track == "T3":
        for f in fams:
            for r in TRACK_REGISTERS[track]:
                out.append(Item(f"T3:{f.family_id}:tree:{r}", track, f.family_id, f.family_type, f.locus, r, None))
    elif track == "T5":
        for i, f in enumerate(t5_families()):
            q = "a" if i % 2 == 0 else "b"
            out.append(Item(f"T5:{f.family_id}:{q}:en", track, f.family_id, f.family_type, f.locus, "en", q))
    else:
        raise ValueError(f"Unknown track {track} (T4 is computed from T1)")
    return out


def write_items(path: Path | None = None) -> Path:
    """Write gold families (with full gold pedigrees) to JSONL. Not for publication before judging."""
    path = path or BENCH_DIR / "data" / "families.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for f in generate_families():
            fh.write(json.dumps({**f.to_json(), "gold_tree": f.gold_tree()}, ensure_ascii=False) + "\n")
    return path


if __name__ == "__main__":
    import collections

    fams = generate_families()
    p = write_items()
    print(f"wrote {len(fams)} families to {p}")
    c = collections.Counter((f.family_type, f.locus) for f in fams)
    print(dict(c))
    print("double first cousin in 'multiple':",
          sum(any(x["relationship"] == "double_first_cousin" for x in f.consanguineous) for f in fams))
    print("people per family: min", min(len(f.people) for f in fams), "max", max(len(f.people) for f in fams))
