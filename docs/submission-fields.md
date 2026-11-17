# Submission form: text for each field

Prepared 16 Nov 2026. Character counts are checked against the form's limits. Fields marked OWNER need a
decision or a fact only the entrant can give.

| Field | What to enter |
|---|---|
| First dropdown (problem statement or track) | Fertility, Challenge 03: Understanding and Reducing Inherited Disease Risk |
| Solution stage | The option closest to "working prototype, deployed, not yet piloted with users". Do not choose anything that implies real users or a pilot: nothing has been used with patients. |
| Technology type | Software application; Machine learning. (Machine learning: the message-triage classifier and the speech and language models that draft a family tree. Not "AI agent": no model acts on its own or writes to a family.) |
| Prototype / Deployment Link | https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io |
| Upload your solution deck | `submission/Silsila_solution_deck.pdf` (the organisers' template, 16 pages, under 5 MB) |
| Conflict of interest | "None. No member of our team has a conflict of interest to declare." (confirmed by the entrant, 16 Nov 2026) |
| Software-based, hardware-based, or both | Software |
| Demo video link | https://youtu.be/fCHWTlGyeSY (unlisted YouTube upload of `submission/silsila-demo-film.mp4`; 5 min 9 s, English; the film labels itself as recorded, fictional and synthetic voice) |
| Source code | https://github.com/DivineTechie/silsila (Apache-2.0; the submission pack is the latest release) |

## Solution summary (1823 of 2,000 characters)

```
Premarital screening protects the next marriage. Silsila protects the marriages that already happened.

When a newborn screen, a premarital test or a diagnosis finds a recessive condition, the relatives are far more likely to be carriers too, and in families where cousins marry they are often already married to each other. Abu Dhabi's programmes find the first person; nothing announced so far reaches the family.

Silsila is a consent-led family cascade. An exact Bayesian engine computes every relative's carrier chance across cousin-marriage loops and ranks whom to tell first. The person with the result decides who is told and how, including an invitation that names no person and no condition. A genetic counsellor approves every invitation. The relative opens a private link in Arabic or English with approved wording and word-for-word MedlinePlus text (which can be read aloud), a comprehension check, the options before or during a pregnancy described and never recommended, and one-tap booking. The case closes only with evidence, and every action is on a hash-chained audit log.

The defining rule: no language model writes anything a family reads, and none computes risk. We measured why, pre-registered, on the co-creators' own models: Jais 3 7B gave an exact number in 59.4% of its free-text answers. Models only draft a family tree from a spoken Emirati story, which a counsellor confirms.

Evidence, all on synthetic families: 30,000 of 30,000 probabilities match an independent solver; Silsila's order found 1.58 times as many at-risk couples per test as an unranked cascade (95% CI 1.43-1.77); 0 disclosures in 10,000 unauthorised requests; 0 accessibility violations in English and Arabic.

Live in Azure UAE North, no password. Not yet used with patients; Arabic wording awaits native clinical review.
```

## What has been built during the challenge? (1474 of 1,500 characters)

```
Everything was built during the challenge (first commit 6 Nov 2026; code at github.com/DivineTechie/silsila):
- An exact pedigree engine (variable elimination) with a sourced UAE parameter register for three genes, checked against an independent solver.
- The full cascade as a working service: consent, anonymous invitations, counsellor approval and queue, the relative's private link, comprehension check, booking, results, closure with evidence, a hash-chained audit log, live outcome measures.
- An output gate: only approved templates and verbatim MedlinePlus text reach a person. Read-aloud tied to the exact text by hash.
- FHIR R4B import of an index result (refused with a reason if unsafe) and case export.
- Voice intake: an Emirati family story to a draft tree (Jais-ASR, Jais 3), confirmed by a counsellor.
- Watch a cascade (13 live steps), the Family Twin (61 simulated relatives recalculated live), and a guide answering questions with fixed answers and live lookups, without AI.
- Evidence: five benchmarks on simulated families, a pre-registered benchmark of five language models, privacy and triage tests, an accessibility audit.
- Governance: hazard log, model cards, DoH Responsible AI clause map, pilot protocol, commercial case.
- Production mode, tested: PostgreSQL for several replicas, OpenID Connect sign-in for UAE PASS (mock-tested), start-up checks, logs without personal data.
- Live in Azure UAE North, Arabic and English; a five-minute film.
```

## Before you submit
- The deck's team table (India, Independent, 18 or over), the conflict-of-interest slide ("None") and the IP slide
  (all written during the challenge) carry what the entrant confirmed on 16 Nov 2026.
- If the form or the rules ask about the use of AI tools in building the entry, answer that yourself; the deck
  does not address it.
