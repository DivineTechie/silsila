# Silsila (سلسلة)

**A consent-led family cascade for inherited disease risk.**
Future Health Digital Innovation Challenge, Fertility, Challenge 03: *Understanding and Reducing Inherited Disease Risk*.

> Premarital screening protects the next marriage. Silsila protects the marriages that already happened.

When one person is found to carry, or to have, a recessive condition (a newborn's genetic screen, an
at-risk premarital result, a diagnosed child), their relatives are much more likely to be carriers too, and
in cousin-marriage families they are often already married to each other. Silsila turns that one result into
private, consent-controlled invitations for the right relatives to be tested, explained in Arabic or English,
checked by a genetic counsellor, and tracked until each case is closed. The person who received the result
decides who is told and how. No name or condition is revealed without their choice.

Prototype with fictional families. Not for clinical use.

## For judges: try it in two minutes

**Live (Azure UAE North):** https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io. No
password is needed: the home page has one-click roles. English and Arabic (button in the header); on a phone
the page links are in the menu.

1. **Watch a cascade** (first button on the home page): one newborn's result travelling through a fictional
   family in 13 live steps: exact risk for every relative, Mariam's permission, an anonymous invitation,
   counsellor approval, the relative's private link and comprehension check, the options before or during a
   pregnancy quoted word for word from MedlinePlus (described, never recommended), booking, a pregnancy
   question routed to a person, the test result closing the case, the output gate blocking AI-written
   advice, and the measures for that run. Beside the family tree: what each person sees, and the
   hash-chained audit entries the step created. Each run uses its own fresh copy of the family, and every
   step follows the language you choose, including a switch mid-run.
2. **Family Twin** (top menu): a fictional, simulated five-generation clan of 61 people in 3D. Click anyone,
   record a test result, and watch every relative's exact carrier chance update across six cousin marriages.
   Measured on the hosted server on 16 Nov: 0.7 s with no extra results, a median of 0.9 s (0.7 to 1.2 s)
   once results are recorded, 1.0 s on the first call after a restart; about 0.12 s on a laptop
   ([record](docs/evidence/twin_hosted_timing.json)). Press "Where did it come from?" to see the most likely
   line of descent, or play the cascade race.
3. **A relative receiving a link** (home page role): the anonymous invitation as a relative sees it. Every
   text has a **Listen** button (a synthetic voice, labelled, reading exactly the approved or quoted text, in
   Arabic or English), then common questions answered in quoted source text, a comprehension check and
   booking.
4. **Mariam** (family): newborn screening found classic CAH in her son. She gives permission and invites her
   pregnant sister Noura anonymously.
5. **Genetic counsellor**: the invitation tops the queue because of the pregnancy. Approve it. In **Cases**,
   import an index result from a FHIR R4B record (load the fictional sample, check it, create the case; then
   change `"final"` to `"preliminary"` and see it refused with the reason). In **Voice intake**, a family
   story in Emirati Arabic becomes a draft tree (Jais-ASR, then Jais 3; a recorded run), the counsellor fixes
   what the checks flag, and only then does the engine calculate. **Outcomes** shows the challenge's
   measures (comprehension, uptake, time to counselling, privacy, equity by language) computed live from
   what you just did. Marriages and reproductive choices are never measured as success. "Reset the demo
   data" is in the audit tab.
6. **Evidence** (top menu): every number with its source, the benchmarks, the announced UAE programmes
   Silsila connects to, and a scenario calculator for programme scale.
7. **Ask about Silsila** (button in the bottom corner of every public page): a guide that answers questions
   about the tool. It is not a language model: it matches your question to one of 24 fixed answers and, for
   most, runs a real lookup and shows the values with their sources (try "What is the chance for a cousin
   with thalassaemia?", "Does AI write what families read?", "Where does it run, and how fast is it?"). It
   says so when it has no answer, and it does not answer personal or medical questions.

**Film (about three minutes, English and Arabic):** a scripted recording of the live site with a synthetic
voiceover, labelled as recorded. The script, narration and build steps are in [`tools/film/`](tools/film/README.md);
the video files are built locally and are not in the repository.

### The six judging criteria: where to look, what was measured, what is not yet shown

| Criterion | Open | Measured | Not yet shown |
|---|---|---|---|
| Health impact and clinical relevance | Watch a cascade: a newborn's result reaches a pregnant sister | In simulation, Silsila's order found 51 at-risk couples per 1,000 tests against 33 unranked for CAH (ratio 1.53, 95% CI 1.29-1.85); all four published yields of the NEJM 2002 family-screening study fall inside the simulated range | No patients. Yields are projections from simulated families; uptake and comprehension need a pilot |
| Technical depth | Family Twin; Evidence | 30,000 of 30,000 probabilities match an independent exact solver; 0 silent failures in 237 malformed inputs; a pre-registered benchmark of five language models on 150 families | Three genes with published UAE data; other conditions are refused, not estimated |
| Working solution and demo quality | Each role on the home page | Every step runs the real service, from consent to closure with evidence; FHIR import and export; 0 accessibility violations on every screen in English and Arabic (axe-core); 197 backend tests | Voice intake on the hosted site replays one recorded run |
| Responsible AI, safety and data governance | Watch a cascade, steps 10 and 12; [hazard log](docs/governance/hazard-log.md); [DoH RAI clause map](docs/governance/doh-rai-clause-map.md) | 0 disclosures in 10,000 unauthorised requests; crisis-message alert sensitivity 0.961 (95% CI 0.890-0.986) with every message read by a person; read-aloud tied to the exact approved text by hash | Arabic is machine translation, not yet reviewed by a native-speaking clinician; no genetic counsellor has reviewed the templates; no clip has been checked by a native listener |
| Scalability and deployment readiness | Evidence: engine latency; [deployment notes](docs/deployment.md) | Running in Azure UAE North on CPU with no language model at run time; median 173 ms for a 60-person family in the benchmark; index results arrive and leave as FHIR R4B | Demo storage is SQLite with one replica; UAE PASS and a managed database come with a pilot |
| Commercial viability and path to pilot | Evidence: announced programmes, scenario calculator; [commercial case](docs/commercial-case.md); [pilot protocol](docs/pilot-protocol.md) | The buyer already produces the index events (565 incompatible couples among 11,748 tested; more than 100 babies identified by newborn screening in the past year; reported figures); 9 practising genetic counsellors in the UAE | No price is validated and no programme has asked for cascade testing; the pilot protocol is a proposal |

## Why this matters

- Testing the extended families of an affected child found 31% of relatives were carriers and 8% of married
  couples were both carriers, versus 0 of 397 people in control families and 0 at-risk couples among 350
  random pregnant couples (Ahmed et al., *NEJM* 2002;347:1162-8, PMID 12374877).
- Abu Dhabi's premarital genetic test (570 genes, 840+ recessive disorders, per the
  [DoH announcement](https://www.doh.gov.ae/en/news/doh-integrates-genetic-testing-as-an-integral-component-of-the-premarital-screening-programme))
  became mandatory for Emiratis in 2024-2025, so couples married before then were never screened. It tested
  11,748 couples from 2022 to July 2026 and found 565 genetically incompatible; the most common conditions
  reported among them included congenital adrenal hyperplasia (the condition in Silsila's demonstration family)
  and thalassaemia (the condition in the Family Twin), and results are exchanged through Malaffi
  ([Gulf News, 3 Oct 2026](https://gulfnews.com/uae/health/abu-dhabi-genetic-screening-flags-565-incompatible-cases-among-couples-1.500697261)).
  The programme is described in the peer-reviewed literature: Al Ameri M, et al. Large-Scale Premarital
  Genetic Screening in the United Arab Emirates. *N Engl J Med* 2026;395(3):306-308,
  [PMID 42456143](https://pubmed.ncbi.nlm.nih.gov/42456143/) (cited from its PubMed record; no figure here
  is taken from it).
- Newborn genomic screening in Abu Dhabi changed the lives of more than 100 babies in the past year,
  according to the DoH chairman
  ([Khaleej Times, 20 Oct 2026](https://www.khaleejtimes.com/uae/abu-dhabi-newborn-genomic-screening-changes-lives-babies)).
  Silsila's demonstration starts from exactly that event: a newborn's result. As a projection, not an observed
  outcome: if 100 index newborns a year each started a cascade for one recessive condition at benchmark B4's
  simulated yields (5 tests per family), Silsila's order would find about 25 at-risk couples (95% interval
  21-31) against 17 unranked for CAH, and 33 (28-37) against 21 for the haemoglobin disorders. The reported
  babies span many conditions, not all recessive, so this shows scale only
  ([`uae_context.json`](docs/evidence/uae_context.json), scenario calculator on the Evidence page).
- The 2026-2031 National Genomics Masterplan (reported 10 Nov 2026) includes personalised genomic reports
  for 900,000 participants through TAMM from December 2026, covering 214 inherited genomic conditions and
  health traits, and nationwide newborn genetic screening (730+ genes, 815+ conditions); the Emirati Genome
  Programme has passed one million participants
  ([The National](https://www.thenationalnews.com/news/uae/2026/11/10/uae-approves-national-genomics-masterplan-to-bring-personalised-medicine-to-all-citizens/)).
  If these reports include carrier findings (the article does not say), every one is a possible index
  result with relatives outside the programme. No announcement of family cascade testing was found, and
  Silsila does not claim DoH has asked for it: it is the step these programmes do not yet describe.
- Half of UAE-national marriages were consanguineous in the only national survey (50.5%, al-Gazali 1997,
  PMID 9881148). Beta-thalassaemia carriers vary from 0% to 13.6% between tribes (Denic 2013, PMID 23600619).

## How it works

| Step | What happens |
|---|---|
| 1. Index result | A newborn screen, premarital result or diagnosis arrives as a FHIR R4B genomics record and is read at counsellor intake: checked first, then confirmed. Names and identifiers in the record are not stored; a record that cannot be read safely is refused with the reason. |
| 2. Family tree and risk | The family enters its tree, including cousin marriages. An exact engine computes every relative's carrier chance and each couple's chance of an affected child. |
| 3. The index person decides | Who is told, and how: a letter they hand over, clinic contact, or an invitation that names no person and no condition. Declining ends the process and is recorded. |
| 4. Counsellor approval | Nothing is sent until a genetic counsellor approves. Pregnancies move to the top of the queue. |
| 5. Relative's view | Only what the index person chose to disclose, sourced information, a comprehension check, and booking. |
| 6. Closure | Each invitation is a case with an owner and closes only with evidence (for example a test result). |

## Design principles

1. **No AI-written advice.** Every sentence a person sees is either quoted word for word from MedlinePlus
   Genetics (US National Library of Medicine, public domain) or an approved procedural template. An output
   gate re-derives each message and blocks anything else. Machine learning only sorts incoming messages, and
   every message is still read by a person.
2. **Nothing made up.** Every population number has a citation with PMID, and conversions are formulas in
   code (`data/params/loci.yaml`). Conditions without published UAE data are deliberately not calculated.
3. **Non-directive.** The system never advises on marriage, pregnancy or termination. Cancelled marriages
   are not a success measure.
4. **Privacy by design.** Granular, revocable consent; relatives see only chosen disclosures; tamper-evident
   audit log; pseudonymous FHIR export; designed for UAE-only hosting.

## Evidence

All evidence is on synthetic data and is reproducible (`docs/evidence/README.md`, per-case logs in
`docs/evidence/logs/`).

| What was tested | Result |
|---|---|
| Engine vs an independent exact solver (pgmpy), 10,000 random consanguineous families | 100% agreement within 1e-9 (30,000 probabilities; max error 5.6e-16) |
| Engine vs textbook values (kinship, Wright's formula, 2/3 sibling risk, residual risk) | 67 / 67 |
| Malformed or impossible inputs | 0 silent failures in 237 (each gets a clear error or counsellor referral) |
| Reproducing NEJM 2002 extended-family yields | All four published figures inside the simulated range |
| At-risk couples found per 1,000 tests (5 tests per family), Silsila ranking vs unranked cascade | HBB 65 vs 41 (ratio 1.58, 95% CI 1.43-1.77); CYP21A2 51 vs 33 (1.53, 1.29-1.85); SMN1 54 vs 35 (1.56, 1.39-1.81) |
| Cascade vs random couple testing | 4.6x (HBB) to about 200x (CYP21A2) more at-risk couples per test |
| Sensitivity to 27 labelled assumptions | Ranking advantage interval above 1 in 16 of 20 settings |
| Crisis messages, blind 400-message test set in English, MSA, Gulf Arabic and Arabizi | Alert sensitivity 0.961 (95% CI 0.890-0.986); 76/76 replies show 998/999; 100% read by a person |
| Unauthorised API requests (14 attack types) | 0 disclosures in 10,000 |
| Arabic translations of quoted text, three independent systems compared | Numbers preserved 76/76; 7 flagged for first clinical review |
| Engine latency, 60-person family with cousin loops | median 173 ms |
| Accessibility, axe-core on every screen (English light desktop, Arabic dark phone) | 0 violations ([record](docs/evidence/accessibility.md)) |
| FHIR import of an index result: 22 kinds of malformed or unsafe record, and each of the sample's 116 fields deleted in turn | 0 crashes and 0 silent failures: each is read, or refused with the reason and audited |
| Readability of the English text a relative can be shown (Flesch-Kincaid grade) | Silsila's own wording 6.9; the quoted MedlinePlus text 13.4, a college reading level, which is why it can be read aloud ([details](docs/evidence/README.md)) |
| Read-aloud clips (synthetic voice, Azure AI Speech), English and Arabic | 74 clips, 33.3 minutes, each attached only to the exact text it reads (SHA-256); none yet checked by a native listener |
| "Ask about Silsila" guide: every listed question in English and Arabic, 28 rewordings, 8 off-topic and 8 personal or urgent questions | Each reaches its answer, an honest "no answer", or a refusal with the counsellor and 998/999 wording; 0 calls to any model or outside service |
| Family Twin recalculation on the hosted server (61 people, six cousin marriages) | 0.7 s with no extra results; median 0.9 s (0.7-1.2 s) with recorded results ([record](docs/evidence/twin_hosted_timing.json)) |

### Silsila-Bench: where language models can be trusted inside Silsila

Pre-registered ([`bench_llm/PREREGISTRATION.md`](bench_llm/PREREGISTRATION.md), changes in
[`AMENDMENTS.md`](bench_llm/AMENDMENTS.md)); 150 synthetic families, gold answers from the exact engine; models
in a fixed order, not a ranking; 95% intervals from a bootstrap over families. Jais 3 32B was run on a
pre-declared 350-prompt sample (A10); K2-Think-V2 was not run (two-GPU cost).

| Model | Free text: exact, of answers given | Free text: no number | With the engine as a tool: exact | Story to tree: links found |
|---|---|---|---|---|
| Jais 3 7B | 59.4% (54-65) | 43.4% | 70.8% (67-75) | 90.9% (88-94) |
| Jais 3 32B (sample) | 95.8% (90-100) | 52.0% | 98.0% (95-100) | 92.5% (87-97) |
| BiMediX2 8B | 5.0% (3-7) | 20.7% | 0.0% | 0.8% |
| Llama3-Med42 8B | 8.4% (6-10) | 0.2% | 3.6% (2-5) | 51.8% (48-55) |
| gpt-oss-120b (frontier reference) | 33.7% (30-38) | 0.0% | 34.4% (29-39) | 91.5% (89-94) |

Every cited PubMed ID was checked: in every model's answers that cited PMIDs, at least one citation did not
support the claim, and 95-100% of the cited IDs that exist belong to unrelated papers
([review](bench_llm/T5_REVIEW.md)). What this decides: no model computes risk in Silsila; models may draft a
family tree from a story, which a counsellor confirms before the exact engine runs. Full tables, splits by
language and family type: [`docs/evidence/silsila_bench.md`](docs/evidence/silsila_bench.md).

## Try it

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+.

```bash
cd backend
cp .env.example .env            # demo test passwords for the fictional families are in this file
uv sync
uv run python -m silsila.api.seed
uv run uvicorn silsila.api.app:app --port 8000
```

```bash
cd web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000. Demo users: `mariam` (family, newborn with CAH), `reem` (family, Arabic) and
`counsellor`. Passwords are in `backend/.env.example`.

Suggested walkthrough: sign in as `mariam`, open the family tree, give permission to inform relatives, invite
Noura anonymously; sign in as `counsellor`, see the pregnancy at the top of the queue, approve; open the
invitation link as the relative (switch to Arabic), complete the comprehension check and book; back in the
console, record the result, try the two demonstration tools (blocked unapproved text, audit tampering),
export FHIR, and import the fictional index result in the Cases tab.

Tests and benchmarks:

```bash
cd backend && uv run pytest -q
```

```bash
cd backend && uv run python -m bench.run_all
```

```bash
cd web && npx next typegen && npx tsc --noEmit && npm run lint && npm run build
```

## Run with Docker or deploy

```bash
docker compose up --build        # web on http://localhost:3100, API on http://localhost:8100
```

Azure (UAE North, Azure Container Apps; images are built in Azure Container Registry):

```bash
az login
bash deploy/azure-deploy.sh      # prints the public web and API URLs
```

## Repository

| Path | Contents |
|---|---|
| `backend/src/silsila/engine/` | Exact pedigree engine (variable elimination, min-fill ordering, Monte Carlo cross-check) |
| `backend/src/silsila/params.py`, `data/params/` | Sourced parameter register and conversions |
| `backend/src/silsila/content.py`, `data/content/` | Approved content, MedlinePlus imports, Arabic translations, output gate |
| `backend/src/silsila/triage.py`, `data/models/` | Message triage (rules + character n-gram model; optional Azure OpenAI labels) |
| `backend/src/silsila/guide.py`, `data/guide/` | "Ask about Silsila": fixed answers and live lookups about the tool; no language model |
| `backend/src/silsila/api/` | FastAPI service: consent, invitations, queue, audit chain, FHIR R4B import and export |
| `backend/src/silsila/sim/`, `backend/bench/` | Family simulator and benchmarks |
| `web/` | Next.js app: family, relative and counsellor views (Arabic and English, installable) |
| `data/eval/`, `data/dev/` | Held-out triage test set and separate development set |
| `tools/translation_qc/` | Three-system Arabic translation check |
| `tools/film/` | Narration, recording script and build steps for the demo film |
| `backend/scripts/` | MedlinePlus import, read-aloud clip generator, readability scoring |
| `docs/` | Evidence, governance, pilot protocol, deployment notes, limitations |

## Governance

- [DoH Responsible AI Standard clause map](docs/governance/doh-rai-clause-map.md): risk class High (3) under
  the DoH AI Risk Management Protocol.
- [Commercial case and path to pilot](docs/commercial-case.md): buyer, value, pricing model, costs, risks.
- [Accessibility audit](docs/evidence/accessibility.md): axe-core, every screen, English and Arabic, 0 violations.
- [Hazard log](docs/governance/hazard-log.md), [triage model card](docs/governance/model-card-triage.md),
  [voice-intake model card](docs/governance/model-card-voice-intake.md),
  [pilot protocol (DECIDE-AI)](docs/pilot-protocol.md), [deployment notes](docs/deployment.md),
  [assumptions and limitations](docs/limitations.md).

## Data and licences

| Source | Use | Licence |
|---|---|---|
| MedlinePlus Genetics (NLM) | Verbatim patient information | Public domain; credited "Source: MedlinePlus, National Library of Medicine" |
| Azure AI Speech neural voices (`en-GB-SoniaNeural`, `ar-AE-FatimaNeural`; film: `en-GB-RyanNeural`, `ar-AE-HamdanNeural`) | Read-aloud clips, the voice-intake demo clip and the film narration; always labelled synthetic | Generated with the team's own Azure subscription |
| Published studies (PMIDs in `data/params/loci.yaml`, `data/calibration/`) | Population parameters | Facts cited from the literature |
| Helsinki-NLP opus-mt-tc-big-en-ar | Translation cross-check only | CC-BY 4.0 |
| sentence-transformers/LaBSE | Translation meaning check only | Apache-2.0 |
| Synthetic families, messages and test sets | Demo and evaluation | Generated for this project |

No real patient data is used. All people in the demo are fictional.

## Status

Prototype submitted to the Future Health Digital Innovation Challenge (November 2026). Not a medical device;
not validated with patients. Arabic text awaits native clinical review, and the read-aloud clips a native
listener. See [limitations](docs/limitations.md).
