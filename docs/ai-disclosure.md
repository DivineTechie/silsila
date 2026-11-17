# AI tools disclosure

**AI does not make any decision in Silsila. Risk is computed by an exact, deterministic Bayesian engine; who is
told is decided by the family; every invitation is approved by a genetic counsellor; no AI-written text reaches
a family member.**

This page lists every AI tool used in or for Silsila, where, and what it is not allowed to do. Back to the
[README](../README.md).

## In the product

| Tool | Where | What it does | What it is not allowed to do |
|---|---|---|---|
| Azure AI Speech neural voices (`en-GB-SoniaNeural`, `ar-AE-FatimaNeural`) | `backend/scripts/make_read_aloud.py` makes the clips in `data/content/audio` | Turns approved or quoted text into audio, ahead of time: 74 clips, 33.3 minutes. Every clip is labelled as a synthetic voice | Read any other text: a clip is attached only to the exact text it was made from (SHA-256). Run at request time. No clip has yet been checked by a native listener |
| Jais-ASR (Inception, dialect `AE`) and Jais 3 7B | Voice intake (`backend/src/silsila/intake.py`, [model card](governance/model-card-voice-intake.md)) | Recognises a spoken Emirati Arabic family story and drafts a family tree | Calculate risk. Reach a family. Skip the counsellor, who confirms each person and marriage before the engine runs. The hosted site replays one recorded run; no model runs there |
| Message-triage classifier (scikit-learn, character n-grams) | `backend/src/silsila/triage.py`, `data/models/triage_ngram.joblib`, [model card](governance/model-card-triage.md) | Labels incoming messages (crisis, decision, religious, distress and others) to order the counsellor queue | Write replies. Replace a person: every message is read by a person and every reply carries 998/999. Trained on 800 synthetic messages written by an AI model (Claude), not on real messages |
| Azure OpenAI classifier | `triage.py`; off unless `AZURE_OPENAI_*` are set | Adds labels to message text with numbers and email addresses removed | Write text. Remove labels set by the rules or the n-gram model. Off by default |
| Machine translation for Arabic | `data/content/translations/ar/`, templates, guide | Arabic versions of quoted MedlinePlus paragraphs, templates and guide answers, produced at build time by an AI model (Claude, Anthropic). `tools/translation_qc` compares three systems (Claude, Helsinki-NLP opus-mt-tc-big-en-ar, Azure AI Translator) and checks meaning with LaBSE: numbers preserved 76/76, 7 flagged. The 26 guide answers added on 17 Nov 2026 and a few interface labels were machine-translated with Azure AI Translator instead, with product names corrected by hand | Be treated as clinically reviewed. It has not been reviewed by a native-speaking clinician, and that review is required before any use with patients |

The guide ("Ask about Silsila", `backend/src/silsila/guide.py`) is **not** an AI. It matches the words of a
question to one of 50 fixed answers and, for some, runs a real lookup. It calls no model and no outside service.

## In the evaluation

Silsila-Bench ([`bench_llm/`](../bench_llm/README.md), [pre-registration](../bench_llm/PREREGISTRATION.md))
evaluated these language models against the exact engine: Jais 3 7B, Jais 3 32B (a pre-declared sample),
K2-Think-V2 (started, did not finish in budget, not scored), BiMediX2 8B, Llama3-Med42 8B and gpt-oss-120b as a
frontier reference. They were evaluated only. None is used at run time to compute risk or to write anything.
The result is why no model computes risk in Silsila: models may draft a tree from a story, which a counsellor
confirms. See [`evidence/silsila_bench.md`](evidence/silsila_bench.md).

## In the demo film and deck

The film narration uses Azure AI Speech (`en-US-AvaMultilingualNeural`) and is labelled on screen as a synthetic
voice. The film is recorded from the live site by scripts in [`tools/film`](../tools/film/README.md). The deck is
built by [`tools/submission/build_deck.py`](../tools/submission/build_deck.py).

## Development tools

Claude Code (Anthropic) was used as a coding and writing assistant during development: writing and reviewing
code, tests and documentation, and building the film and deck tooling. Every design decision, clinical rule and
claim was reviewed by the author; all evidence figures come from scripts in this repository.

Claude (Anthropic) was also used to write the synthetic messages used to train and test the triage classifier
and to produce the machine translation of Arabic, as stated in the table above. Both are labelled as such in the
repository (`docs/governance/model-card-triage.md`, `data/content/translations/ar/medlineplus.json`).
