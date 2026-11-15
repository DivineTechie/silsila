"""Importing an index result from a FHIR R4B record: read completely or refused with a reason, never silently."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE = json.loads((Path(__file__).resolve().parents[2] / "data" / "demo" / "fhir" / "newborn_cah_index_result.json").read_text())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SILSILA_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("SILSILA_DEMO_FAMILY_PASSWORD", "test-family-pw")
    monkeypatch.setenv("SILSILA_DEMO_COUNSELLOR_PASSWORD", "test-counsellor-pw")
    monkeypatch.setenv("SILSILA_DEMO", "1")
    from silsila.api import app as app_mod, seed, store as store_mod
    importlib.reload(app_mod)
    s = store_mod.Store()
    seed.seed(s)
    app_mod._store = s
    return TestClient(app_mod.app)


def as_(client, persona):
    return {"Authorization": f"Bearer {client.post('/api/demo/login', json={'persona': persona}).json()['token']}"}


def sample():
    return copy.deepcopy(SAMPLE)


def res(bundle, kind):
    return next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind)


def comp(obs, loinc):
    return next(c for c in obs["component"] if c["code"]["coding"][0]["code"] == loinc)


def test_sample_is_previewed_then_becomes_a_case_that_waits_for_the_family(client):
    cou, fam = as_(client, "counsellor"), as_(client, "mariam")
    assert client.get("/api/fhir/sample", headers=cou).json() == SAMPLE
    before = len(client.get("/api/cases", headers=cou).json())

    preview = client.post("/api/fhir/import", headers=cou, json={"bundle": sample(), "index_source": "newborn_screen"}).json()
    assert preview["created"] is False and len(client.get("/api/cases", headers=cou).json()) == before  # dry run stores nothing
    d = preview["draft"]
    assert d["locus_id"] == "CYP21A2" and d["index"] == {"sex": "male", "status": "affected",
                                                         "affected_with": "classic congenital adrenal hyperplasia",
                                                         "test": {"detected": ["c", "c"]}}
    assert d["not_stored"] == ["birthDate", "identifier", "name"] and d["warnings"] == []

    r = client.post("/api/fhir/import", headers=cou, json={"bundle": sample(), "index_source": "newborn_screen",
                                                           "family_user_id": "user_family", "dry_run": False}).json()
    assert r["created"] is True
    from silsila.api import app as app_mod
    stored = app_mod.store().get("case", r["case_id"])
    blob = json.dumps(stored, ensure_ascii=False)
    for personal in ("Zayed", "FICTIONAL-MRN-0001", "2026-10-28"):  # nothing identifying is kept
        assert personal not in blob
    assert stored["source_record"]["sha256"] == d["source"]["sha256"] and stored["index_source"] == "newborn_screen"

    # consent-led: nothing is calculated until the family gives permission
    case = client.get(f"/api/cases/{r['case_id']}", headers=fam).json()
    assert case["report"]["status"] == "awaiting_consent"
    client.post(f"/api/cases/{r['case_id']}/consents", headers=fam, json={"scope": "compute", "granted": True})
    rep = client.get(f"/api/cases/{r['case_id']}", headers=fam).json()["report"]
    assert rep["status"] == "ok"
    assert rep["people"]["mother"]["computed"]["p_any_variant"] == pytest.approx(1.0)  # parents of an affected child
    assert rep["people"]["father"]["computed"]["p_any_variant"] == pytest.approx(1.0)

    events = client.get("/api/audit", headers=cou).json()["events"]
    done = next(e for e in events if e["action"] == "fhir.import" and e["outcome"] == "success")
    assert done["case_id"] == r["case_id"] and done["detail"]["sha256"] == d["source"]["sha256"]
    assert any(e["action"] == "fhir.import_preview" for e in events)


@pytest.mark.parametrize("case_id,expect", [
    ("case_cah_demo", {"sex": "male", "status": "affected", "affected_with": "classic congenital adrenal hyperplasia", "test": None}),
    ("case_hbb_demo", {"sex": "female", "status": "unknown", "affected_with": None, "test": {"detected": ["B"]}}),
])
def test_export_then_import_gives_back_the_index_result(client, case_id, expect):
    cou = as_(client, "counsellor")
    bundle = client.get(f"/api/fhir/cases/{case_id}", headers=cou).json()
    r = client.post("/api/fhir/import", headers=cou, json={"bundle": bundle})
    assert r.status_code == 200, r.text
    d = r.json()["draft"]
    from silsila.api import app as app_mod
    assert d["locus_id"] == app_mod.store().get("case", case_id)["locus_id"] and d["index"] == expect
    assert d["not_stored"] == []  # the export is pseudonymous, so there is nothing to drop


def test_sickle_variant_is_told_from_other_hbb_variants(client):
    cou = as_(client, "counsellor")
    b = sample()
    b["entry"] = [e for e in b["entry"] if e["resource"]["resourceType"] != "Condition"]
    obs = res(b, "Observation")
    comp(obs, "48018-6")["valueCodeableConcept"]["coding"][0].update(code="HGNC:4827", display="HBB")
    comp(obs, "53034-5")["valueCodeableConcept"]["coding"][0].update(code="LA6706-1", display="Heterozygous")
    plain = client.post("/api/fhir/import", headers=cou, json={"bundle": b}).json()["draft"]
    assert plain["index"]["test"] == {"detected": ["B"]} and plain["index_source"] == "carrier_result"
    obs["component"].append({"code": {"coding": [{"system": "http://loinc.org", "code": "48004-6"}]}, "valueString": "NM_000518.5:c.20A>T"})
    sickle = client.post("/api/fhir/import", headers=cou, json={"bundle": b}).json()["draft"]
    assert sickle["index"]["test"] == {"detected": ["S"]}


def _no_patient(b):
    b["entry"] = [e for e in b["entry"] if e["resource"]["resourceType"] != "Patient"]


def _two_patients(b):
    extra = copy.deepcopy(res(b, "Patient"))
    extra["id"] = "someone-else"
    b["entry"].append({"fullUrl": "urn:uuid:8f1c2c1e-0001-4a6b-9c11-000000000009", "resource": extra})


def _drop_condition(b):
    b["entry"] = [e for e in b["entry"] if e["resource"]["resourceType"] != "Condition"]


def _unsupported_gene(b):
    comp(res(b, "Observation"), "48018-6")["valueCodeableConcept"]["coding"][0].update(code="HGNC:1884", display="CFTR")


def _uncertain(b):
    comp(res(b, "Observation"), "53037-8")["valueCodeableConcept"]["coding"][0].update(code="LA26333-7", display="Uncertain significance")


def _absent_no_diagnosis(b):
    _drop_condition(b)
    res(b, "Observation")["valueCodeableConcept"]["coding"][0].update(code="LA9634-2", display="Absent")


def _no_allelic_state(b):
    _drop_condition(b)
    obs = res(b, "Observation")
    obs["component"] = [c for c in obs["component"] if c["code"]["coding"][0]["code"] != "53034-5"]


def _diagnosis_does_not_fit(b):
    comp(res(b, "Observation"), "53034-5")["valueCodeableConcept"]["coding"][0].update(code="LA6706-1", display="Heterozygous")


def _second_gene(b):
    extra = copy.deepcopy(res(b, "Observation"))
    extra["id"] = "second-gene"
    comp(extra, "48018-6")["valueCodeableConcept"]["coding"][0].update(code="HGNC:4827", display="HBB")
    b["entry"].append({"fullUrl": "urn:uuid:8f1c2c1e-0001-4a6b-9c11-000000000008", "resource": extra})


def _present_and_absent(b):
    extra = copy.deepcopy(res(b, "Observation"))
    extra["id"] = "contradiction"
    extra["valueCodeableConcept"]["coding"][0].update(code="LA9634-2", display="Absent")
    b["entry"].append({"fullUrl": "urn:uuid:8f1c2c1e-0001-4a6b-9c11-000000000007", "resource": extra})


MALFORMED = [
    ("not a bundle", lambda b: (b.clear(), b.update(resourceType="Patient", id="x")), "not a FHIR Bundle"),
    ("invalid FHIR", lambda b: res(b, "Observation").pop("code"), "Not a valid FHIR R4B Bundle"),
    ("wrong type for a field", lambda b: res(b, "Patient").update(birthDate="last Tuesday"), "Not a valid FHIR R4B Bundle"),
    ("empty bundle", lambda b: b.update(entry=[]), "exactly one Patient"),
    ("no patient", _no_patient, "exactly one Patient"),
    ("two patients", _two_patients, "exactly one Patient"),
    ("sex not recorded", lambda b: res(b, "Patient").update(gender="unknown"), "sex is not recorded"),
    ("result about someone else", lambda b: res(b, "Observation")["subject"].update(reference="Patient/other"), "not about the Patient"),
    ("diagnosis about someone else", lambda b: res(b, "Condition")["subject"].update(reference="Patient/other"), "not about the Patient"),
    ("preliminary result", lambda b: res(b, "Observation").update(status="preliminary"), "Only a final result"),
    ("entered in error", lambda b: res(b, "Observation").update(status="entered-in-error"), "Only a final result"),
    ("gene not stated", lambda b: res(b, "Observation")["component"].pop(0), "which gene was studied"),
    ("gene Silsila does not calculate", _unsupported_gene, "does not calculate chances for the gene HGNC:1884"),
    ("neither present nor absent", lambda b: res(b, "Observation").pop("valueCodeableConcept"), "Present (LA9633-4) or Absent"),
    ("variant of uncertain significance", _uncertain, "not a reason to contact relatives"),
    ("no variant and no diagnosis", _absent_no_diagnosis, "no result to start a cascade from"),
    ("carrier or affected cannot be told", _no_allelic_state, "one copy or two"),
    ("diagnosis does not fit the genotype", _diagnosis_does_not_fit, "does not fit the genetic result"),
    ("two genes at once", _second_gene, "more than one gene"),
    ("present and absent", _present_and_absent, "both present and absent"),
    ("no genetic result and no diagnosis", lambda b: b.update(entry=[e for e in b["entry"] if e["resource"]["resourceType"] == "Patient"]),
     "no genetic variant assessment"),
    ("too many entries", lambda b: b.update(entry=b["entry"] * 80), "too large"),
]


@pytest.mark.parametrize("name,mutate,expected", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_a_record_that_cannot_be_read_safely_is_refused_with_the_reason(client, name, mutate, expected):
    cou = as_(client, "counsellor")
    before = len(client.get("/api/cases", headers=cou).json())
    b = sample()
    mutate(b)
    for dry_run in (True, False):
        r = client.post("/api/fhir/import", headers=cou, json={"bundle": b, "family_user_id": "user_family", "dry_run": dry_run})
        assert r.status_code == 422, (name, r.status_code, r.text)
        assert expected in r.json()["detail"], (name, r.json()["detail"])
    assert len(client.get("/api/cases", headers=cou).json()) == before  # nothing was created
    refused = [e for e in client.get("/api/audit", headers=cou).json()["events"] if e["action"] == "fhir.import" and e["outcome"] == "refused"]
    assert len(refused) == 2 and expected in refused[0]["detail"]["reason"]  # and each refusal is on the audit chain


def test_warnings_are_shown_instead_of_guessing(client):
    cou = as_(client, "counsellor")
    b = sample()
    obs = res(b, "Observation")
    obs["component"] = [c for c in obs["component"] if c["code"]["coding"][0]["code"] != "53037-8"]
    res(b, "Condition")["verificationStatus"]["coding"][0]["code"] = "provisional"
    d = client.post("/api/fhir/import", headers=cou, json={"bundle": b}).json()["draft"]
    assert d["index"]["status"] == "unknown" and d["index"]["test"] == {"detected": ["c", "c"]}  # a provisional diagnosis is not used
    text = " ".join(d["warnings"])
    assert "no clinical significance" in text and "not confirmed" in text and "no diagnosis is recorded" in text
    # a diagnosis with no verification status at all is treated the same way, and a non-genetic result is named
    b = sample()
    res(b, "Condition").pop("verificationStatus")
    res(b, "Observation")["code"]["coding"][0]["code"] = "1668-3"
    r = client.post("/api/fhir/import", headers=cou, json={"bundle": b})
    assert r.status_code == 422 and "no genetic variant assessment" in r.json()["detail"]
    b = sample()
    res(b, "Condition").pop("verificationStatus")
    d = client.post("/api/fhir/import", headers=cou, json={"bundle": b}).json()["draft"]
    assert d["index"]["status"] == "unknown" and "no verification status" in " ".join(d["warnings"])


def test_only_a_counsellor_can_import_and_a_family_account_must_be_chosen(client):
    cou, fam = as_(client, "counsellor"), as_(client, "mariam")
    assert client.post("/api/fhir/import", headers=fam, json={"bundle": sample()}).status_code == 403
    assert client.post("/api/fhir/import", json={"bundle": sample()}).status_code == 401
    assert client.get("/api/fhir/sample", headers=fam).status_code == 403
    for owner in (None, "user_counsellor", "nobody"):
        r = client.post("/api/fhir/import", headers=cou, json={"bundle": sample(), "family_user_id": owner, "dry_run": False})
        assert r.status_code == 422 and "family account" in r.json()["detail"]
    assert [f["id"] for f in client.get("/api/fhir/families", headers=cou).json()] == ["user_family", "user_family2"]


def _paths(node, prefix=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield prefix + (k,)
            yield from _paths(v, prefix + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield prefix + (i,)
            yield from _paths(v, prefix + (i,))


def test_deleting_any_one_field_of_the_sample_never_fails_silently(client):
    """Every single-field deletion of the sample record is either read (200) or refused with a reason (422).
    Never a crash, never an empty reason, and a deletion never turns into a different condition."""
    cou = as_(client, "counsellor")
    outcomes = {200: 0, 422: 0}
    for path in list(_paths(SAMPLE)):
        b = sample()
        node = b
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]
        r = client.post("/api/fhir/import", headers=cou, json={"bundle": b})
        assert r.status_code in (200, 422), (path, r.status_code, r.text[:200])
        outcomes[r.status_code] += 1
        if r.status_code == 422:
            assert len(r.json()["detail"]) > 20, path
        else:
            d = r.json()["draft"]
            assert d["locus_id"] == "CYP21A2" and d["index"]["sex"] == "male", path
            assert d["index"]["status"] in ("affected", "unknown"), path
    assert outcomes[200] + outcomes[422] == len(list(_paths(SAMPLE))) and outcomes[422] > 20
    print(f"single-field deletions: {outcomes}")
