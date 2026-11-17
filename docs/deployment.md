# Deployment notes

**Hosting.** Two containers (API, web) on Azure Container Apps in UAE North, so compute and storage stay in
the UAE (DoH Responsible AI Standard 3.1.4.5.1). `deploy/azure-deploy.sh` creates the resource group,
registry, environment and both apps, stores demo passwords and the token secret as Container Apps secrets,
and restricts the API's allowed origin to the web app. SQLite is used for the prototype;
a pilot would use a managed database in the same region with encryption at rest.

**Identity.** Demo accounts with scrypt-hashed passwords and signed tokens. A pilot would use UAE PASS for
families and the provider's identity system (with MFA) for counsellors.

**Optional language model.** Off by default. If enabled, set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`
and `AZURE_OPENAI_DEPLOYMENT` to a deployment in a UAE region. It receives message text with numbers and
email addresses removed, returns labels only, and cannot remove labels set by the rules or n-gram model.

**Interoperability.** An index result is read at counsellor intake from a FHIR R4B Bundle (Patient, a
genomics Observation with LOINC 69548-6, gene, allelic state and clinical significance, and an optional
confirmed Condition): checked first, refused with the reason if it cannot be read safely, and stored without
the name, identifier or date of birth (`backend/src/silsila/api/fhir_import.py`). Cases export as FHIR R4B
Bundles (Patient, Condition, FamilyMemberHistory, Observation with LOINC 69548-6 and HGNC gene codes,
RiskAssessment, Consent, Task, AuditEvent). Malaffi exchanges HL7 v2 feeds today; a pilot would map the
Observation and Task content to those feeds through the provider's integration engine rather than connect
directly. The sample record in `data/demo/fhir` is fictional and follows no Malaffi specification.

**The guide.** "Ask about Silsila" (`/api/guide`) is public and needs no sign-in. It calls no outside service
and stores no question text. Its lookups read the evidence files shipped in the image and run the engine on
the server; the outcome counts it shows are aggregate.

**Configuration.** See `backend/.env.example`. `SILSILA_DEMO=0` disables the demonstration endpoints
(password-free personas, the guided story, reset, audit tampering and output-gate injection).

**Measured on the hosted prototype (16 Nov 2026).** One exact recalculation of the 61-person Family Twin
clan: 0.7 s with no extra results, a median of 0.9 s (0.7 to 1.2 s) once results are recorded, on 2 vCPU
(`docs/evidence/twin_hosted_timing.json`). A Watch a cascade step took 0.5 to 0.9 s from a browser outside
the UAE.

## Measured capacity of the hosted prototype (17 Nov 2026)

`backend/scripts/load_test.py` ran against the hosted API and web app (API 2 vCPU / 4 GiB, one replica, SQLite)
from a client outside the UAE, 30 seconds at each level; the full record is
[`docs/evidence/load_hosted.json`](evidence/load_hosted.json).

| What | Clients at once | Requests a second | Median | 95th percentile | Errors |
|---|---|---|---|---|---|
| A relative opens their link | 25 | 382 | 61 ms | 78 ms | 0 |
| Guide questions and the home page | 25 | 245 | 72 ms | 231 ms | 0 |
| Exact recalculation of the 61-person clan | 1 | 1.6 | 614 ms | 709 ms | 0 |
| Exact recalculation of the 61-person clan | 8 | 1.2 | 6,288 ms | 8,468 ms | 0 |

What this shows: reading pages is not the limit on this size. The exact recalculation is: one replica does about
1.5 a second whatever the number of clients, so extra requests wait in line. In a programme a recalculation
happens when a result is recorded, not on every page view, and most families are far smaller than 61 people
(median 3 ms for 10 people, 31 ms for 30). More replicas would need the managed database first, because SQLite
is a single file. That is not built.

