# Abu Dhabi DoH Responsible AI Standard: clause map

Standard: *Responsible Artificial Intelligence (AI) Standard*, DoH/ST/DDGO/RAI/V1/2025 (Oct 2025),
<https://www.doh.gov.ae/-/media/B84FF5DD027846699C51F36C439A580F.ashx>.
Risk method: *AI Risk Management Protocol*, DoH/Protocol/DDGO/RALRM/V1/2025 (Jul 2025),
<https://www.doh.gov.ae/-/media/8BD7C5DEC5974781B4C11BA00964B6F7.ashx>.

Status key: **Met** = implemented and tested in this prototype. **Partly** = implemented in part; the gap is
stated. **Deployment** = an organisational or infrastructure duty that only a deploying licensed entity can
fulfil; the prototype shows how it would be met.

## Risk classification (Protocol, 3.3)

| Item | Assessment |
|---|---|
| Asset criticality | **High (3)**: the Protocol's example for this level is clinical decision support "that can influence patient treatment with complete human oversight". Silsila informs testing and counselling decisions and keeps every decision with people. |
| Main threats considered | Wrong probability (engine error), wrong or harmful wording, missed crisis message, disclosure of genetic information to the wrong person, tampering with records, missing or contradictory family data, population data that do not fit the family. See [hazard log](hazard-log.md). |
| Consequence for deployment | High residual risk requires DoH conformity assessment before and after deployment, coordinated with DDGO (3.3.1.2.2). The [pilot protocol](../pilot-protocol.md) starts with a shadow-mode phase to support this. |

## Clause map

| Clause | Requirement (short) | How Silsila addresses it | Evidence | Status |
|---|---|---|---|---|
| 3.1.1.1.1 | Co-design with clinicians and patients | Not yet done. Usability sessions with Arabic and English speakers and a genetic-counsellor review are planned before any pilot. | [pilot protocol](../pilot-protocol.md) | Partly |
| 3.1.1.1.3 | Fit existing workflows | Counsellor queue, FHIR R4B export, family physician routing; designed to sit beside the premarital and newborn screening programmes. | `backend/src/silsila/api/fhir.py` | Partly |
| 3.1.1.2.1-2 | Human in or on the loop; escalation by risk | Nothing is sent to a relative without counsellor approval. Every free-text message is read by a person; triage only orders the queue. Inconsistent families show no numbers and go to review. | `service.transition`, `service.queue`, `tests/test_api_flow.py` | Met |
| 3.1.2.1.1 | Reliable under failures and adversarial input | 200+ malformed and contradictory inputs; 10,000 unauthorised requests. | `docs/evidence/` (B2, privacy_api.json) | Met |
| 3.1.2.1.2 | Graceful degradation and fallback | The app works with no language model at all. Missing detection rates disable residual-risk numbers and say so. Unsupported conditions show a referral message instead of numbers. | `result.residual_not_modelled`, `result.excluded_locus` | Met |
| 3.1.2.1.3 | Safety testing and failure-mode analysis before deployment | Hazard log with controls and tests for each hazard. | [hazard log](hazard-log.md) | Met |
| 3.1.2.1.4, 3.1.3.1.3 | Post-deployment monitoring | Audit log records every triage decision, block and access; pilot metrics defined. Live drift monitoring is not built. | [pilot protocol](../pilot-protocol.md) | Partly |
| 3.1.3.1.1-2 | Validate against benchmarks across diverse data | Engine checked against textbook values, a second exact implementation (pgmpy) and Monte Carlo; triage checked on a blind 400-message set in four language varieties with 95% CIs. | `docs/evidence/README.md` | Met (synthetic data) |
| 3.1.3.1.5 | Keep validation records | Per-case CSV logs (input, expected, actual, error source) for every benchmark. | `docs/evidence/*_cases.csv` | Met |
| 3.1.4.2.1-3 | RBAC, least privilege, logging | Roles: family, counsellor, relative (link only). Every access and every refusal is logged. MFA and time-bound privileges are deployment items (UAE PASS). | `tests/test_api_flow.py::test_privacy_between_families_and_roles` | Partly |
| 3.1.4.4.1 | Minimum necessary data | The engine needs sex, parent links, recorded results and pregnancy status only. No ID numbers, dates of birth or contact details are stored. Names are free text chosen by the family. | `backend/src/silsila/api/seed.py` | Met |
| 3.1.4.4.2 | Encryption, pseudonymisation; no training on production data | FHIR export is pseudonymous (no names or identifiers). The only trained model (message triage) was trained on synthetic messages. Encryption at rest is a deployment item. | `fhir.py`, `docs/governance/model-card-triage.md` | Partly |
| 3.1.4.4.3 | Privacy-enhancing techniques | Relatives are contacted only through choices made by the index person; invitations can name nobody; family members never see each other's results. | `relative_view`, privacy evaluation | Met |
| 3.1.4.5.1 | Compute and storage inside the UAE | Designed for Azure UAE North. The optional language model is off by default and receives redacted message text only. | [deployment notes](../deployment.md) | Deployment |
| 3.1.5.1.1-3 | Representative data; subgroup audits | Population inputs are UAE-national studies. Triage results reported per language variety; weakest group (Gulf Arabic crisis detection) stated. Reports by sex, literacy and age need real users. | `docs/evidence/triage_rules_ngram.json` | Partly |
| 3.1.6.1.1-2 | Tell people when AI contributes; plain language | The interface labels every value as recorded, calculated, quoted source or approved wording. No AI-written text is shown. | web app, `content.py` | Met |
| 3.1.6.1.3 | Right to opt out; consent | Permissions for calculation and for informing relatives are separate, granular and revocable; declining to inform a relative is recorded and ends the process. | `service.set_consent` | Met |
| 3.1.6.2.1-3 | Document data, logic; traceability logs | Parameter register with sources; formulas in code and docs; SHA-256 hash-chained audit log; content hashes per paragraph. | `data/params/loci.yaml`, `store.py` | Met |
| 3.1.6.3.1-3 | Role-specific explanations | Families and relatives see approved sentences; counsellors see the full working (alleles, derivations, sources, limitations). | web app | Met |
| 3.1.7.1.1-3 | Owner; logged, traceable changes | Every invitation has an owner and lifecycle; every change is in the audit log and in version control. Named organisational owner is a deployment item. | `INVITE_FLOW` | Partly |
| 3.1.7.2.1-3 | Clinicians keep authority; override; audit | Counsellors approve, record results and resolve messages; the system never decides. | API tests | Met |
| 3.2.1.3 | Every dataset mapped to a task | Each data file states its single purpose (parameters, content, dev set, test set). | `data/*/README.md` | Met |
| 3.2.1.5 | Open-data licences reviewed | MedlinePlus Genetics public-domain status verified on medlineplus.gov/copyright.html; US-specific paragraphs excluded. Legal review is a deployment item. | `data/content/sources.yaml` | Partly |
| 3.2.2.1-3 | Report dataset limitations and gaps | Excluded conditions (alpha-thalassaemia, CYP1B1) with reasons; per-allele notes on study populations. | `loci.yaml` | Met |
| 3.2.4 | Dataset versioning | Git history; content hashes; model card records training data and date. | repository | Met |
| 3.3.1.1 | Risk register and owners | Hazard log with control owner per hazard. | [hazard log](hazard-log.md) | Met |
| 3.4 | AI literacy | Counsellor-facing "show the working" view; training plan in the pilot protocol. | pilot protocol | Partly |
| 5.1 | Periodic compliance reporting to DoH | Pilot reporting schedule defined. | pilot protocol | Deployment |

## Generative AI note

The Standard has no generative-AI clauses, but the Protocol names hallucination as a threat. Silsila removes
that threat from person-facing output by design: no language model writes text that people see. An outbound
message must match approved content exactly, or the output gate blocks it (demonstrated in the app and
tested in `tests/test_content_triage.py`).
