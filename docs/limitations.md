# Assumptions and limitations

Silsila is a prototype tested only on synthetic data. Nothing here has been used with real patients.

## Clinical scope
- Calculates chances only for autosomal recessive conditions at three loci with published UAE data:
  HBB (beta-thalassaemia, sickle cell), CYP21A2 (classic congenital adrenal hyperplasia) and SMN1 (spinal
  muscular atrophy). Alpha-thalassaemia and primary congenital glaucoma are deliberately not calculated
  because the UAE parameters they need are not published (`data/params/loci.yaml`, `excluded_loci`).
- Full penetrance is assumed: a person recorded as unaffected is treated as not having two pathogenic
  alleles. This is not true for every condition (for example CYP1B1, which is excluded partly for this reason).
- Beta-zero and beta-plus thalassaemia alleles are combined; severity is not modelled. HbD-Punjab, HbE and
  other variants are not modelled and are referred to a counsellor.
- Carrier tests are assumed to have no false positives (specificity 1). Sensitivity uses published detection
  rates where they exist. No detection rate is published for CYP21A2, so residual risk after a negative test
  is not calculated for that gene, and the app says so.
- Population inputs come from UAE-national studies from 1997-2024 with the sample sizes stated in the
  register. They may not describe a particular family, tribe or emirate, or non-Emirati residents.
- Background inbreeding (F = 0.0222, al-Gazali 1997) represents relatedness not drawn in the family tree.
  Relatedness that is drawn is computed exactly.
- The invitation order uses family structure and pregnancy only. It does not yet use age, so couples past
  childbearing age can rank highly; counsellors approve every invitation.
- Very large or highly interlinked family trees can exceed the engine's memory limit; the app then shows no
  number and refers the case to a counsellor.

## Content and language
- Clinical explanations are verbatim MedlinePlus Genetics text (US National Library of Medicine). It is
  authoritative but written for a US audience; paragraphs about US law or programmes are excluded.
- Arabic versions of quoted paragraphs, condition names and interface templates are machine translations.
  Three systems were compared (`data/content/translations/ar/qc_report.json`), but none has been reviewed by
  a native-speaking clinician. This review is required before any use with patients.
- Templates are the development team's procedural wording and have not been reviewed by a genetic
  counsellor or by religious and cultural advisers.
- Reading level (English, `docs/evidence/readability.json`): Silsila's own wording scores Flesch-Kincaid grade
  6.9, but the quoted MedlinePlus text scores grade 13.4 (college level). Quoted text is not
  simplified. No readability measure was applied to the Arabic text; none validated for Arabic health text
  was used.
- Read aloud uses a synthetic voice (Azure AI Speech) reading fixed approved text only. Sentences containing a
  name or a number (for example an invitation that names its sender) have no audio. No clip has been checked
  by a native listener; mispronunciation is possible, most of all in the machine-translated Arabic. The
  listener may be overheard (hazard H20).
- The interface labels added for these features (Listen, Stop, "synthetic voice (Azure)", the read-aloud
  notice, "Common questions") are short functional labels written by the development team; like the
  templates, they await clinical and native-language review.

## Importing results (FHIR)
- The import reads one index result from a FHIR R4B Bundle: a Patient, a genomics Observation (LOINC 69548-6
  with gene, allelic state and clinical significance) and an optional confirmed Condition. It follows no
  published Malaffi or DoH profile, because the team has not seen one; the sample record is fictional and
  "Malaffi-style" only in being the kind of record an exchange carries. A pilot would map to the real profile.
- Variants are mapped to the engine's allele classes very simply: for HBB, c.20A>T is the sickle variant and any
  other pathogenic variant is treated as beta-thalassaemia; for the other genes, any pathogenic variant is the
  one modelled allele. A pilot needs the laboratory's own classification.
- Only the three calculated genes are accepted. Anything else is refused and referred to a counsellor.

## Message triage
- Trained and tested on synthetic messages written by an AI model; not validated on real messages.
  Specificity is deliberately low. Safety does not rely on it: every message is read by a person and every
  reply carries the 998/999 emergency line.

## Evidence
- All benchmarks use synthetic families and messages. The family simulator relies on labelled structural
  assumptions (`backend/src/silsila/sim/assumptions.yaml`) tested in a sensitivity analysis.
- Cascade yields are projections, not observed outcomes. Uptake, comprehension and family effects need a
  pilot to measure.

## Engineering
- SQLite storage and demo passwords are for the prototype only. A pilot needs a managed database in a UAE
  region with encryption at rest, UAE PASS identity, MFA for staff, and ADHICS-aligned security review.
- The service targets used to flag overdue steps (for example 2 days for counsellor approval) are pilot
  assumptions, not published standards.
