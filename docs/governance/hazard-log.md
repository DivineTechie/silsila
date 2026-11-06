# Hazard log and risk register

Method: DoH AI Risk Management Protocol (likelihood 1-5 x impact 1-5 = exposure; residual risk after
controls). Ratings are the development team's assessment for the prototype and must be re-assessed with the
deploying programme and DDGO. "Owner" is the role accountable in a pilot.

| ID | Hazard | Cause | Controls in Silsila | Verified by | Residual | Owner |
|---|---|---|---|---|---|---|
| H1 | Wrong carrier or couple probability | Engine bug; looped (cousin) families | Exact variable elimination; agreement with pgmpy to ~1e-16 and with Monte Carlo; textbook checks (kinship, Wright formula, 2/3 sibling risk, residual risk) | `tests/engine`, evidence B1 | Low | Product owner |
| H2 | Probability based on wrong population inputs | Study population differs from family; outdated studies | Every input sourced (PMID) and shown in "show the working"; conditions without UAE data are not calculated; background inbreeding stated | `test_params.py`, `loci.yaml` | Medium | Clinical lead |
| H3 | Results that cannot all be true are hidden or averaged | Recording error, sample mix-up, misattributed parentage | Engine raises `InconsistentEvidence`; no numbers shown; case enters counsellor queue | `test_inconsistent_results_are_flagged_not_hidden`, API test | Low | Counsellor |
| H4 | Advice or directive wording reaches a person | Model-generated text; edited templates | No runtime text generation; output gate re-derives every message from approved content; non-directive templates | `test_gate_*`, demo injection | Low | Product owner |
| H5 | Crisis message not acted on | Classifier misses dialect or indirect phrasing | Every message read by a person; every reply carries 998/999; crisis alert sensitivity 0.961 (95% CI 0.890-0.986) on blind set | `triage_rules_ngram.json` | Medium | Counselling lead |
| H6 | Genetic information disclosed to the wrong person | Guessed links; cross-family access; social engineering | Unguessable links; role checks; relatives see only chosen disclosure; privacy refusals; 0 disclosures in 10,000 attacks | `privacy_api.json` | Low | Data protection officer |
| H7 | Relative identifies the sender of an anonymous invitation | Small families | Explicit notice in every anonymous invitation; index person chooses channel; counsellor review | `invite.anonymity_notice` | Medium (inherent) | Counsellor |
| H8 | Family pressure or blame after disclosure, often on women | Social dynamics | Non-directive wording; decline option ends the process; counsellor contact | templates | Medium (inherent) | Counsellor |
| H9 | False reassurance after a negative test | Imperfect test sensitivity | Residual risk computed from published detection rates; where none is published (CYP21A2) the app says it cannot calculate it | `result.residual_not_modelled` | Low | Clinical lead |
| H10 | Audit records altered | Insider with database access | SHA-256 hash chain; verification endpoint shows first broken event | API test, demo tamper | Low | Security officer |
| H11 | Data leaves the UAE | Cloud model calls | Optional model off by default; redaction of numbers and emails; deployment in UAE North | `triage.redact`, deployment notes | Low (if deployed as specified) | Infrastructure owner |
| H12 | Arabic wording mistranslated | Machine translation | Marked as pending native clinical review; English source shown on request | `templates.yaml` meta | Medium (until review) | Clinical lead |
| H13 | Misuse for matchmaking or registries | Pressure from families or third parties | No compatibility "matching" feature; no registry; success metrics exclude marriage outcomes | design | Low | Programme lead |
