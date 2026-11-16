# Seven-minute storyline

For a live pitch with the site open. Times are targets; the split gives the most time to what only Silsila
does. Every number below is in `README.md` or `docs/evidence/`. Say the limits out loud: they are part of the
pitch.

| Time | What is on screen | What to say |
|---|---|---|
| 0:00-0:35 | Home page | "Premarital screening protects the next marriage. Silsila protects the marriages that already happened." Abu Dhabi's premarital test found 565 incompatible couples among 11,748 tested; newborn genomic screening identified more than 100 babies in the past year (reported figures). Each of those results belongs to a family, and in families where cousins marry, the relatives at risk are often already married to each other. Nothing announced so far reaches them. |
| 0:35-1:30 | Watch a cascade, steps 1-2 | The index case: newborn screening finds classic CAH in baby Zayed (a fictional family). His parents are first cousins; his aunt Noura married another cousin and is pregnant. **Only Silsila:** an exact Bayesian engine computes every relative's chance across both cousin loops, not couple arithmetic, and ranks whom to tell first. Point at the ranking and the numbers beside the tree. |
| 1:30-2:30 | Steps 3-9 | The family decides. Mariam gives permission, chooses an anonymous invitation, and a genetic counsellor approves it before anything is sent. Noura's link: approved wording and word-for-word MedlinePlus text in Arabic, with read-aloud; a comprehension check; the options before or during a pregnancy in the source's words, described and never recommended; booking. Say: "No language model wrote any sentence she reads." |
| 2:30-3:15 | Steps 10-13 | She asks whether to end the pregnancy: the system does not answer, a counsellor is alerted. The test result closes the case with evidence. A model's attempt to write advice is blocked by the output gate, live. Every step is on a hash-chained audit log, shown beside the tree. The programme's measures for this run: comprehension, uptake, time to counselling, privacy, language. Marriages and reproductive choices are never counted. |
| 3:15-4:30 | Family Twin | **Only Silsila:** a simulated clan of 61 people with six cousin marriages. Record a result and watch every relative's chance recalculated exactly (about a second on the hosted server). Play the cascade race. Then the claim, which rests on many clans, not this one: Silsila's order found 1.58 times as many at-risk couples per test as an unranked cascade (95% interval 1.43 to 1.77), and the engine agrees with an independent solver on 30,000 of 30,000 probabilities. |
| 4:30-5:30 | Counsellor: Voice intake, then Evidence (chatbot contrast) | **Only Silsila:** we measured the co-creators' own models, pre-registered, on 150 families. Jais 3 7B gave an exact number in 59.4% of its free-text answers; with the engine as a tool, 70.8%. Every model's cited PubMed IDs included ones that did not support the claim. So models do one job here: Jais-ASR and Jais 3 draft a family tree from a spoken Emirati story (a recorded run), and the counsellor confirms every person before the engine runs. |
| 5:30-6:15 | Counsellor: Cases (FHIR import), Outcomes; Evidence: announced programmes, scenario | It plugs into what exists: the index result arrives as a FHIR R4B record and is refused if it is preliminary or a variant of uncertain significance. Hosted in Azure UAE North, on CPU, no model at run time. Scenario, as a projection: 100 index newborns a year at 5 tests per family is 500 tests, about 25 at-risk couples for CAH in Silsila's order against 17 unranked. The UAE has 9 practising genetic counsellors: counsellor time is what Silsila saves. |
| 6:15-7:00 | Home page: the six criteria | What is not yet shown, said plainly: no patients; yields are simulations; three genes; Arabic is machine translation awaiting a native clinician; no programme has asked for cascade testing. The ask: a shadow-mode pilot at one screening centre, counsellors running their usual process with Silsila computing alongside, and a native Arabic and genetic-counsellor review of every sentence. "Silsila: the step after the result." |

## If there are only three minutes
Play the film (`tools/film/`), or do rows 1, 2, 5 and the last sentence of row 8.

## Questions to expect, and where the answer is
- "Is this a medical device?" Not validated; decision support with a counsellor approving every message. `docs/commercial-case.md`, Regulation and readiness.
- "Why not let the model explain the result?" `docs/evidence/silsila_bench.md` and the contrast panel; hazard H17.
- "What about a family that does not want to tell anyone?" Declining ends the process and is recorded; step 3 of the cascade; hazards H7 and H8.
- "Whose data, and where?" Fictional only; UAE North; names and identifiers in an imported record are not stored. `docs/deployment.md`, `docs/limitations.md`.
- "What would you measure in a pilot?" `docs/pilot-protocol.md`: comprehension, uptake, time to counselling, at-risk couples identified, privacy, equity. Never marriages.
