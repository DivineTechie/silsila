# Commercial case and path to pilot

Every number has a source or is labelled as an assumption. Prices are proposals to test in the pilot, not quotes.

## The problem, in numbers

| Fact | Value | Source |
|---|---|---|
| Emirati births in Abu Dhabi, 2024 | 15,628 (of 39,333 total) | DoH and Statistics Centre Abu Dhabi, via [Gulf Today, Aug 2025](https://www.gulftoday.ae/lifestyle/2025/08/03/abu-dhabi-recorded-15628-emirati-births-in-2024) |
| Births with a haemoglobin disorder (sickle cell disease, beta-thalassaemia major) implied by Silsila's sourced parameters, before any screening effect | about 38 a year in Abu Dhabi | `data/params/loci.yaml` (Belhoul 2013 carrier rates, background inbreeding F = 0.0222); model figure, not an observed count |
| Practising genetic counsellors in the UAE | 9 (plus 8 clinical geneticists) for nearly 11 million people | [Almarri et al., J Genet Couns 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12619030/) |
| Direct cost of transfusion-dependent beta-thalassaemia | about USD 28,100 per patient-year (Saudi tertiary centre, 2018-2022; no UAE study found) | [Medicine 2025, PMC12237305](https://pmc.ncbi.nlm.nih.gov/articles/PMC12237305/) |
| Couples flagged at risk by Abu Dhabi premarital screening | 565 among 11,748 tested (2022 to Jul 2026) | [Gulf News, Oct 2026](https://gulfnews.com/uae/health/abu-dhabi-genetic-screening-flags-565-incompatible-cases-among-couples-1.500697261) |
| Conditions most often found among those couples | include congenital adrenal hyperplasia and thalassaemia (Silsila's two demonstration conditions); results exchanged through Malaffi | same Gulf News report |
| Babies identified by newborn genomic screening in Abu Dhabi | more than 100 in the past year (DoH chairman, 20 Oct 2026) | [Khaleej Times](https://www.khaleejtimes.com/uae/abu-dhabi-newborn-genomic-screening-changes-lives-babies) |
| Personalised genomic reports planned under the 2026-2031 National Genomics Masterplan | 900,000 participants, through TAMM from December 2026, 214 inherited conditions and health traits; newborn genetic screening to expand nationwide | [The National, 10 Nov 2026](https://www.thenationalnews.com/news/uae/2026/11/10/uae-approves-national-genomics-masterplan-to-bring-personalised-medicine-to-all-citizens/) |
| Relatives of an affected child who are carriers | 31% (vs 0 of 397 in control families); 8% of married relative couples both carriers | Ahmed et al., NEJM 2002, PMID 12374877 |

Every flagged couple and every affected newborn starts a family cascade that today depends on a handful of
specialists drawing family trees by hand.

**Volume the announced programmes imply (projection, not an observed outcome).** At about 100 index newborns a
year, a cascade of 5 tests per family is 500 tests. At benchmark B4's simulated yields for one recessive
condition, that finds about 25 at-risk couples in Silsila's order (95% interval 21-31) against 17 unranked for
CAH, and 33 (28-37) against 21 for the haemoglobin disorders. The reported babies span many conditions, not all
recessive, so the real number of cascades would be lower. If the TAMM genomic reports include carrier findings
(the article does not say), the number of possible index results is far larger, and the limiting resource is
counsellor time, which is what Silsila is priced against. No announcement of cascade testing was found;
Silsila does not claim DoH has asked for it. Sources and arithmetic:
[`docs/evidence/uae_context.json`](evidence/uae_context.json).

## What Silsila sells

A consent and cascade layer for programmes that already find index cases. It does not hold genomes and does
not replace counsellors; it gives each counsellor:

1. **The right relatives first.** Exact carrier and couple probabilities for every relative across cousin
   loops, and a ranked invitation list. In simulation (benchmark B4) the ranked cascade found 1.58× as many
   at-risk couples per test as an unranked family cascade (95% CI 1.43-1.77), and 4.6× (HBB) to about 200×
   (CYP21A2) as many as testing random couples.
2. **Less hand work per family.** A family tree drafted from the family's own spoken story (counsellor
   confirms), a work queue ordered by urgency (pregnancy first), approved wording in Arabic and English, and
   closure only with evidence.
3. **Consent and privacy the regulator can audit.** Separate permissions for calculation and for informing
   relatives, anonymous invitations, a hash-chained audit log, FHIR R4B export, DoH RAI clause map.

## Who buys and who pays

| Role | Organisation (Abu Dhabi) | Why |
|---|---|---|
| Programme owner and buyer | Department of Health (premarital and newborn genomic screening programmes) | Owns the index events and the outcome measures; Silsila reports exactly those measures |
| Operator | The genetics service the programmes refer to (for example SEHA / PureHealth genetics clinics) | Counsellor time is the bottleneck Silsila relieves |
| Data partner | Emirati Genome Programme / M42 | Index events from genomic reports; Silsila covers the unsequenced relatives and in-laws |
| Payer for confirmatory tests | Thiqa / Daman (existing benefit) | Fewer tests per at-risk couple found |
| Entry points | TAMM, Sahatna, UAE PASS, Malaffi (FHIR) | Families reach Silsila where they already are |

## Pricing model (proposal, to be validated in the pilot)

- **Pilot:** fixed fee for six months, one screening centre and its genetics clinic, up to 200 index
  families, including hosting in Azure UAE North, integration work and monthly DoH reports.
- **At scale:** an annual programme licence priced per index family started (all relatives in that family
  included), with a floor for platform operation. Per-family pricing keeps cost proportional to the
  programme's own volume and needs no per-relative billing.
- **Hosting cost (assumption, list prices):** the current deployment (API 2 vCPU / 4 GiB, web 0.5 vCPU /
  1 GiB on Azure Container Apps, UAE North, always on) comes to about USD 200 a month at list consumption
  prices (our estimate from per-second vCPU and memory rates; free monthly grants not counted); the exact
  engine runs on CPU, so cost grows with families, not with model tokens. No language model is needed at
  run time; voice intake is an optional module that runs on a clinic workstation.

## Path to pilot

Detailed in [pilot-protocol.md](pilot-protocol.md). In short:

1. **Shadow mode (months 1-2).** Counsellors run their usual process; Silsila computes alongside. Measure
   agreement on whom to contact first and the time saved per family. Nothing is sent to relatives.
2. **Assisted mode (months 3-6).** Invitations go out through Silsila with counsellor approval.
3. **Measures** (from the challenge statement): comprehension (teach-back), counselling uptake, time from
   index result to counselling, at-risk couples identified per test, privacy incidents, equity across
   Arabic, English and literacy levels. **Never** cancelled marriages or any particular reproductive choice.
4. **Exit criteria:** zero unauthorised disclosures; non-inferior comprehension in Arabic; counsellor time
   per family lower than baseline; DoH conformity assessment passed (high-risk asset, Protocol 3.3).

## Regulation and readiness

- **Maturity:** working prototype with fictional data, deployed in UAE North; not yet used with patients.
- **Regulatory:** the engine informs who is offered testing and keeps decisions with counsellors, which
  places it near clinical decision support with full human oversight (DoH AI Risk Protocol, criticality 3).
  Conformity assessment with DDGO before patient use; medical-device classification to be confirmed with DoH.
- **Still needed before patients:** native Arabic clinical review of all wording, genetic-counsellor review of
  templates and queue rules, usability sessions, penetration test, UAE PASS sign-in.

## Why Silsila and not a larger vendor

- **Exact family-wide inference**, not couple arithmetic: every relative's probability across cousin loops,
  validated against an independent solver (30,000 of 30,000 values agree).
- **Vendor-neutral and model-free at run time:** works with whichever genomic provider produced the index
  result, and needs no language model to operate.
- **Built for the people the programmes cannot reach yet:** married couples, unsequenced relatives and
  in-laws from outside the programme.

## Risks to the business case

| Risk | Mitigation |
|---|---|
| Programmes build cascade features themselves | Silsila is a thin, standards-based layer (FHIR, UAE PASS) that can be licensed or transferred; the evidence and governance work is the asset |
| Counsellors do not adopt it | Shadow-mode phase measures time saved before any change in practice |
| Cultural harm (blame, pressure) | Anonymous invitations, decline option, non-directive wording, counsellor contact; tracked in the hazard log |
| Population parameters do not fit a tribe or family | Parameters shown with sources; tribe structure tested in sensitivity analysis (B5); counsellor can override |
