import copy
import json

import httpx
import numpy as np
import pytest

from silsila_bench import items as I
from silsila_bench import score as S
from silsila_bench.prompts import build_messages


@pytest.fixture(scope="module")
def fams():
    return I.family_map()


@pytest.mark.parametrize("p_hat,p,b", [
    (0.25, 0.25, "exact"), (0.26, 0.25, "exact"), (0.2625, 0.25, "exact"), (0.27, 0.25, "close"),
    (0.3125, 0.25, "close"), (0.32, 0.25, "other"), (0.5, 0.25, "off2x"), (0.125, 0.25, "off2x"),
    (0.13, 0.25, "other"), (0.0, 0.25, "off2x"), (None, 0.25, "no_number"), (1e-3, 1e-3 * 1.049, "exact"),
])
def test_bands(p_hat, p, b):
    assert S.band(p_hat, p) == b


def test_bootstrap_ratio_basic():
    groups = {f"f{i}": (1.0, 2.0) for i in range(30)}
    ci = S.bootstrap_ratio(groups)
    assert ci["value"] == 0.5 and ci["lo"] == pytest.approx(0.5) and ci["hi"] == pytest.approx(0.5)
    groups = {f"f{i}": (float(i % 2), 1.0) for i in range(40)}
    ci = S.bootstrap_ratio(groups)
    assert ci["value"] == 0.5 and 0.3 < ci["lo"] < 0.5 < ci["hi"] < 0.7
    assert S.bootstrap_ratio({})["value"] is None
    assert S.bootstrap_ratio({"a": (0.0, 0.0)})["value"] is None


def test_bootstrap_resamples_families_not_items():
    # one family with many identical items must not shrink the interval like independent items would
    rows = [{"family_id": "big", "x": 1.0} for _ in range(100)] + [{"family_id": f"f{i}", "x": 0.0} for i in range(9)]
    out = S.summarise(rows, {"m": (lambda r: r["x"], lambda r: 1.0)}, splits=())
    m = out["overall"]["m"]
    assert m["n_families"] == 10 and m["hi"] - m["lo"] > 0.3


def _rec(item, fam, content, **kw):
    return {"item_id": item.item_id, "family_id": item.family_id, "family_type": item.family_type,
            "register": item.register, "qid": item.qid, "locus": item.locus, "track": item.track,
            "messages": build_messages(item, fam), "final_content": content, "turns": [{"finish_reason": "stop", "usage": {}}],
            "error": None, "tool_args": kw.get("tool_args", []), "tool_results": kw.get("tool_results", [])}


def test_t1_and_t4_scoring(fams):
    items = [i for i in I.build_items("T1") if i.family_id in ("no_loop-01", "one_loop-01")]
    recs = {}
    for it in items:
        gold = fams[it.family_id].question(it.qid).gold
        # exact in en/msa/gulf, off by 2x in arabizi for family no_loop-01; no number for one item
        if it.item_id == "T1:one_loop-01:a:msa":
            text = "I cannot say."
        elif it.register == "arabizi" and it.family_id == "no_loop-01":
            text = f"Answer: {100 * gold / 3:.6f}%"
        else:
            text = f"Answer: {gold:.8f}"
        recs[it.item_id] = _rec(it, fams[it.family_id], text)
    rows = S.score_t1(recs, fams)
    assert len(rows) == 16
    by = {r["item_id"]: r["band"] for r in rows}
    assert by["T1:one_loop-01:a:msa"] == "no_number"
    assert by["T1:no_loop-01:a:arabizi"] == "off2x" and by["T1:no_loop-01:a:en"] == "exact"
    summ = S.summarise(rows, S.T1_METRICS)
    assert summ["overall"]["no_number"]["value"] == pytest.approx(1 / 16)
    assert summ["overall"]["exact"]["value"] == pytest.approx(13 / 15)
    assert summ["by_register"]["arabizi"]["off_2x"]["value"] == pytest.approx(0.5)
    t4 = S.score_t4(rows)
    assert len(t4) == 4
    d = {r["item_id"]: r for r in t4}
    assert d["T4:no_loop-01:a"]["complete"] and not d["T4:no_loop-01:a"]["same_band"]
    assert d["T4:no_loop-01:a"]["sd_log"] == pytest.approx(np.std([0, 0, 0, np.log(3)], ddof=1))
    assert not d["T4:one_loop-01:a"]["complete"]
    assert d["T4:one_loop-01:b"]["same_band"] and d["T4:one_loop-01:b"]["sd_log"] == pytest.approx(0, abs=1e-6)


def _q(f, qid):
    q = f.question(qid)
    return {"type": "carrier", "person": q.person} if q.type == "carrier" else {"type": "child_affected", "couple": list(q.couple)}


def test_t2_scoring(fams):
    f = fams["multiple-02"]
    it_ok, it_bad, it_none = [i for i in I.build_items("T2") if i.family_id == "multiple-02"][:3]
    good_args = {**f.gold_tree(), "question": _q(f, it_ok.qid)}
    bad_tree = copy.deepcopy(f.gold_tree())
    bad_tree["people"] = [p for p in bad_tree["people"] if p["mother"] is not None or p["id"] in
                          {x["mother"] for x in bad_tree["people"]} | {x["father"] for x in bad_tree["people"]}]
    bad_tree["people"][0]["status"] = "unknown"
    gold_a = f.question(it_ok.qid).gold
    recs = {
        it_ok.item_id: _rec(it_ok, f, f"Answer: {gold_a}", tool_args=[good_args], tool_results=[{"probability": gold_a}]),
        it_bad.item_id: _rec(it_bad, f, "Answer: 50%", tool_args=[{**bad_tree, "question": _q(f, it_bad.qid)}],
                             tool_results=[{"probability": 0.5}]),
        it_none.item_id: _rec(it_none, f, "no idea"),
    }
    rows = {r["item_id"]: r for r in S.score_t2(recs, fams)}
    assert rows[it_ok.item_id]["n_tree_identical"] == 1 and rows[it_ok.item_id]["band"] == "exact"
    assert rows[it_ok.item_id]["n_question_match"] == 1
    assert rows[it_bad.item_id]["n_tree_identical"] == 0
    assert rows[it_none.item_id]["n_tool_calls"] == 0 and rows[it_none.item_id]["band"] == "no_number"
    summ = S.summarise(list(rows.values()), S.T2_METRICS)["overall"]
    assert summ["tool_call_rate"]["value"] == pytest.approx(2 / 3)
    assert summ["tool_tree_identical"]["value"] == pytest.approx(0.5)


def test_t3_scoring(fams):
    f = fams["one_loop-05"]
    it_en, it_gulf = [i for i in I.build_items("T3") if i.family_id == "one_loop-05"]
    wrong = copy.deepcopy(f.gold_tree())
    # forget that the cousin couple's parents are siblings: remove one grandparent link
    p = next(x for x in wrong["people"] if x["mother"] and any(x["id"] in (c["female"], c["male"]) for c in f.consanguineous))
    p["mother"] = p["father"] = None
    recs = {it_en.item_id: _rec(it_en, f, "", tool_args=[f.gold_tree()]),
            it_gulf.item_id: _rec(it_gulf, f, "", tool_args=[wrong])}
    rows = {r["item_id"]: r for r in S.score_t3(recs, fams)}
    r = rows[it_en.item_id]
    assert r["identical"] and r["engine_correct"] == 2 and r["edges_tp"] == r["edges_gold"] == r["edges_pred"]
    w = rows[it_gulf.item_id]
    assert not w["structure_identical"] and w["edges_tp"] < w["edges_gold"] and w["edges_pred"] == w["edges_tp"]
    summ = S.summarise(list(rows.values()), S.T3_METRICS)["overall"]
    assert summ["edge_precision"]["value"] == 1.0 and summ["edge_recall"]["value"] < 1.0
    assert summ["exact_tree"]["value"] == 0.5


def test_t3_missing_tree(fams):
    f = fams["no_loop-02"]
    it = [i for i in I.build_items("T3") if i.family_id == "no_loop-02"][0]
    rows = S.score_t3({it.item_id: _rec(it, f, "Here is the tree: ...")}, fams)
    assert not rows[0]["tree_submitted"] and rows[0]["engine_correct"] == 0


def test_extract_pmids_and_relatedness():
    text = ("Carrier rates in the UAE (PMID: 23647352). Consanguinity was 50.5% (PMID 9881148). "
            "See https://pubmed.ncbi.nlm.nih.gov/99999999/ and PMID: 23647352 again.")
    got = [p for p, _ in S.extract_pmids(text)]
    assert got == ["23647352", "9881148", "99999999"]
    ok, hits = S.related("Hemoglobinopathy carrier prevalence in the United Arab Emirates", "carrier rates", "HBB")
    assert ok and "hemoglobinopathy" in hits
    ok, _ = S.related("A randomized trial of statins in heart failure", "carrier rates", "HBB")
    assert not ok


def test_pubmed_lookup_with_mock_and_cache(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        ids = req.url.params["id"].split(",")
        assert req.url.params["db"] == "pubmed" and "email" not in req.url.params
        res = {"uids": ids}
        for i in ids:
            res[i] = ({"uid": i, "title": "Hemoglobinopathy carrier prevalence in the United Arab Emirates.",
                       "pubdate": "2013", "source": "Hemoglobin"} if i == "23647352" else {"uid": i, "error": "cannot get document summary"})
        return httpx.Response(200, json={"result": res})

    pm = S.PubMed(cache_path=tmp_path / "c.json", client=httpx.Client(transport=httpx.MockTransport(handler)),
                  api_key="", min_interval=0.0)
    out = pm.lookup(["23647352", "99999999"])
    assert out["23647352"]["exists"] and not out["99999999"]["exists"]
    pm2 = S.PubMed(cache_path=tmp_path / "c.json", client=httpx.Client(transport=httpx.MockTransport(handler)),
                   api_key="", min_interval=0.0)
    pm2.lookup(["23647352"])
    assert len(calls) == 1  # second lookup served from the cache file


def test_pubmed_retries_on_server_error(tmp_path, monkeypatch):
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    n = {"k": 0}

    def handler(req):
        n["k"] += 1
        if n["k"] < 3:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"result": {"1234": {"uid": "1234", "title": "Spinal muscular atrophy carriers"}}})

    pm = S.PubMed(cache_path=tmp_path / "c.json", client=httpx.Client(transport=httpx.MockTransport(handler)),
                  api_key="", min_interval=0.0)
    assert pm.lookup(["1234"])["1234"]["exists"] and n["k"] == 3


def test_t5_scoring(tmp_path, fams):
    it = I.build_items("T5")[0]
    f = fams[it.family_id]
    gold = f.question(it.qid).gold
    text = (f"Using carrier frequencies (PMID: 23647352) and a made-up study (PMID: 99999999), and an unrelated "
            f"paper (PMID: 11111111). Answer: {gold}")

    def handler(req):
        res = {"23647352": {"uid": "23647352", "title": "Hemoglobinopathy carrier prevalence in the United Arab Emirates"},
               "11111111": {"uid": "11111111", "title": "Statins and cholesterol in older adults"},
               "99999999": {"uid": "99999999", "error": "cannot get document summary"}}
        return httpx.Response(200, json={"result": res})

    pm = S.PubMed(cache_path=tmp_path / "c.json", client=httpx.Client(transport=httpx.MockTransport(handler)),
                  api_key="", min_interval=0.0)
    rows = S.score_t5({it.item_id: _rec(it, f, text)}, fams, pm)
    r = rows[0]
    assert r["n_refs"] == 3 and r["n_exist"] == 2 and r["band"] == "exact"
    flagged = {x["pmid"] for x in r["refs"] if x["flag_for_review"]}
    assert "99999999" in flagged and "11111111" in flagged
    summ = S.summarise(rows, S.T5_METRICS, splits=())["overall"]
    assert summ["pmid_not_found"]["value"] == pytest.approx(1 / 3)


def test_t3_tree_written_as_text_is_not_a_call_but_logged(fams):
    f = fams["no_loop-03"]
    it = [i for i in I.build_items("T3") if i.family_id == "no_loop-03"][0]
    text = "Here is the tree:\n```json\n" + json.dumps(f.gold_tree()) + "\n```"
    row = S.score_t3({it.item_id: _rec(it, f, text)}, fams)[0]
    assert not row["tree_submitted"] and row["engine_correct"] == 0
    assert row["tree_in_text"] and row["text_tree_identical"] and row["text_tree_edge_recall"] == 1.0
    summ = S.summarise([row], S.T3_METRICS, splits=())["overall"]
    assert summ["tree_in_text_only"]["value"] == 1.0 and summ["exact_tree"]["value"] == 0.0
