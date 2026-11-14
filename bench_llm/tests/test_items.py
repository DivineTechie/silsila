import collections
import json

import pytest
from silsila import params
from silsila.engine import Pedigree, Person, Phenotype, Sex, TestResult, couple_risk, person_risks

from silsila_bench import items as I


@pytest.fixture(scope="module")
def fams():
    return I.generate_families()


def test_counts_types_and_loci(fams):
    assert len(fams) == 150
    c = collections.Counter(f.family_type for f in fams)
    assert c == {"no_loop": 50, "one_loop": 50, "multiple": 50}
    for t in I.FAMILY_TYPES:
        loci = collections.Counter(f.locus for f in fams if f.family_type == t)
        assert set(loci) == set(I.LOCI) and max(loci.values()) - min(loci.values()) <= 1
    assert len({f.family_id for f in fams}) == 150


def test_family_type_definitions(fams):
    n_double = 0
    for f in fams:
        cons = f.consanguineous
        ped = f.pedigree()
        # recompute from the gold pedigree, not from the stored annotation
        k = [ped.kinship(a, b) for a, b in ped.couples() if ped.kinship(a, b) > 0]
        assert len(k) == len(cons)
        if f.family_type == "no_loop":
            assert not cons
        elif f.family_type == "one_loop":
            assert len(cons) == 1 and cons[0]["relationship"] == "first_cousin" and cons[0]["kinship"] == 1 / 16
        else:
            assert len(cons) >= 2
            n_double += any(c["relationship"] == "double_first_cousin" and c["kinship"] == 1 / 8 for c in cons)
    assert n_double >= I.MIN_DOUBLE


def test_one_affected_index_and_some_tests(fams):
    for f in fams:
        affected = [p for p in f.people.values() if p.status == "affected"]
        assert [p.id for p in affected] == [f.index]
        assert affected[0].affected_with in params.load()[f.locus].locus.affected_phenotypes
        assert any(p.test_detected is not None for p in f.people.values())
        assert f.narrator in (f.people[f.index].mother, f.people[f.index].father)
        assert I.MIN_PEOPLE <= len(f.people) <= I.MAX_PEOPLE
        # unique names in both scripts
        assert len({p.id for p in f.people.values()}) == len(f.people)
        assert len({p.name_ar for p in f.people.values()}) == len(f.people)


def test_questions_are_well_formed(fams):
    for f in fams:
        qa, qb = f.question("a"), f.question("b")
        p = f.people[qa.person]
        assert p.test_detected is None and not p.deceased and qa.person != f.index
        assert 0.005 < qa.gold < 0.95
        fem, mal = qb.couple
        assert f.people[fem].sex == "female" and f.people[mal].sex == "male"
        assert not f.people[fem].deceased and not f.people[mal].deceased
        assert qb.gold >= 1e-5
        # background inbreeding changes no answer by 5% or more (it is stated in the prompt anyway)
        for q in (qa, qb):
            assert abs(q.gold - q.gold_f0) / q.gold < 0.05


def test_generator_is_deterministic(fams):
    f0 = fams[0]
    again = I.build_family(f0.family_type, f0.seed, f0.locus, f0.family_id)
    assert json.dumps(again.to_json(), sort_keys=True) == json.dumps(f0.to_json(), sort_keys=True)
    f1 = fams[120]
    again = I.build_family(f1.family_type, f1.seed, f1.locus, f1.family_id)
    assert json.dumps(again.to_json(), sort_keys=True) == json.dumps(f1.to_json(), sort_keys=True)


def test_json_roundtrip(fams):
    f = fams[77]
    g = I.Family.from_json(json.loads(json.dumps(f.to_json())))
    assert g.to_json() == f.to_json()
    assert I.gold_answer(g, g.question("b")) == pytest.approx(f.question("b").gold, rel=1e-12)


def test_gold_equals_engine_spot_check(fams):
    """Recompute gold answers directly with the engine for a spread of families."""
    for f in fams[::10]:
        rec = params.load()[f.locus]
        ped = f.pedigree()
        qa, qb = f.question("a"), f.question("b")
        assert person_risks(ped, rec.locus, rec.background_f)[qa.person].p_carrier == pytest.approx(qa.gold, rel=1e-12)
        assert couple_risk(ped, rec.locus, *qb.couple, rec.background_f).p_child_affected == pytest.approx(qb.gold, rel=1e-12)


def test_gold_textbook_values():
    """Hand-built nuclear family through the bench's gold path: unaffected sibling of an affected child
    is a carrier with probability 2/3; the parents' next child is affected with probability 1/4."""
    people = {
        "Mariam": I.PersonRec("Mariam", "مريم", "female", None, None, False, 0, "unaffected", None, None),
        "Khalid": I.PersonRec("Khalid", "خالد", "male", None, None, False, 0, "unaffected", None, None),
        "Saeed": I.PersonRec("Saeed", "سعيد", "male", "Mariam", "Khalid", False, 1, "affected", "spinal muscular atrophy", None),
        "Noura": I.PersonRec("Noura", "نورة", "female", "Mariam", "Khalid", False, 1, "unaffected", None, None),
    }
    fam = I.Family("t", "no_loop", 0, "SMN1", 0.0222, people, [], [("Mariam", "Khalid")], [], "Saeed", "Mariam")
    assert I.gold_answer(fam, I.Question("a", "carrier", person="Noura")) == pytest.approx(2 / 3, abs=1e-9)
    assert I.gold_answer(fam, I.Question("b", "child_affected", couple=("Mariam", "Khalid"))) == pytest.approx(0.25, abs=1e-9)


def test_item_counts_match_preregistration():
    assert len(I.build_items("T1")) == 1200
    assert len(I.build_items("T2")) == 600
    assert len(I.build_items("T3")) == 300
    t5 = I.build_items("T5")
    assert len(t5) == 50 and {i.register for i in t5} == {"en"}
    assert collections.Counter(i.family_type for i in t5) == {"no_loop": 17, "one_loop": 17, "multiple": 16}
    ids = [i.item_id for t in ("T1", "T2", "T3", "T5") for i in I.build_items(t)]
    assert len(ids) == len(set(ids))
