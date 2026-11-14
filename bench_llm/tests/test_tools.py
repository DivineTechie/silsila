import copy
import json

import pytest

from silsila_bench import items as I
from silsila_bench.tools import (
    COMPUTE_TOOL, IncrementalTree, SUBMIT_TREE_TOOL, compare_trees, compute_family_risk, engine_answer_on_tree,
    normalise_affected, normalise_variants, tree_from_args,
)


@pytest.fixture(scope="module")
def fams():
    return I.generate_families()


def _question(f, qid):
    q = f.question(qid)
    return {"type": "carrier", "person": q.person} if q.type == "carrier" else {"type": "child_affected", "couple": list(q.couple)}


def test_tool_on_gold_tree_reproduces_gold_for_every_family(fams):
    for f in fams:
        for qid in ("a", "b"):
            out = compute_family_risk({**f.gold_tree(), "question": _question(f, qid)})
            assert "error" not in out, (f.family_id, out)
            assert out["probability"] == pytest.approx(f.question(qid).gold, rel=1e-9)


def test_tool_accepts_json_string_and_arabic_names(fams):
    f = fams[3]
    args = {**f.gold_tree(), "question": _question(f, "a")}
    assert compute_family_risk(json.dumps(args))["probability"] == pytest.approx(f.question("a").gold, rel=1e-9)
    # Arabic-script ids (as a model may use for the Gulf Arabic story), resolved via the family's name index
    ar = {p.id: p.name_ar for p in f.people.values()}
    tree = copy.deepcopy(f.gold_tree())
    for p in tree["people"]:
        p["id"] = ar[p["id"]]
        p["mother"] = ar.get(p["mother"]) if p["mother"] else None
        p["father"] = ar.get(p["father"]) if p["father"] else None
    tree["unions"] = [{"a": ar[u["a"]], "b": ar[u["b"]]} for u in tree["unions"]]
    gold = tree_from_args(f.gold_tree(), f.name_index())
    pred = tree_from_args(tree, f.name_index())
    assert compare_trees(pred, gold)["identical"]
    q = _question(f, "a")
    q["person"] = ar[q["person"]]
    assert compute_family_risk({**tree, "question": q})["probability"] == pytest.approx(f.question("a").gold, rel=1e-9)


@pytest.mark.parametrize("mutate,needle", [
    (lambda a: a.update(gene="BRCA1"), "gene"),
    (lambda a: a["people"].pop(0), "not in the family tree"),
    (lambda a: a.update(question={"type": "carrier", "person": "Nobody"}), "not in the family tree"),
    (lambda a: a.update(question={"type": "odds"}), "question.type"),
    (lambda a: a["people"][-1].update(sex="other"), "sex"),
])
def test_tool_errors_are_returned_not_raised(fams, mutate, needle):
    f = next(x for x in fams if x.people[next(iter(x.people))].mother is None)
    args = copy.deepcopy({**f.gold_tree(), "question": _question(f, "a")})
    mutate(args)
    out = compute_family_risk(args)
    assert "error" in out and needle.split()[0] in out["error"]


def test_tool_rejects_one_parent_only(fams):
    f = fams[0]
    args = copy.deepcopy({**f.gold_tree(), "question": _question(f, "a")})
    child = next(p for p in args["people"] if p["mother"])
    child["father"] = None
    assert "both parents" in compute_family_risk(args)["error"]


def test_tool_schema_shape():
    p = COMPUTE_TOOL["function"]["parameters"]
    assert set(p["required"]) == {"gene", "people", "question"}
    assert set(p["properties"]["people"]["items"]["properties"]) >= {"id", "sex", "mother", "father", "status",
                                                                    "affected_with", "test_detected"}
    assert SUBMIT_TREE_TOOL["function"]["name"] == "submit_family_tree"


def test_normalisers():
    assert normalise_affected("HBB", "Sickle cell disease (HbSS)") == "sickle cell disease"
    assert normalise_affected("HBB", "sickle beta thalassemia") == "sickle beta-thalassaemia"
    assert normalise_affected("HBB", "beta thalassaemia major") == "beta-thalassaemia major or intermedia"
    assert normalise_affected("SMN1", "SMA") == "spinal muscular atrophy"
    assert normalise_variants("HBB", ["sickle"]) == ("S",)
    assert normalise_variants("SMN1", "[\"del\"]") == ("del",)
    assert normalise_variants("CYP21A2", []) == ()
    with pytest.raises(ValueError):
        normalise_variants("HBB", ["X"])


def test_compare_trees_detects_changes(fams):
    f = fams[60]
    res = f.name_index()
    gold = tree_from_args(f.gold_tree(), res)
    assert compare_trees(tree_from_args(f.gold_tree(), res), gold)["identical"]
    # drop a parent link -> structure differs, edge recall < 1
    t = copy.deepcopy(f.gold_tree())
    child = next(p for p in t["people"] if p["mother"])
    child["mother"] = child["father"] = None
    cmp = compare_trees(tree_from_args(t, res), gold)
    assert not cmp["structure_identical"] and cmp["edges_tp"] == cmp["edges_gold"] - 2
    # status change only -> structure identical, tree not identical
    t = copy.deepcopy(f.gold_tree())
    t["people"][0]["status"] = "unknown"
    cmp = compare_trees(tree_from_args(t, res), gold)
    assert cmp["structure_identical"] and not cmp["identical"]


def test_engine_answer_on_model_tree(fams):
    f = fams[100]
    t = tree_from_args(f.gold_tree(), f.name_index())
    assert engine_answer_on_tree(t, _question(f, "b"), f.name_index()) == pytest.approx(f.question("b").gold, rel=1e-12)


def test_incremental_tree_builds_same_tree(fams):
    f = fams[10]
    st = IncrementalTree()
    for p in f.people.values():
        assert st.call("add_person", {"id": p.id, "sex": p.sex}) == {"ok": True}
    for p in f.people.values():
        if p.mother:
            assert st.call("set_parents", json.dumps({"child": p.id, "mother": p.mother, "father": p.father}))["ok"]
        st.call("set_status", {"id": p.id, "status": p.status, "affected_with": p.affected_with})
        if p.test_detected is not None:
            st.call("set_test_result", {"id": p.id, "detected": p.test_detected})
    for a, b in f.unions:
        st.call("add_marriage", {"a": a, "b": b})
    assert "error" in st.call("set_parents", {"child": "Nobody", "mother": "x", "father": "y"})
    st.call("finish_family_tree", {"gene": f.locus})
    assert st.finished
    res = f.name_index()
    assert compare_trees(tree_from_args(st.as_args(), res), tree_from_args(f.gold_tree(), res))["identical"]
