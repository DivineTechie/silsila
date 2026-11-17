# What exists today, and what Silsila adds

A family or a programme that finds a recessive or inherited condition already has options. This page compares
them with Silsila, using published evidence only. Silsila is a prototype on fictional families; most of the
options below are in clinical use. Figures are from the sources listed at the end, read on 17 Nov 2026. The
published figures come mostly from hereditary cancer and familial hypercholesterolaemia (FH), not from the
recessive conditions Silsila calculates, and no study of cascade contact in the UAE was found.

## 1. The family letter (patient-mediated contact)

**What it does.** The person with the result is asked to tell relatives, often with a letter from the clinic.
A 2022 systematic review of hereditary cancer calls this "the current standard" (Frey et al.).
**Reach.** In that review of 87 studies, 40% of first-degree relatives tested after patient-mediated contact
and 35% had genetic counselling. A separate review found that 70% of at-risk relatives were told, and 43% of
those told were tested (Ahsan et al., 2023).
**Compared with Silsila.** It costs nothing and needs no software. It gives the family no order of whom to
tell first, calculates nothing, has no counsellor check and cannot show that anyone acted. Silsila adds
the calculation, the counsellor's queue and closure.

## 2. Contact of relatives by the genetics service

**What it does.** The clinic or laboratory writes to, or telephones, relatives directly, usually with the
index person's agreement.
**Reach.** In the hereditary cancer review, direct contact reached 62% testing in first-degree relatives
against 40% by patient-mediated contact, and 63% against 35% for counselling. By method: telephone 61%,
letter 48%, email 48%. The authors call for randomised trials to confirm this. For FH, a review of 24
studies, none comparing strategies head to head, found limited evidence and that a combination in which the
index person chooses the method gave the best yields (Leonardi-Bee et al., 2021).
**Compared with Silsila.** This is the best-evidenced approach and Silsila does not replace it: Silsila's
counsellor-approved invitation is a form of it. What Silsila adds is the exact ranking and the index
person's control over who is told. What Silsila lacks is any measured uptake; its yields are simulated.

## 3. Digital tools for cascade communication

**What they do.** The index person shares a web tool or chatbot with relatives, which gives education and
access to testing.
**Reach.**
- GIFT, a cluster-randomised trial of an online tool with home testing, USA: 414 patients enrolled and
  invited 19.2% of their 4,946 relatives; 303 relatives enrolled and 267 were tested. A human navigator did
  not increase testing (Katz et al., *J Clin Oncol* 2026).
- A cascade chatbot at one gynaecological oncology clinic, USA (a quality improvement study with no control
  group, 100 probands): 122 relatives received it; of 96 reached at three months, 49 (51.0%) had booked or
  completed a genetics appointment (Davis Rivera et al., *JCO Clin Cancer Inform* 2026).
- A UCLA project describes a chatbot prototype and reports no results.
**Compared with Silsila.** These are tested with real people, which Silsila is not. They rely on the
patient to forward the tool, and neither source describes calculated risk for each relative, counsellor
approval of each message or a closure rule. Silsila does not use a chatbot to talk to families.

## 4. Pedigree and risk software in clinics

**What it does.** CanRisk (BOADICEA and related models) lets healthcare professionals enter a family history
and estimate breast, ovarian and prostate cancer risk and mutation carrier probabilities. A 2026 public
version, MyCanRisk, lets women record family history before an appointment without producing a risk estimate.
**Reach.** The CanRisk page says nothing about contacting relatives. MyCanRisk's evaluation (51 women) measured
agreement with a clinical interview, not reach.
**Compared with Silsila.** CanRisk is validated and in clinical use, for dominant cancer genes. Silsila
calculates recessive carrier chances across cousin marriages and adds consent, invitations and closure, but
has no clinical validation.

## 5. Expanded carrier screening of couples

**What it does.** A couple planning or in pregnancy is tested for many recessive conditions at once; the ACMG
practice resource (2021) recommends offering it to all individuals during pregnancy or preconception.
**Reach.** The ACMG abstract describes the couple's own reproductive decisions as its measure of benefit and
does not give a figure for relatives; none was found.
**Compared with Silsila.** It tests more genes than Silsila, which covers three. It protects the couple
tested, not their relatives or marriages already made.

## 6. UAE premarital and newborn screening

Abu Dhabi tested 11,748 couples and found 565 incompatible; newborn screening identified more than 100 babies
in a year (sources in the README). These programmes create the index events. No published description of a
step that reaches the relatives of those couples or babies was found, and Silsila does not claim that DoH has
asked for one.

## Where Silsila is weaker

- No patients, no measured uptake, no clinical validation. Its yields are simulated.
- Three genes only; the others are refused, not estimated.
- Arabic text is machine translation without clinical review, and no genetic counsellor has reviewed the
  templates.
- Demo-grade storage, one replica, no UAE PASS or managed database.
- The options above have published trials, some randomised; Silsila's evidence is its own benchmarks.
- Direct contact (section 2) has the strongest published evidence of higher uptake. Silsila contacts a
  relative only after the index person agrees, and how much uptake that costs or gains has not been measured.
  It also depends on counsellor time, which the UAE has little of (nine practising counsellors).

## Sources (all read 17 Nov 2026)

1. Frey MK et al. Cascade testing for hereditary cancer syndromes: should we move toward direct relative contact? *J Clin Oncol* 2022. https://doi.org/10.1200/jco.22.00303 (abstract via Europe PMC, https://europepmc.org/article/MED/35960887)
2. Ahsan MD et al. Do people with hereditary cancer syndromes inform their at-risk relatives? *PEC Innovation* 2023;2:100138. https://pmc.ncbi.nlm.nih.gov/articles/PMC10194207/
3. Leonardi-Bee J et al. Effectiveness of cascade testing strategies in relatives for familial hypercholesterolemia. *Atherosclerosis* 2021. https://doi.org/10.1016/j.atherosclerosis.2021.09.014 (abstract via Europe PMC, https://europepmc.org/article/MED/34753031)
4. Katz SJ et al. Results from the Genetic Information and Family Testing Study: a cluster-randomized trial. *J Clin Oncol* 2026. https://doi.org/10.1200/jco-25-02196 (abstract via https://europepmc.org/article/MED/41875376)
5. Davis Rivera LB et al. Cascade chatbot. *JCO Clin Cancer Inform* 2026. https://doi.org/10.1200/cci-25-00321 (abstract via https://europepmc.org/article/MED/41802247)
6. UCLA Medical & Imaging Informatics, Chatbots for cascade screening. https://mii.ucla.edu/projects/chatbots-for-cascade-screening
7. CanRisk. https://www.canrisk.org/
8. Wilson C et al. Towards a public-facing version of the CanRisk tool: MyCanRisk. *Cancer Prev Res* 2026. https://doi.org/10.1158/1940-6207.capr-26-0084 (abstract via https://europepmc.org/article/MED/42975085)
9. Gregg AR et al. Screening for autosomal recessive and X-linked conditions during pregnancy and preconception: an ACMG practice resource. *Genet Med* 2021. https://doi.org/10.1038/s41436-021-01203-z (abstract via https://europepmc.org/article/MED/34285390)
10. UAE figures: Gulf News, 3 Oct 2026, https://gulfnews.com/uae/health/abu-dhabi-genetic-screening-flags-565-incompatible-cases-among-couples-1.500697261 ; Khaleej Times, 20 Oct 2026, https://www.khaleejtimes.com/uae/abu-dhabi-newborn-genomic-screening-changes-lives-babies
11. Almarri et al., *J Genet Couns* 2025 (nine practising counsellors). https://pmc.ncbi.nlm.nih.gov/articles/PMC12619030/
