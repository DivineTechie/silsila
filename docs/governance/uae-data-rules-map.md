# UAE data rules: map to the prototype

This is the development team's reading of public sources, not a legal assessment. No lawyer or compliance
officer has reviewed it, and a pilot needs a formal assessment with the Department of Health (DoH).

Only one primary text could be opened (the genome law). The others are read as summarised by the law firms and
government pages linked in [Sources](#sources); each row says which. Article numbers for those rows are the
summaries' numbers, not checked against the statute. "Maps to" means the prototype has a feature on the same
subject; it is not a finding that a rule is met.

"What the prototype does today" is taken only from the repository documents: the README,
[limitations](../limitations.md), [deployment notes](../deployment.md), the [hazard log](hazard-log.md), the
[pilot protocol](../pilot-protocol.md) and the [DoH AI clause map](doh-rai-clause-map.md). All data are fictional.

| Rule (source) | What it asks for, as the source states it | What the prototype does today | Gap, and when it would be closed |
|---|---|---|---|
| Federal Law by Decree No. 49 of 2023, Regulating the Use of the Human Genome, Art. 25(1) and Art. 3(3) ([official text, DHA copy](https://dha.gov.ae/uploads/062024/Federal%20Law_49_2023_Regulating%20the%20Use%20of%20the%20Human%20Genome202466484.pdf)). Primary text opened. | "All Genomic or Genetic Data in the State shall be completely maintained confidential and shall not be circulated or disclosed except in cases permitted by the legislation in force." | Relatives see only what the index person chose to disclose; role checks and unguessable links; 0 disclosures in 10,000 unauthorised requests in a synthetic test; the FHIR import does not store names or identifiers. Maps to this rule. Whether a disclosure to relatives is a "case permitted by the legislation" is not assessed. | Legal reading of the relative-notification step: before pilot. |
| Same law, Art. 4, 6 and 8 (consent to genetic screening; written, explicit consent on a Health Authority form; right to withdraw). | Screening needs consent given in writing "pursuant to the form approved by the Health Authority"; a person may withdraw "at any stage". | The prototype does not perform screening. Its own permissions (to calculate, to inform relatives) are separate and can be withdrawn; declining ends the process and is recorded. These are in-app permissions, not the Art. 6 form. | Whether the clinic's consent form covers the cascade, and whether the app's permissions need a DoH-approved form: before pilot. |
| Same law, Art. 28 (licensing) and Art. 26 (National Genomic Database). | No facility may provide services related to genes, "storage, preservation and transfer of ... Genomic or Genetic Data" without a Health Authority licence. Parties carrying out screening must give genetic data to the National Genomic Database. | Not addressed in the repository. The prototype stores an imported index result (gene, allelic state, significance) without name or identifier. | Whether a deploying provider's licence covers the service, and whether Art. 26 applies: before pilot, with DoH. |
| Federal Law No. 2 of 2019, ICT in Health Fields. Confidentiality and integrity of health data (Art. 4 per [Latham & Watkins](https://lw.com/thoughtLeadership/lw-new-uae-law-regulates-healthcare-data); the [u.ae portal](https://u.ae/en/about-the-uae/digital-uae/whole-of-government-approach/digital-health/ict-in-the-health-sector) states the duty without article numbers). Secondary and portal summaries only; statute not opened. | Keep health data confidential, protect it from "unauthorised amendment, alteration, deletion", and keep it available to authorised parties. | Hash-chained audit log (altering a record shows as the first broken event); role checks; every access and refusal logged. Encryption at rest is not in the prototype (SQLite, one replica). | Encryption at rest and a managed database: before pilot. |
| Same law, Art. 13 (data stays in the UAE), as summarised by [Latham & Watkins](https://lw.com/thoughtLeadership/lw-new-uae-law-regulates-healthcare-data) and [BSA](https://bsalaw.com/insight/the-new-uae-health-data-law-an-in-depth-look/); exceptions in Ministerial Decision 51/2021 as summarised by [CMS](https://cms.law/en/are/legal-updates/uae-health-data-new-data-transfer-permissions). | Health data for services provided in the UAE may not be stored, processed, generated or transferred outside the UAE unless approved by a health-authority decision. | Hosted in Azure UAE North. The optional language model is off by default and, if enabled, would be a UAE-region deployment receiving redacted text only. Consistent with this rule for hosting. Hosting of the benchmark and film tooling was not reviewed; those use synthetic data. | Confirm every processing location, including any model endpoint, for the real deployment: before pilot. |
| Same law, Art. 20 (retention), as summarised by [Latham & Watkins](https://lw.com/thoughtLeadership/lw-new-uae-law-regulates-healthcare-data). | Health data kept for at least 25 years from the last procedure, longer if needed. | No data-retention schedule exists in the repository. The "Reset the demo data" function deletes fictional data. | Retention and deletion schedule, reconciled with the withdrawal rights above: before pilot. |
| Same law, Art. 16 (purpose limitation), as summarised by [Latham & Watkins](https://lw.com/thoughtLeadership/lw-new-uae-law-regulates-healthcare-data) and [CMS](https://cms.law/en/are/legal-updates/uae-health-data-new-data-transfer-permissions). | Data may not be used for non-health purposes except in listed cases, such as the patient's written consent. | No matchmaking, registry or advertising feature (hazard H13); the engine needs only sex, parent links, results and pregnancy status. Maps to this rule. | Review of any secondary use (research, programme statistics): during pilot. |
| Federal Decree-Law No. 45 of 2021 (PDPL), as summarised by [Clyde & Co](https://www.clydeco.com/en/insights/2021/11/uae-issues-landmark-personal-data-protection-law). Secondary only; the official portal returned an access block. | The law does not apply to health personal data regulated by the 2019 ICT law. For other personal data it requires specific, clear consent, gives rights of access, correction, erasure, restriction and objection, and requires breach reports to the UAE Data Office. | Consent is granular and revocable. No data-subject-request or breach-notification procedure is documented. Whether any Silsila data falls outside the health-data exclusion (for example staff or sign-in data) is not assessed. | Scope decision, rights-request and breach procedures: before pilot. |
| Abu Dhabi Healthcare Information and Cyber Security Standard (ADHICS), as summarised by [K7 Computing](https://blog.k7computing.com/adhics-compliance-for-smaller-healthcare-organisations/). Secondary only; DoH documents could not be opened. | Applies to healthcare entities in Abu Dhabi; 11 domains including access control, third-party security and incident management; periodic risk assessment, yearly audit and penetration testing. | Maps to access control, logging and risk register (the hazard log). No formal ADHICS assessment; no UAE PASS; no MFA for staff; no penetration test. The same summary says a cloud ban applied under the 2019 text; the team could not check this against the current version, so how it affects Azure hosting is not verified. | Formal ADHICS assessment by the deploying entity, current version confirmed with DoH: before pilot. |

## Not done

- No legal review of any row above. No compliance officer or DoH contact has seen this map.
- Primary texts of the 2019 ICT law, the PDPL, Ministerial Decision 51/2021 and ADHICS were not opened; the
  official portals refused or dropped the connection. Article numbers and summaries need checking against them.
- Not verified: the current ADHICS version and whether its cloud provisions permit the Azure UAE North setup.
- Not verified: any DoH genomics or precision-medicine policy text. A DoH news item says pharmacogenomic
  reports are available to Abu Dhabi physicians through Malaffi ([Abu Dhabi Media Office](https://www.mediaoffice.abudhabi/en/health/department-of-health-abu-dhabi-advances-precision-medicine-for-alzheimers-disease-through-pharmacogenomics-reports/)),
  but the policy itself and its consent rules were not read.
- Malaffi: its public page describes a health information exchange connecting Abu Dhabi providers
  ([Malaffi](https://www.malaffi.ae/)). No Malaffi connection rules or profile were found; Silsila does not
  connect to it.
- Not built: UAE PASS, MFA, encryption at rest, a retention schedule, data-subject-request and breach procedures.
- Not assessed: cross-border transfer rules for any benchmark or demonstration tooling, and the Dubai
  Healthcare City or other free-zone regimes, which do not apply to an Abu Dhabi pilot as the team understands it.

## Sources

All read on 17 Nov 2026.

- Federal Law by Decree No. 49 of 2023 (official text, DHA copy): https://dha.gov.ae/uploads/062024/Federal%20Law_49_2023_Regulating%20the%20Use%20of%20the%20Human%20Genome202466484.pdf
- u.ae, ICT in the health sector: https://u.ae/en/about-the-uae/digital-uae/whole-of-government-approach/digital-health/ict-in-the-health-sector
- Latham & Watkins, "New UAE Law Regulates Healthcare Data" (19 June 2019): https://lw.com/thoughtLeadership/lw-new-uae-law-regulates-healthcare-data
- BSA, "The new UAE health data law: an in-depth look": https://bsalaw.com/insight/the-new-uae-health-data-law-an-in-depth-look/
- CMS, "UAE health data: new data transfer permissions" (22 June 2021): https://cms.law/en/are/legal-updates/uae-health-data-new-data-transfer-permissions
- Clyde & Co, "UAE issues landmark personal data protection law" (Nov 2021): https://www.clydeco.com/en/insights/2021/11/uae-issues-landmark-personal-data-protection-law
- K7 Computing, "ADHICS compliance for smaller healthcare organisations": https://blog.k7computing.com/adhics-compliance-for-smaller-healthcare-organisations/
- Malaffi: https://www.malaffi.ae/
- Abu Dhabi Media Office, pharmacogenomics reports: https://www.mediaoffice.abudhabi/en/health/department-of-health-abu-dhabi-advances-precision-medicine-for-alzheimers-disease-through-pharmacogenomics-reports/
