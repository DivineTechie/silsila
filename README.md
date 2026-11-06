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

## Why this matters

- Testing the extended families of an affected child found 31% of relatives were carriers and 8% of married
  couples were both carriers, versus 0 of 397 people in control families and 0 at-risk couples among 350
  random pregnant couples (Ahmed et al., *NEJM* 2002;347:1162-8, PMID 12374877).
- Abu Dhabi's premarital programme (570 genes) became mandatory for Emiratis in 2024-2025, so couples married
  before then were never screened. It has flagged 565 incompatible couples among 11,748 tested (Gulf News,
  Oct 2026).
- Half of UAE-national marriages were consanguineous in the only national survey (50.5%, al-Gazali 1997,
  PMID 9881148). Beta-thalassaemia carriers vary from 0% to 13.6% between tribes (Denic 2013, PMID 23600619).

## How it works

| Step | What happens |
|---|---|
| 1. Index result | A newborn screen, premarital result or diagnosis is entered (FHIR genomics observation). |
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
| Arabic translations of quoted text, three independent systems compared | Numbers preserved 72/72; cross-system agreement median 0.966; 7 flagged for first clinical review |
| Engine latency, 60-person family with cousin loops | median 173 ms |

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
console, record the result, try the two demonstration tools (blocked unapproved text, audit tampering) and
export FHIR.

Tests and benchmarks:

```bash
cd backend && uv run pytest -q
```

```bash
cd backend && uv run python -m bench.run_all
```

## Repository

| Path | Contents |
|---|---|
| `backend/src/silsila/engine/` | Exact pedigree engine (variable elimination, min-fill ordering, Monte Carlo cross-check) |
| `backend/src/silsila/params.py`, `data/params/` | Sourced parameter register and conversions |
| `backend/src/silsila/content.py`, `data/content/` | Approved content, MedlinePlus imports, Arabic translations, output gate |
| `backend/src/silsila/triage.py`, `data/models/` | Message triage (rules + character n-gram model; optional Azure OpenAI labels) |
| `backend/src/silsila/api/` | FastAPI service: consent, invitations, queue, audit chain, FHIR R4B export |
| `backend/src/silsila/sim/`, `backend/bench/` | Family simulator and benchmarks |
| `web/` | Next.js app: family, relative and counsellor views (Arabic and English, installable) |
| `data/eval/`, `data/dev/` | Held-out triage test set and separate development set |
| `tools/translation_qc/` | Three-system Arabic translation check |
| `docs/` | Evidence, governance, pilot protocol, deployment notes, limitations |

## Governance

- [DoH Responsible AI Standard clause map](docs/governance/doh-rai-clause-map.md): risk class High (3) under
  the DoH AI Risk Management Protocol.
- [Hazard log](docs/governance/hazard-log.md), [triage model card](docs/governance/model-card-triage.md),
  [pilot protocol (DECIDE-AI)](docs/pilot-protocol.md), [deployment notes](docs/deployment.md),
  [assumptions and limitations](docs/limitations.md).

## Data and licences

| Source | Use | Licence |
|---|---|---|
| MedlinePlus Genetics (NLM) | Verbatim patient information | Public domain; credited "Source: MedlinePlus, National Library of Medicine" |
| Published studies (PMIDs in `data/params/loci.yaml`, `data/calibration/`) | Population parameters | Facts cited from the literature |
| Helsinki-NLP opus-mt-tc-big-en-ar | Translation cross-check only | CC-BY 4.0 |
| sentence-transformers/LaBSE | Translation meaning check only | Apache-2.0 |
| Synthetic families, messages and test sets | Demo and evaluation | Generated for this project |

No real patient data is used. All people in the demo are fictional.

## Status

Prototype submitted to the Future Health Digital Innovation Challenge (November 2026). Not a medical device;
not validated with patients. Arabic text awaits native clinical review. See [limitations](docs/limitations.md).
