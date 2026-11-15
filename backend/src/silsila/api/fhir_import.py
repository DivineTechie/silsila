"""Import an index result from a FHIR R4B genomics record: the reverse of `fhir.case_bundle`.

A screening programme or a health information exchange delivers the result that starts a cascade (a newborn's
genetic screen, a carrier finding, a diagnosis). This module reads that record at counsellor intake and turns
it into the first entry of a Silsila case. It is deliberately strict:

  * A record is either read completely or refused with a reason a counsellor can act on. Nothing is guessed
    and nothing fails silently.
  * A result is only accepted when it could start a cascade: a final result, about the patient in the
    record, in a gene Silsila calculates, classified pathogenic or likely pathogenic when a classification
    is given. A variant of uncertain significance is refused: it is not a reason to contact relatives.
  * Names, identifiers, dates of birth and addresses in the record are not stored. The case keeps the
    person's sex, the finding, and a SHA-256 of the record it came from.
  * The counsellor previews the reading first (dry run) and then confirms. The new case has no permission
    recorded: the family still decides whether anything is calculated or anyone is told.

What is read:
  Patient                         exactly one; gender
  Observation, LOINC 69548-6      "Genetic variant assessment": Present (LA9633-4) or Absent (LA9634-2)
    component 48018-6             gene studied (HGNC code)
    component 53034-5             allelic state: Heterozygous (LA6706-1) or Homozygous (LA6705-3)
    component 53037-8             clinical significance: Pathogenic (LA6668-3), Likely pathogenic (LA26332-9)
    component 48004-6             DNA change (c.HGVS); used only to tell the sickle variant from other HBB variants
  Condition                       a diagnosis explicitly marked confirmed, by ICD-10 code or by the condition's name
LOINC and ICD-10 codes were checked against tx.fhir.org on 15 Nov 2026.

Limits (also in docs/limitations.md): variants are mapped to the engine's allele classes very simply (for
HBB, c.20A>T is the sickle variant and any other pathogenic variant is treated as beta-thalassaemia); a pilot
needs the laboratory's own classification. The sample file in data/demo/fhir is fictional and "Malaffi-style"
only in the sense of being a FHIR record of the kind an exchange carries; it follows no Malaffi specification.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fhir.resources.R4B.bundle import Bundle
from pydantic import ValidationError

from .. import params
from . import service
from .fhir import HGNC, ICD10_BY_PHENOTYPE
from .store import Store, new_id, now

LOINC = "http://loinc.org"
ICD10 = "http://hl7.org/fhir/sid/icd-10"
GENE_SYSTEMS = ("http://www.genenames.org/geneId", "http://www.genenames.org")
LOCUS_BY_HGNC = {code: locus for locus, code in HGNC.items()}
PHENOTYPE_BY_ICD10 = {code: (locus, label) for (locus, label), codes in ICD10_BY_PHENOTYPE.items() for code in codes}
HBS_HGVS = "c.20A>T"  # HBB:c.20A>T (p.Glu7Val), the sickle variant
INDEX_SOURCES = ("newborn_screen", "premarital_at_risk", "diagnosed_child", "carrier_result")
MAX_BYTES, MAX_ENTRIES = 1_000_000, 200
REFER = " Refer this record to a genetic counsellor for manual entry."


class ImportRefused(service.Invalid):
    """The record cannot start a case as it stands. The message says why and what to do (HTTP 422)."""


def record_hash(bundle: Any) -> str:
    return hashlib.sha256(json.dumps(bundle, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _codes(concept: dict[str, Any] | None, system: str | tuple[str, ...]) -> list[str]:
    systems = (system,) if isinstance(system, str) else system
    return [c.get("code") for c in (concept or {}).get("coding", []) if c.get("system") in systems and c.get("code")]


def _component(obs: dict[str, Any], loinc: str) -> dict[str, Any] | None:
    hits = [c for c in obs.get("component", []) if loinc in _codes(c.get("code"), LOINC)]
    if len(hits) > 1:
        raise ImportRefused(f"Observation {obs.get('id', '?')} states component {loinc} more than once." + REFER)
    return hits[0] if hits else None


def _points_at(ref: dict[str, Any] | None, resource: dict[str, Any], full_url: str | None) -> bool:
    r = (ref or {}).get("reference")
    return bool(r) and r in (f"{resource['resourceType']}/{resource.get('id')}", full_url)


def read_index_result(bundle: Any, index_source: str | None = None) -> dict[str, Any]:
    """Read one index result from a FHIR R4B Bundle. Returns a draft for the counsellor to confirm, or raises
    ImportRefused with the reason."""
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise ImportRefused("This is not a FHIR Bundle: the record must be a JSON object with resourceType 'Bundle'.")
    if len(json.dumps(bundle, default=str)) > MAX_BYTES or len(bundle.get("entry") or []) > MAX_ENTRIES:
        raise ImportRefused(f"The record is too large to import here (limit {MAX_ENTRIES} entries, 1 MB)." + REFER)
    try:
        Bundle.model_validate(bundle)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"]) or "Bundle"
        raise ImportRefused(f"Not a valid FHIR R4B Bundle: {where}: {first['msg']} ({e.error_count()} problem(s) in all).") from e

    entries = [(en.get("fullUrl"), en["resource"]) for en in bundle.get("entry") or [] if isinstance(en.get("resource"), dict)]
    by_type: dict[str, list[tuple[str | None, dict[str, Any]]]] = {}
    for url, res in entries:
        by_type.setdefault(res["resourceType"], []).append((url, res))

    patients = by_type.get("Patient", [])
    if len(patients) != 1:
        raise ImportRefused(f"The record must contain exactly one Patient; it contains {len(patients)}." + REFER)
    patient_url, patient = patients[0]
    if patient.get("gender") not in ("male", "female"):
        raise ImportRefused("The Patient's sex is not recorded as male or female, which a family tree needs." + REFER)

    notes: list[str] = []
    warnings: list[str] = []
    findings: list[dict[str, Any]] = []
    for _, obs in by_type.get("Observation", []):
        oid = obs.get("id", "?")
        if "69548-6" not in _codes(obs.get("code"), LOINC):
            notes.append(f"Observation {oid} is not a genetic variant assessment (LOINC 69548-6) and was not read.")
            continue
        if not _points_at(obs.get("subject"), patient, patient_url):
            raise ImportRefused(f"Observation {oid} is not about the Patient in this record." + REFER)
        if obs.get("focus"):
            notes.append(f"Observation {oid} is about a relative (it has a focus) and was not imported: only the index result is.")
            continue
        if obs.get("status") not in ("final", "amended", "corrected"):
            raise ImportRefused(f"Observation {oid} has status '{obs.get('status')}'. Only a final result can start a cascade." + REFER)
        gene_c = _component(obs, "48018-6")
        gene_codes = _codes((gene_c or {}).get("valueCodeableConcept"), GENE_SYSTEMS)
        if not gene_codes:
            raise ImportRefused(f"Observation {oid} does not say which gene was studied (LOINC 48018-6 with an HGNC code)." + REFER)
        locus = LOCUS_BY_HGNC.get(gene_codes[0])
        if locus is None or locus not in params.load():
            raise ImportRefused(f"Silsila does not calculate chances for the gene {gene_codes[0]} in this version, because the "
                                "population data it needs for the UAE are not in its register." + REFER)
        value = _codes(obs.get("valueCodeableConcept"), LOINC)
        if "LA9633-4" in value:
            present = True
        elif "LA9634-2" in value:
            present = False
        else:
            raise ImportRefused(f"Observation {oid} does not say whether a variant is Present (LA9633-4) or Absent (LA9634-2)." + REFER)
        sig = _codes((_component(obs, "53037-8") or {}).get("valueCodeableConcept"), LOINC)
        if present and sig and not {"LA6668-3", "LA26332-9"} & set(sig):
            raise ImportRefused(f"Observation {oid} reports a variant that is not classified pathogenic or likely pathogenic "
                                "(for example a variant of uncertain significance). That is not a reason to contact relatives." + REFER)
        if present and not sig:
            warnings.append(f"Observation {oid} gives no clinical significance. Confirm with the laboratory that the variant is "
                            "pathogenic or likely pathogenic before any relative is invited.")
        state = _codes((_component(obs, "53034-5") or {}).get("valueCodeableConcept"), LOINC)
        copies = 2 if "LA6705-3" in state else 1 if "LA6706-1" in state else None
        dna_c = _component(obs, "48004-6") or {}
        dna = dna_c.get("valueString") or (dna_c.get("valueCodeableConcept") or {}).get("text")
        findings.append({"observation": oid, "locus": locus, "present": present, "copies": copies, "dna": dna})

    diagnoses: list[dict[str, Any]] = []
    for _, cond in by_type.get("Condition", []):
        cid = cond.get("id", "?")
        if not _points_at(cond.get("subject"), patient, patient_url):
            raise ImportRefused(f"Condition {cid} is not about the Patient in this record." + REFER)
        ver = _codes(cond.get("verificationStatus"), "http://terminology.hl7.org/CodeSystem/condition-ver-status")
        if "confirmed" not in ver:
            warnings.append(f"Condition {cid} is recorded as '{ver[0] if ver else 'no verification status'}', not confirmed, "
                            "and was not used.")
            continue
        hit = next((PHENOTYPE_BY_ICD10[c] for c in _codes(cond.get("code"), ICD10) if c in PHENOTYPE_BY_ICD10), None)
        if hit is None:
            text = ((cond.get("code") or {}).get("text") or "").strip().lower()
            hit = next(((lid, ph) for lid, rec in params.load().items() for ph in rec.locus.affected_phenotypes
                        if text and text == ph.lower()), None)
        if hit is None:
            notes.append(f"Condition {cid} is not one of the conditions Silsila calculates and was not imported.")
            continue
        diagnoses.append({"condition": cid, "locus": hit[0], "phenotype": hit[1]})

    loci = {f["locus"] for f in findings} | {d["locus"] for d in diagnoses}
    if not loci:
        raise ImportRefused("The record has no genetic variant assessment (LOINC 69548-6) and no diagnosis that Silsila can read." + REFER)
    if len(loci) > 1:
        raise ImportRefused(f"The record has results for more than one gene ({', '.join(sorted(loci))}). Import one condition at a time." + REFER)
    locus_id = loci.pop()
    rec = params.load()[locus_id]
    present = [f for f in findings if f["present"]]
    if present and len(present) != len(findings):
        raise ImportRefused("The record says a variant is both present and absent in the same gene. It cannot be read safely." + REFER)
    phenotypes = {d["phenotype"] for d in diagnoses}
    if len(phenotypes) > 1:
        raise ImportRefused(f"The record gives more than one diagnosis ({', '.join(sorted(phenotypes))})." + REFER)
    if not present and not diagnoses:
        raise ImportRefused("No variant was found and no diagnosis is recorded, so there is no result to start a cascade from. "
                            "Nothing was imported.")
    if not present and findings:
        raise ImportRefused("The record gives a diagnosis but its genetic result says no variant was found. It cannot be read safely." + REFER)

    pathogenic = [a.id for a in rec.locus.alleles if a.pathogenic]
    detected: list[str] | None = []
    for f in present:
        if f["copies"] is None:
            if not diagnoses:
                raise ImportRefused(f"Observation {f['observation']} does not say whether the variant is in one copy or two "
                                    "(allelic state, LOINC 53034-5), so a carrier cannot be told from an affected person." + REFER)
            detected = None  # the diagnosis carries the status; the number of copies is not recorded
            notes.append(f"Observation {f['observation']} gives no allelic state; the confirmed diagnosis is used instead.")
            break
        if locus_id == "HBB":
            allele = "S" if (f["dna"] or "").replace(" ", "").endswith(HBS_HGVS) else "B"
        else:
            allele = pathogenic[0]
        detected += [allele] * f["copies"]
    if detected is not None and len(detected) > 2:
        raise ImportRefused("The record lists more than two variant copies in one gene. It cannot be read safely." + REFER)

    status, affected_with = "unknown", None
    if diagnoses:
        status, affected_with = "affected", phenotypes.pop()
        if detected:
            implied = rec.locus.phenotypes.get(tuple(sorted((detected + ["N"])[:2])))  # type: ignore[arg-type]
            if implied != affected_with:
                raise ImportRefused(f"The diagnosis ({affected_with}) does not fit the genetic result in the same record "
                                    f"({', '.join(detected)}: {implied or 'not a known combination'})." + REFER)
    elif detected and len(detected) == 2:
        warnings.append("Two variant copies were found but no diagnosis is recorded. Confirm the diagnosis with the treating "
                        "clinician; the case is created with the test result only.")

    if index_source is not None and index_source not in INDEX_SOURCES:
        raise ImportRefused(f"Unknown kind of index result '{index_source}'.")
    dropped = sorted(k for k in ("identifier", "name", "birthDate", "address", "telecom", "photo", "contact") if patient.get(k))
    return {
        "locus_id": locus_id, "gene": rec.locus.gene, "condition": rec.display, "condition_ar": rec.display_ar,
        "index": {"sex": patient["gender"], "status": status, "affected_with": affected_with,
                  "test": {"detected": detected} if detected else None},
        "index_source": index_source or ("diagnosed_child" if status == "affected" else "carrier_result"),
        "summary": ("affected: " + affected_with) if affected_with else
                   ("carrier: one copy of " + detected[0]) if detected and len(detected) == 1 else "two variant copies, no diagnosis recorded",
        "warnings": warnings, "notes": notes,
        "not_stored": dropped,  # personal fields present in the record that the case does not keep
        "source": {"format": "FHIR R4B Bundle", "sha256": record_hash(bundle), "bundle_id": bundle.get("id"),
                   "observations": [f["observation"] for f in present], "conditions": [d["condition"] for d in diagnoses],
                   "resources": {k: len(v) for k, v in sorted(by_type.items())}},
    }


def create_case(store: Store, counsellor: dict[str, Any], draft: dict[str, Any], family_user_id: str) -> dict[str, Any]:
    """Create the case a confirmed draft describes. No permission is recorded: until the family gives it,
    nothing is calculated and nobody can be invited."""
    family = store.get("user", family_user_id)
    if family is None or family.get("role") != "family":
        raise ImportRefused("Choose the family account this result belongs to.")
    idx = draft["index"]
    person: dict[str, Any] = {"id": "index", "sex": idx["sex"], "name": "Index person", "name_ar": "الشخص الدليل",
                              "mother": "mother", "father": "father", "status": idx["status"]}
    if idx["affected_with"]:
        person["affected_with"] = idx["affected_with"]
    if idx["test"]:
        person["test"] = {"detected": idx["test"]["detected"], "recorded_at": now(), "recorded_by": "fhir_import"}
    people = [{"id": "mother", "sex": "female", "name": "Mother", "name_ar": "الأم", "mother": None, "father": None, "status": "unknown"},
              {"id": "father", "sex": "male", "name": "Father", "name_ar": "الأب", "mother": None, "father": None, "status": "unknown"},
              person]
    case_id = new_id("case")
    case = {"id": case_id, "case_id": case_id, "locus_id": draft["locus_id"], "index_person_id": "index",
            "index_source": draft["index_source"], "family_user_id": family_user_id,
            "title": f"Imported result: {draft['condition']}", "title_ar": f"نتيجة مستوردة: {draft['condition_ar']}",
            "pedigree": {"people": people, "unions": []}, "consents": {},
            "source_record": {**draft["source"], "received_at": now(), "imported_by": counsellor["id"]}}
    if service.compute_report(case)["status"] != "ok":  # the same check every case goes through
        raise ImportRefused("The imported result does not make a consistent family record." + REFER)
    store.put("case", case)
    store.audit(counsellor["id"], counsellor["role"], "fhir.import", case_id=case_id,
                detail={"sha256": draft["source"]["sha256"], "locus": draft["locus_id"], "index_source": draft["index_source"],
                        "warnings": len(draft["warnings"]), "not_stored": draft["not_stored"]})
    return case
