# Judges' guide

Organised by the six judging criteria. Live app (no password; one-click roles):
https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io. All figures below are on synthetic
families and are already in the [README](../README.md) and [`evidence/`](evidence/README.md). Nothing has been used
with patients.

| Time | Path |
|---|---|
| 5 minutes | Home page, **Watch a cascade** (13 live steps), **Family Twin**, press **Listen** on a relative's link |
| 15 minutes | Add the three roles (Mariam, counsellor, relative), the FHIR import, the **Evidence** page |
| 1 hour | Add the sections below, the [hazard log](governance/hazard-log.md), and the tests: `cd backend && uv run pytest -q` |

## 1. Health impact and clinical relevance

- **Open:** Watch a cascade (a newborn's result reaches a pregnant sister); Family Twin.
- **Check:** in simulation, Silsila's order found 51 at-risk couples per 1,000 tests against 33 unranked for CAH
  (ratio 1.53, 95% CI 1.29-1.85); HBB 65 vs 41 (1.58, 1.43-1.77); SMN1 54 vs 35 (1.56, 1.39-1.81). All four
  published yields of the NEJM 2002 family-screening study fall inside the simulated range.
  Evidence: [`evidence/b4_uae.json`](evidence/b4_uae.json), [`evidence/b3_nejm.json`](evidence/b3_nejm.json).
- **Not yet shown:** any patient outcome. Yields are projections; uptake and comprehension need a pilot.
  See [`limitations.md`](limitations.md).

## 2. Technical depth

- **Open:** Family Twin (61 people, six cousin marriages, exact recalculation); Evidence page.
- **Check:** 30,000 of 30,000 probabilities match an independent exact solver (pgmpy), maximum error 5.6e-16
  ([`evidence/b1_engine.json`](evidence/b1_engine.json)); 0 silent failures in 237 malformed inputs
  ([`evidence/b2_robustness.json`](evidence/b2_robustness.json)); median 173 ms for a 60-person family
  ([`evidence/perf_engine.json`](evidence/perf_engine.json)); pre-registered benchmark of five language models on
  150 families ([`evidence/silsila_bench.md`](evidence/silsila_bench.md),
  [`../bench_llm/PREREGISTRATION.md`](../bench_llm/PREREGISTRATION.md)).
- **Not yet shown:** three genes only (HBB, CYP21A2, SMN1); other conditions are refused, not estimated.

## 3. Working solution and demo quality

- **Open:** each role on the home page; counsellor **Cases** (FHIR import, then change `"final"` to
  `"preliminary"` and see the refusal); **Voice intake**; **Outcomes**; the 5-minute film
  https://youtu.be/fCHWTlGyeSY.
- **Check:** every cascade step runs the real service, from consent to closure with evidence; 0 accessibility
  violations on every screen in English and Arabic ([`evidence/accessibility.md`](evidence/accessibility.md)); 250
  backend tests (run them locally, or see CI).
- **Not yet shown:** voice intake on the hosted site replays one recorded run.

## 4. Responsible AI, safety and data governance

- **Open:** Watch a cascade, steps 10 and 12; the guide question "Does AI write what families read?";
  [`ai-disclosure.md`](ai-disclosure.md); [hazard log](governance/hazard-log.md);
  [DoH RAI clause map](governance/doh-rai-clause-map.md); [UAE data rules map](governance/uae-data-rules-map.md).
- **Check:** 0 disclosures in 10,000 unauthorised requests
  ([`evidence/privacy_api.json`](evidence/privacy_api.json)); crisis-message alert sensitivity 0.961 (95% CI
  0.890-0.986), 76/76 replies show 998/999, every message read by a person
  ([`evidence/triage_rules_ngram.json`](evidence/triage_rules_ngram.json)); read-aloud tied to the exact approved
  text by hash ([`../data/content/audio/manifest.json`](../data/content/audio/manifest.json)).
- **Not yet shown:** Arabic is machine translation, not reviewed by a native-speaking clinician; no genetic
  counsellor has reviewed the templates; no clip has been checked by a native listener; the output gate has no
  measured block rate.

## 5. Scalability and deployment readiness

- **Open:** Evidence page (engine latency); [`deployment.md`](deployment.md); [`production.md`](production.md);
  [`architecture.md`](architecture.md); API health
  https://silsila-api.lemonisland-568f9acd.uaenorth.azurecontainerapps.io/api/health.
- **Check:** runs in Azure UAE North on CPU with no language model at run time; 0 errors at 25 concurrent
  clients on the hosted prototype, 382 link opens a second
  ([`evidence/load_hosted.json`](evidence/load_hosted.json)); Family Twin recalculation 0.7 s, median 0.9 s hosted
  ([`evidence/twin_hosted_timing.json`](evidence/twin_hosted_timing.json)); index results arrive and leave as FHIR
  R4B.
- **Not yet shown:** the hosted demo is one SQLite replica; one replica does about 1.5 full 61-person
  recalculations a second, so heavy recalculation queues. PostgreSQL storage (whole suite passes on it) and OIDC
  sign-in are built and tested but not deployed; UAE PASS itself has not been tested (only a mock provider).
  What only a pilot partner can provide is listed in [`production.md`](production.md).

## 6. Commercial viability and path to pilot

- **Open:** Evidence page (announced programmes, scenario calculator); [`commercial-case.md`](commercial-case.md);
  [`pilot-protocol.md`](pilot-protocol.md); [`alternatives.md`](alternatives.md).
- **Check:** the buyer already produces the index events: 565 incompatible couples among 11,748 tested; more than
  100 babies identified by newborn screening in the past year (reported figures,
  [`evidence/uae_context.json`](evidence/uae_context.json)); 9 practising genetic counsellors in the UAE.
- **Not yet shown:** no price is validated and no programme has asked for cascade testing; the pilot protocol is a
  proposal.
