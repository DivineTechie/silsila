"""Export a case as a FHIR R4B Bundle (validated with fhir.resources).

Mapping:
  index person          -> Patient (pseudonymous: no name, no identifiers)
  index person affected -> Condition (confirmed; ICD-10 code where one maps)
  other family members  -> FamilyMemberHistory (status, condition if affected)
  recorded test results -> Observation, LOINC 69548-6 "Genetic variant assessment"
                           with component 48018-6 "Gene studied [ID]" (HGNC code),
                           53034-5 "Allelic state" and 53037-8 clinical significance;
                           one Observation per variant class found
  engine probabilities  -> RiskAssessment (method: Silsila engine, basis: inputs)
  permissions           -> Consent
  invitations           -> Task (status mapped from the invitation lifecycle)
  audit log entries     -> AuditEvent
Codes were checked against tx.fhir.org (LOINC, ICD-10) and rest.genenames.org (HGNC).
`fhir_import` reads the index person's part of this bundle back: export then import gives the same result.
"""

from __future__ import annotations

import re
from typing import Any

from collections import Counter

from fhir.resources.R4B.bundle import Bundle

from .. import params
from .service import compute_report
from .store import Store

HGNC = {"HBB": "HGNC:4827", "CYP21A2": "HGNC:2600", "SMN1": "HGNC:11117"}
# Affected phenotypes (labels in data/params/loci.yaml) and the ICD-10 codes read for them; the first is written.
ICD10_BY_PHENOTYPE = {
    ("CYP21A2", "classic congenital adrenal hyperplasia"): ("E25.0",),
    ("HBB", "beta-thalassaemia major or intermedia"): ("D56.1",),
    ("HBB", "sickle cell disease"): ("D57.1", "D57.0"),
    ("SMN1", "spinal muscular atrophy"): ("G12.1", "G12.0"),
}
LOINC = "http://loinc.org"
TASK_STATUS = {"awaiting_counsellor": "requested", "approved": "accepted", "sent": "in-progress",
               "opened": "in-progress", "understood": "in-progress", "booked": "in-progress",
               "tested": "in-progress", "closed": "completed", "withdrawn": "cancelled",
               "declined_by_relative": "rejected", "no_response": "failed"}


def fid(id_: str) -> str:
    """FHIR ids allow only [A-Za-z0-9-.] (max 64); map anything else to '-'."""
    return re.sub(r"[^A-Za-z0-9.-]", "-", id_)[:64]


def _ref(kind: str, id_: str) -> dict[str, str]:
    return {"reference": f"{kind}/{fid(id_)}"}


def case_bundle(store: Store, case: dict[str, Any]) -> dict[str, Any]:
    rep = compute_report(case)
    rec = params.load().get(case["locus_id"])
    gene = rec.locus.gene if rec else case["locus_id"]
    index = case["index_person_id"]
    entries: list[dict[str, Any]] = []

    def add(resource: dict[str, Any]) -> None:
        resource["id"] = fid(resource["id"])
        entries.append({"fullUrl": f"urn:uuid:{resource['resourceType'].lower()}-{resource['id']}", "resource": resource})

    sex_map = {"female": "female", "male": "male"}
    people = {p["id"]: p for p in case["pedigree"]["people"]}
    add({"resourceType": "Patient", "id": index, "gender": sex_map[people[index]["sex"]],
         "meta": {"security": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue", "code": "PSEUDED"}]}})
    for pid, p in people.items():
        if pid == index:
            continue
        fmh: dict[str, Any] = {"resourceType": "FamilyMemberHistory", "id": pid, "status": "partial",
                               "patient": _ref("Patient", index),
                               "relationship": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-RoleCode",
                                                            "code": "FAMMEMB", "display": "family member"}]},
                               "sex": {"coding": [{"system": "http://hl7.org/fhir/administrative-gender",
                                                   "code": sex_map[p["sex"]]}]}}
        if p.get("deceased"):
            fmh["deceasedBoolean"] = True
        if p.get("status") == "affected":
            fmh["condition"] = [{"code": {"text": p.get("affected_with")}}]
        add(fmh)
    if people[index].get("status") == "affected" and people[index].get("affected_with"):
        label = people[index]["affected_with"]
        icd = ICD10_BY_PHENOTYPE.get((case["locus_id"], label))
        add({"resourceType": "Condition", "id": f"cond-{index}", "subject": _ref("Patient", index),
             "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
             "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                                "code": "confirmed"}]},
             "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": icd[0]}] if icd else None, "text": label}})
    for pid, p in people.items():
        if not p.get("test"):
            continue
        # One Observation per variant class found (two for a compound heterozygote), or one saying "Absent".
        groups = sorted(Counter(p["test"]["detected"]).items()) or [(None, 0)]
        for allele, copies in groups:
            present = allele is not None
            component = [{"code": {"coding": [{"system": LOINC, "code": "48018-6", "display": "Gene studied [ID]"}]},
                          "valueCodeableConcept": {"coding": [{"system": "http://www.genenames.org/geneId",
                                                               "code": HGNC.get(gene, gene), "display": gene}]}}]
            if present:
                component.append({"code": {"coding": [{"system": LOINC, "code": "53034-5", "display": "Allelic state"}]},
                                  "valueCodeableConcept": {"coding": [
                                      {"system": LOINC, "code": "LA6705-3", "display": "Homozygous"} if copies == 2 else
                                      {"system": LOINC, "code": "LA6706-1", "display": "Heterozygous"}]}})
                component.append({"code": {"coding": [{"system": LOINC, "code": "53037-8",
                                                       "display": "Genetic variation clinical significance [Imp]"}]},
                                  "valueCodeableConcept": {"coding": [{"system": LOINC, "code": "LA6668-3", "display": "Pathogenic"}]}})
                if gene == "HBB" and allele == "S":
                    component.append({"code": {"coding": [{"system": LOINC, "code": "48004-6", "display": "DNA change (c.HGVS)"}]},
                                      "valueString": "c.20A>T"})
            add({"resourceType": "Observation", "id": f"obs-{pid}" + (f"-{allele}" if len(groups) > 1 else ""), "status": "final",
                 "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                           "code": "laboratory"}]}],
                 "code": {"coding": [{"system": LOINC, "code": "69548-6", "display": "Genetic variant assessment"}]},
                 "subject": _ref("Patient", index), "focus": [_ref("FamilyMemberHistory", pid)] if pid != index else None,
                 "valueCodeableConcept": {"coding": [{"system": LOINC, "code": "LA9633-4" if present else "LA9634-2",
                                                      "display": "Present" if present else "Absent"}],
                                          "text": allele or "no variant detected"},
                 "component": component})
    if rep.get("status") == "ok":
        for pid, pr in rep["people"].items():
            if not pr["informative"]:
                continue
            add({"resourceType": "RiskAssessment", "id": f"risk-{pid}", "status": "preliminary",
                 "subject": _ref("Patient", index),
                 "method": {"text": rep["engine"]},
                 "basis": [_ref("FamilyMemberHistory", x) for x in people if x != index][:50],
                 "prediction": [{"outcome": {"text": f"carries a variant in {gene}"},
                                 "probabilityDecimal": round(pr["computed"]["p_any_variant"], 6)}],
                 "note": [{"text": "Calculated from the family tree; not a test result."}]})
    for scope, c in (case.get("consents") or {}).items():
        add({"resourceType": "Consent", "id": f"consent-{scope}",
             "status": "active" if c.get("granted") and not c.get("withdrawn_at") else "inactive",
             "scope": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/consentscope", "code": "patient-privacy"}]},
             "category": [{"coding": [{"system": "http://loinc.org", "code": "59284-0", "display": "Consent Document"}]}],
             "patient": _ref("Patient", index), "dateTime": c.get("granted_at"),
             "policyRule": {"text": f"Silsila permission '{scope}' (wording: template {c.get('wording_template')})"}})
    for inv in store.list("invitation", case["id"]):
        add({"resourceType": "Task", "id": inv["id"], "status": TASK_STATUS[inv["status"]], "intent": "proposal",
             "description": f"Offer carrier testing to a relative ({inv['channel']})",
             "for": _ref("Patient", index), "focus": _ref("FamilyMemberHistory", inv["person_id"]),
             "authoredOn": inv["history"][0]["at"], "lastModified": inv["history"][-1]["at"],
             "businessStatus": {"text": inv["status"]}})
    for ev in reversed(store.audit_events(case["id"], limit=200)):
        add({"resourceType": "AuditEvent", "id": f"audit-{ev['seq']}",
             "type": {"system": "http://dicom.nema.org/resources/ontology/DCM", "code": "110110", "display": "Patient Record"},
             "recorded": ev["ts"], "outcome": "0" if ev["outcome"] == "success" else "4",
             "agent": [{"who": {"display": f"{ev['role']}:{ev['actor']}"}, "requestor": True}],
             "source": {"observer": {"display": "Silsila"}},
             "entity": [{"what": {"display": ev["entity"] or ev["action"]},
                         "detail": [{"type": "hash", "valueString": ev["hash"]}]}]})
    for e in entries:  # drop None values introduced above
        e["resource"] = {k: v for k, v in e["resource"].items() if v is not None}
        if "code" in e["resource"] and isinstance(e["resource"]["code"], dict):
            e["resource"]["code"] = {k: v for k, v in e["resource"]["code"].items() if v is not None}
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    return Bundle.model_validate(bundle).model_dump(mode="json", exclude_none=True)
