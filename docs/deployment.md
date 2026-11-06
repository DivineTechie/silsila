# Deployment notes

**Hosting.** Two containers (API, web) in Azure UAE North, for example on Azure Container Apps, so compute
and storage stay in the UAE (DoH Responsible AI Standard 3.1.4.5.1). SQLite is used for the prototype;
a pilot would use a managed database in the same region with encryption at rest.

**Identity.** Demo accounts with scrypt-hashed passwords and signed tokens. A pilot would use UAE PASS for
families and the provider's identity system (with MFA) for counsellors.

**Optional language model.** Off by default. If enabled, set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`
and `AZURE_OPENAI_DEPLOYMENT` to a deployment in a UAE region. It receives message text with numbers and
email addresses removed, returns labels only, and cannot remove labels set by the rules or n-gram model.

**Interoperability.** Cases export as FHIR R4B Bundles (Patient, FamilyMemberHistory, Observation with LOINC
69548-6 and HGNC gene codes, RiskAssessment, Consent, Task, AuditEvent). Malaffi exchanges HL7 v2 feeds
today; a pilot would map the Observation and Task content to those feeds through the provider's integration
engine rather than connect directly.

**Configuration.** See `backend/.env.example`. `SILSILA_DEMO=0` disables the demonstration endpoints
(audit tampering and output-gate injection).
