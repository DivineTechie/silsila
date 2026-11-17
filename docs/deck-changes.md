# Pitch deck: what was corrected, and what is recommended

The deck is a private Slides artifact (13 slides). On 16 Nov three factual corrections were made in it; the
rest below are recommendations for the owner to accept or not. Every number is in `README.md` or
`docs/evidence/`.

## Corrected in the deck on 16 Nov

| Slide | Was | Now | Why |
|---|---|---|---|
| Family Twin | "change in under a second"; "0.7 s on the hosted server; 0.15 s on a laptop" | "in about a second"; "0.7-1.2 s, measured on the hosted server, 16 Nov; 0.12 s on a laptop" | Measured after the redeploy: 0.7 s with no extra results, median 0.9 s (0.7 to 1.2) once results are recorded (`docs/evidence/twin_hosted_timing.json`) |
| Responsible AI | "19 hazards"; "axe, WCAG 2.1 AA" | "24 hazards"; "axe, WCAG 2.2 AA rules, English and Arabic, 16 Nov" | Hazards H20 to H24 were added; the audit was repeated with the 2.2 rules |
| Deployment and scale | "FHIR R4B export for Malaffi; entry from TAMM or Sahatna" | "An index result arrives as a FHIR R4B record and leaves the same way (fictional sample; no Malaffi profile seen yet)" | Import now exists; nothing has been tested against Malaffi, TAMM or Sahatna |

## Recommended, not yet made

1. **Problem slide.** Add the newborn figure beside the premarital one: newborn genomic screening identified
   more than 100 babies in the past year (DoH chairman, Khaleej Times, 20 Oct 2026). Change "565 at-risk
   couples flagged" to the source's wording: "565 couples found genetically incompatible among 11,748 tested,
   2022 to July 2026". The demo's index case is a newborn, so this slide should set that up.
2. **What Silsila does.** The four steps are right. Add under them: read-aloud of the exact text (synthetic
   voice, labelled), and the options before or during a pregnancy quoted word for word, described and never
   recommended. Both are now live.
3. **Proof slide.** Since the story is a CAH newborn, add the CAH yield beside the haemoglobin one: 51 against
   33 at-risk couples per 1,000 tests (ratio 1.53, 95% interval 1.29 to 1.85). Add the newborn projection,
   labelled a projection: 100 index newborns a year, 500 tests, about 25 couples against 17 for CAH.
4. **Outcomes slide.** Say that the last step of Watch a cascade shows these measures for that one run,
   including time to counselling and what the invitation disclosed.
5. **Deployment and scale.** Replace the Emirati Genome Programme card's wording with the announced plan, kept
   conditional: personalised genomic reports for 900,000 participants through TAMM from December 2026,
   covering 214 inherited conditions and health traits (The National, 10 Nov 2026). "If those reports include
   carrier findings, each is a possible index result." Do not say DoH has asked for cascade testing.
6. **A new slide, "Ask it anything, without AI".** The guide answers questions about the tool from 50 fixed
   answers and 19 live lookups (the engine, the gate, the audit chain, the evidence files), says so when it has
   no answer, and declines personal questions. It makes the "no language model writes to a family" rule
   visible in the product itself.
7. **Close slide.** Add to the limits: read-aloud clips have not been checked by a native listener; the quoted
   MedlinePlus text scores at a college reading level (Flesch-Kincaid grade 13.4) while Silsila's own wording
   scores 6.9. Add where the film is.
8. **Speaker notes throughout.** The seven-minute order in `docs/storyline-7min.md` differs from the deck
   order: it goes hook, newborn case and cascade (live), Family Twin (live), models measured and voice
   intake, FHIR and scale, limits and the ask. Either reorder the deck to match or use the deck only for the
   opening, the proof numbers and the close.
