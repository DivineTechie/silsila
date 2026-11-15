"""Family Twin: the fictional clan, the hidden truth stays hidden, and live exact recomputation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from silsila import twin
from silsila.api import app as app_mod

client = TestClient(app_mod.app)


def test_clan_is_served_without_the_hidden_truth():
    t = client.get("/api/twin").json()
    assert "truth" not in t and len(t["people"]) >= 40 and len(t["consanguineous"]) >= 3
    index = next(p for p in t["people"] if p["id"] == t["index"])
    assert index["status"] == "affected"
    # only the index's parents have test results to start with
    assert {p["id"] for p in t["people"] if p["test"]} == set(t["parents"])


def test_what_if_is_exact_and_responds_to_evidence():
    base = client.post("/api/twin/what-if", json={"results": {}}).json()
    assert base["status"] == "ok" and base["people_count"] == len(twin.public()["people"])
    t = twin.public()
    for par in t["parents"]:  # parents of an affected child are carriers (they were tested positive)
        assert base["p_carrier"][par] > 0.99
    target = max((pid for pid, v in base["p_carrier"].items() if v < 0.9), key=lambda pid: base["p_carrier"][pid])
    after = client.post("/api/twin/what-if", json={"results": {target: "clear"}}).json()
    assert after["p_carrier"][target] < base["p_carrier"][target]
    assert after["p_carrier"] != base["p_carrier"]


def test_what_if_rejects_unknown_people_and_bad_values():
    assert client.post("/api/twin/what-if", json={"results": {"nobody": "carrier"}}).status_code == 422
    assert client.post("/api/twin/what-if", json={"results": {"k1": "maybe"}}).status_code == 422


def test_a_result_already_on_file_cannot_be_re_recorded():
    t = twin.public()
    assert twin.on_file() == {t["index"], *t["parents"]}
    for pid in (t["index"], *t["parents"]):  # the affected newborn and the tested parents
        for value in ("carrier", "clear"):
            r = client.post("/api/twin/what-if", json={"results": {pid: value}})
            assert r.status_code == 422 and "already on file" in r.json()["detail"]
    # and neither strategy in the race ever tests them
    for strat in ("ranked", "family_order"):
        assert not {e["person"] for e in t["race"][strat]} & twin.on_file()


def test_race_uses_the_same_hidden_results_for_both_strategies():
    t = twin.load()
    for strat in ("ranked", "family_order"):
        for e in t["race"][strat]:
            assert not e["carrier"] or t["truth"][e["person"]]  # a positive test is always a true carrier
    found_r = {tuple(c) for e in t["race"]["ranked"] for c in e["couples_found"]}
    found_f = {tuple(c) for e in t["race"]["family_order"] for c in e["couples_found"]}
    true = {tuple(c) for c in t["race"]["true_atrisk_couples"]}
    assert found_r <= true and found_f <= true
