## Silsila-Bench: where language models can be used safely inside Silsila

Pre-registered in `bench_llm/PREREGISTRATION.md`; changes in `bench_llm/AMENDMENTS.md`. 150 synthetic families (fictional people), gold answers from the exact Silsila engine. All models are reported together in a fixed order; this is not a ranking. Values are shares with 95% intervals from a bootstrap over families. Band shares exclude answers with no number, which are reported separately.

Generated 2026-11-15T09:38:11Z.

### Models

| Model | Licence | Status |
|---|---|---|
| Jais 3 7B | Apache-2.0 | T1 complete (1200/1200); T2 complete (600/600); T3 complete (300/300); T5 complete (50/50) |
| Jais 3 32B (FP8) | Apache-2.0 | reduced set (t5-sample, AMENDMENTS A10): T1 complete (100/100); T2 complete (100/100); T3 complete (100/100); T5 complete (50/50) |
| K2-Think-V2 (72B, FP8 on load) | Apache-2.0 | not run |
| BiMediX2 8B | CC-BY-NC-SA-4.0 (evaluation only) | T1 complete (1200/1200); T2 complete (600/600); T3 complete (300/300); T5 complete (50/50) |
| Llama3-Med42 8B | Llama 3 Community Licence | T1 complete (1200/1200); T2 complete (600/600); T3 complete (300/300); T5 complete (50/50) |
| gpt-oss-120b (Fireworks, frontier reference) | Apache-2.0 | T1 complete (1200/1200); T2 complete (600/600); T3 complete (300/300); T5 complete (50/50) |
| GPT-class model on Azure OpenAI |  | not run |

### T1 free-text risk

| Model | Items | No number | Exact (≤5%) | Within 25% | Off by ≥2x |
|---|---|---|---|---|---|
| Jais 3 7B | 1200 | 43.4% (38.2–48.5) | 59.4% (54.1–64.5) | 75.3% (70.9–79.6) | 8.0% (5.6–10.6) |
| Jais 3 32B (FP8) | 100 | 52.0% (40.0–65.0) | 95.8% (89.6–100.0) | 100.0% (100.0–100.0) | 0.0% (0.0–0.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | |
| BiMediX2 8B | 1200 | 20.7% (18.4–22.8) | 5.0% (3.5–6.7) | 9.8% (7.7–11.9) | 82.4% (79.7–84.9) |
| Llama3-Med42 8B | 1200 | 0.2% (0.0–0.4) | 8.4% (6.5–10.4) | 13.9% (11.6–16.2) | 78.0% (75.5–80.6) |
| gpt-oss-120b (Fireworks, frontier reference) | 1200 | 0.0% (0.0–0.0) | 33.7% (29.5–37.8) | 49.0% (45.1–53.0) | 30.5% (27.3–33.7) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | |

Exact (≤5%), by register:

| Model | arabizi | en | gulf | msa |
|---|---|---|---|---|
| Jais 3 7B | 40.3% (33.3–46.9) | 74.6% (67.0–81.9) | 57.2% (49.7–64.5) | 78.3% (71.1–85.4) |
| Jais 3 32B (FP8) | – | 96.3% (87.5–100.0) | 95.2% (84.0–100.0) | – |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run | not run |
| BiMediX2 8B | 8.3% (4.6–12.4) | 4.9% (2.7–7.6) | 4.4% (2.0–7.2) | 3.1% (1.2–5.2) |
| Llama3-Med42 8B | 15.0% (11.3–19.0) | 7.7% (5.0–10.7) | 4.7% (2.3–7.3) | 6.3% (3.7–9.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 28.7% (23.3–34.0) | 39.7% (34.0–45.3) | 29.3% (24.3–34.3) | 37.0% (31.7–42.3) |
| GPT-class model on Azure OpenAI | not run | not run | not run | not run |

Exact (≤5%), by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 50.3% (37.4–62.0) | 62.5% (53.9–70.2) | 61.3% (53.1–68.6) |
| Jais 3 32B (FP8) | 100.0% (100.0–100.0) | 88.9% (75.0–100.0) | 100.0% (100.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 4.9% (2.3–8.2) | 5.0% (2.9–7.2) | 5.2% (2.3–8.5) |
| Llama3-Med42 8B | 6.0% (2.8–9.8) | 8.8% (5.5–12.2) | 10.5% (7.2–14.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 27.3% (20.2–34.8) | 38.5% (31.8–45.3) | 35.2% (28.5–42.0) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

### T2 engine as a tool

| Model | Items | Called the tool | Tool tree = gold tree | Tool question = asked question | No number | Final answer exact | Final off by ≥2x |
|---|---|---|---|---|---|---|---|
| Jais 3 7B | 600 | 98.7% (97.7–99.5) | 8.6% (6.9–10.7) | 72.0% (68.8–75.4) | 14.5% (11.7–17.3) | 70.8% (66.5–75.0) | 4.3% (2.7–6.2) |
| Jais 3 32B (FP8) | 100 | 100.0% (100.0–100.0) | 66.9% (58.1–76.1) | 89.5% (82.6–96.1) | 2.0% (0.0–5.0) | 98.0% (94.8–100.0) | 0.0% (0.0–0.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | | | |
| BiMediX2 8B | 600 | 41.2% (37.7–44.8) | 0.0% (0.0–0.0) | 0.4% (0.0–1.3) | 98.0% (96.8–99.0) | 0.0% (0.0–0.0) | 100.0% (100.0–100.0) |
| Llama3-Med42 8B | 600 | 52.0% (47.3–57.2) | 0.0% (0.0–0.0) | 75.3% (69.8–80.4) | 12.2% (9.8–14.8) | 3.6% (2.1–5.5) | 83.5% (79.9–86.9) |
| gpt-oss-120b (Fireworks, frontier reference) | 600 | 77.0% (73.5–80.7) | 0.2% (0.0–0.5) | 69.8% (66.0–73.6) | 0.2% (0.0–0.5) | 34.4% (29.5–39.2) | 19.2% (15.9–22.5) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | | | |

Final answer exact, by register:

| Model | en | gulf |
|---|---|---|
| Jais 3 7B | 70.2% (65.0–75.6) | 71.3% (66.1–76.5) |
| Jais 3 32B (FP8) | 98.0% (93.7–100.0) | 98.0% (93.8–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | – |
| Llama3-Med42 8B | 5.4% (3.0–8.2) | 1.3% (0.0–3.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 38.7% (33.0–44.0) | 30.1% (24.7–35.4) |
| GPT-class model on Azure OpenAI | not run | not run |

Final answer exact, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 70.9% (64.5–77.3) | 65.9% (57.9–73.9) | 75.6% (68.4–82.5) |
| Jais 3 32B (FP8) | 96.8% (90.0–100.0) | 97.1% (91.2–100.0) | 100.0% (100.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 1.2% (0.0–3.0) | 8.4% (4.5–13.3) | 1.1% (0.0–2.8) |
| gpt-oss-120b (Fireworks, frontier reference) | 27.5% (20.0–35.0) | 38.5% (30.0–47.0) | 37.2% (28.6–45.5) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

### T3 story to tree

| Model | Items | Called the tool | Edge precision | Edge recall | Exact tree | Exact structure | Engine answer = gold | Tree written as text, no call |
|---|---|---|---|---|---|---|---|---|
| Jais 3 7B | 300 | 95.0% (92.3–97.3) | 95.0% (93.4–96.4) | 90.9% (87.8–93.6) | 38.7% (33.7–44.0) | 61.7% (55.7–67.3) | 48.0% (42.5–53.5) | 0.0% (0.0–0.0) |
| Jais 3 32B (FP8) | 100 | 94.0% (89.0–98.0) | 99.5% (99.0–99.9) | 92.5% (87.1–97.3) | 84.0% (76.0–91.0) | 85.0% (77.0–92.0) | 88.5% (82.0–94.0) | 5.0% (1.0–9.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | | | | |
| BiMediX2 8B | 300 | 59.0% (54.7–63.7) | 67.3% (52.5–86.2) | 0.8% (0.0–1.8) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 300 | 99.7% (99.0–100.0) | 68.7% (65.7–71.8) | 51.8% (48.3–55.5) | 0.0% (0.0–0.0) | 8.3% (5.3–11.3) | 1.0% (0.2–2.0) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 300 | 99.7% (99.0–100.0) | 93.2% (91.7–94.6) | 91.5% (88.6–93.7) | 33.3% (29.0–37.3) | 59.0% (54.3–63.7) | 37.7% (33.2–42.2) | 0.0% (0.0–0.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | | | | |

Engine answer = gold, by register:

| Model | en | gulf |
|---|---|---|
| Jais 3 7B | 56.7% (48.7–64.7) | 39.3% (31.7–47.0) |
| Jais 3 32B (FP8) | 97.0% (92.0–100.0) | 80.0% (69.0–90.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 1.7% (0.3–3.3) | 0.3% (0.0–1.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 68.0% (60.7–75.3) | 7.3% (3.7–11.3) |
| GPT-class model on Azure OpenAI | not run | not run |

Engine answer = gold, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 38.5% (29.0–48.5) | 57.0% (48.0–66.5) | 48.5% (39.0–57.5) |
| Jais 3 32B (FP8) | 85.9% (75.0–95.3) | 92.6% (79.4–100.0) | 86.8% (76.5–97.1) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 0.0% (0.0–0.0) | 2.5% (0.5–5.5) | 0.5% (0.0–1.5) |
| gpt-oss-120b (Fireworks, frontier reference) | 27.5% (20.5–34.5) | 47.0% (38.5–55.5) | 38.5% (31.5–45.0) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

### T4 language consistency (from T1)

| Model | Items | All 4 registers same band | Mean SD of ln(p̂) | All 4 registers gave a number |
|---|---|---|---|---|
| Jais 3 7B | 300 | 49.0% (38.9–59.0) | 0.23 (0.13–0.36) | 32.0% (26.0–38.3) |
| Jais 3 32B (FP8) | not run | not computed on the sample (needs all four registers) | | |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | |
| BiMediX2 8B | 300 | 52.1% (44.2–60.3) | 2.19 (2.02–2.37) | 39.0% (33.7–44.7) |
| Llama3-Med42 8B | 300 | 48.3% (43.6–53.0) | 1.76 (1.63–1.91) | 99.3% (98.3–100.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 300 | 21.7% (17.3–26.3) | 1.04 (0.92–1.16) | 100.0% (100.0–100.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | |

All 4 registers same band, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 44.4% (20.0–69.2) | 52.8% (40.0–65.4) | 44.0% (22.2–65.2) |
| Jais 3 32B (FP8) | not run | not run | not run |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 53.1% (38.9–67.6) | 50.0% (38.1–62.3) | 54.3% (38.7–69.4) |
| Llama3-Med42 8B | 51.5% (42.0–61.2) | 47.0% (40.0–54.0) | 46.5% (38.3–55.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 16.0% (9.0–23.0) | 29.0% (21.0–38.0) | 20.0% (13.0–28.0) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

### T5 invented sources

| Model | Items | Answers citing PMIDs | PMIDs per answer | PMIDs not found | Existing PMIDs, title unrelated | Answers with a flagged PMID |
|---|---|---|---|---|---|---|
| Jais 3 7B | 50 | 6.0% (0.0–14.0) | 0.08 (0.00–0.18) | 0.0% (0.0–0.0) | 100.0% (100.0–100.0) | 100.0% (100.0–100.0) |
| Jais 3 32B (FP8) | 50 | 48.0% (34.0–62.0) | 0.94 (0.66–1.24) | 4.3% (0.0–10.5) | 95.6% (88.7–100.0) | 100.0% (100.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | | |
| BiMediX2 8B | 50 | 50.0% (36.0–64.0) | 1.22 (0.38–2.76) | 0.0% (0.0–0.0) | 98.4% (97.7–100.0) | 100.0% (100.0–100.0) |
| Llama3-Med42 8B | 50 | 30.0% (18.0–44.0) | 0.42 (0.22–0.64) | 4.8% (0.0–17.6) | 95.0% (85.7–100.0) | 100.0% (100.0–100.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 50 | 80.0% (70.0–90.0) | 2.48 (2.02–2.90) | 3.2% (0.0–7.3) | 96.7% (93.4–99.2) | 100.0% (100.0–100.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | | |

PMIDs not found, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Jais 3 32B (FP8) | 20.0% (0.0–40.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 10.0% (0.0–40.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 0.0% (0.0–0.0) | 5.4% (0.0–16.7) | 4.8% (0.0–11.4) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

### Same sample for every model (AMENDMENTS A10)

Jais 3 32B was run on the T5 sample only: every third family (50), one question each (alternating carrier / couple), English and Gulf Arabic (T1 100, T2 100, T3 100, T5 50). To compare like with like, every model is scored again on exactly these items below.

#### T1 free-text risk

| Model | Items | No number | Exact (≤5%) | Within 25% | Off by ≥2x |
|---|---|---|---|---|---|
| Jais 3 7B | 100 | 41.0% (30.0–52.0) | 64.4% (49.2–77.6) | 78.0% (64.8–89.2) | 6.8% (0.0–15.6) |
| Jais 3 32B (FP8) | 100 | 52.0% (40.0–65.0) | 95.8% (89.6–100.0) | 100.0% (100.0–100.0) | 0.0% (0.0–0.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | |
| BiMediX2 8B | 100 | 19.0% (12.0–27.0) | 8.6% (3.4–14.8) | 14.8% (7.4–22.0) | 80.2% (71.6–88.8) |
| Llama3-Med42 8B | 100 | 1.0% (0.0–3.0) | 9.1% (4.0–14.1) | 15.2% (8.1–22.0) | 77.8% (70.0–85.9) |
| gpt-oss-120b (Fireworks, frontier reference) | 100 | 0.0% (0.0–0.0) | 37.0% (26.0–49.0) | 50.0% (38.0–62.0) | 33.0% (23.0–44.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | |

Exact (≤5%), by register:

| Model | en | gulf |
|---|---|---|
| Jais 3 7B | 66.7% (47.4–85.0) | 62.9% (46.9–77.5) |
| Jais 3 32B (FP8) | 96.3% (87.5–100.0) | 95.2% (84.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run |
| BiMediX2 8B | 11.6% (2.4–22.2) | 5.3% (0.0–13.2) |
| Llama3-Med42 8B | 12.2% (4.1–21.3) | 6.0% (0.0–14.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 40.0% (26.0–54.0) | 34.0% (20.0–48.0) |
| GPT-class model on Azure OpenAI | not run | not run |

Exact (≤5%), by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 44.4% (15.8–72.7) | 66.7% (38.5–92.9) | 76.9% (56.5–92.9) |
| Jais 3 32B (FP8) | 100.0% (100.0–100.0) | 88.9% (75.0–100.0) | 100.0% (100.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 4.8% (0.0–16.7) | 9.4% (0.0–20.7) | 10.7% (0.0–23.1) |
| Llama3-Med42 8B | 12.5% (3.1–21.9) | 0.0% (0.0–0.0) | 15.2% (5.9–26.5) |
| gpt-oss-120b (Fireworks, frontier reference) | 28.1% (9.4–50.0) | 26.5% (11.8–44.1) | 55.9% (38.2–73.5) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

#### T2 engine as a tool

| Model | Items | Called the tool | Tool tree = gold tree | Tool question = asked question | No number | Final answer exact | Final off by ≥2x |
|---|---|---|---|---|---|---|---|
| Jais 3 7B | 100 | 99.0% (97.0–100.0) | 8.6% (4.7–13.5) | 72.7% (63.7–81.2) | 15.0% (9.0–21.0) | 72.9% (62.1–82.8) | 7.1% (2.3–12.9) |
| Jais 3 32B (FP8) | 100 | 100.0% (100.0–100.0) | 66.9% (58.1–76.1) | 89.5% (82.6–96.1) | 2.0% (0.0–5.0) | 98.0% (94.8–100.0) | 0.0% (0.0–0.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | | | |
| BiMediX2 8B | 100 | 36.0% (28.0–44.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 99.0% (97.0–100.0) | 0.0% (0.0–0.0) | 100.0% (100.0–100.0) |
| Llama3-Med42 8B | 100 | 46.0% (35.0–58.0) | 0.0% (0.0–0.0) | 84.1% (74.2–93.2) | 10.0% (5.0–16.0) | 2.2% (0.0–5.6) | 84.4% (75.3–92.3) |
| gpt-oss-120b (Fireworks, frontier reference) | 100 | 79.0% (71.0–87.0) | 0.0% (0.0–0.0) | 68.3% (58.0–78.8) | 0.0% (0.0–0.0) | 36.0% (25.0–46.0) | 21.0% (13.0–30.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | | | |

Final answer exact, by register:

| Model | en | gulf |
|---|---|---|
| Jais 3 7B | 77.8% (64.4–88.9) | 67.5% (52.6–82.1) |
| Jais 3 32B (FP8) | 98.0% (93.7–100.0) | 98.0% (93.8–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | – |
| Llama3-Med42 8B | 4.0% (0.0–10.0) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 48.0% (34.0–62.0) | 24.0% (12.0–36.0) |
| GPT-class model on Azure OpenAI | not run | not run |

Final answer exact, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 73.1% (54.2–88.9) | 57.1% (35.7–77.8) | 87.1% (71.0–100.0) |
| Jais 3 32B (FP8) | 96.8% (90.0–100.0) | 97.1% (91.2–100.0) | 100.0% (100.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | – | – |
| Llama3-Med42 8B | 0.0% (0.0–0.0) | 6.9% (0.0–17.9) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 37.5% (18.8–56.2) | 17.6% (5.9–32.4) | 52.9% (35.3–70.6) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

#### T3 story to tree

| Model | Items | Called the tool | Edge precision | Edge recall | Exact tree | Exact structure | Engine answer = gold | Tree written as text, no call |
|---|---|---|---|---|---|---|---|---|
| Jais 3 7B | 100 | 96.0% (92.0–99.0) | 92.4% (89.1–95.2) | 90.4% (85.4–94.5) | 34.0% (25.0–43.0) | 56.0% (46.0–66.0) | 42.5% (33.0–52.0) | 0.0% (0.0–0.0) |
| Jais 3 32B (FP8) | 100 | 94.0% (89.0–98.0) | 99.5% (99.0–99.9) | 92.5% (87.1–97.3) | 84.0% (76.0–91.0) | 85.0% (77.0–92.0) | 88.5% (82.0–94.0) | 5.0% (1.0–9.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | | | | |
| BiMediX2 8B | 100 | 65.0% (57.0–73.0) | 86.2% (86.2–86.2) | 0.8% (0.0–2.6) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 100 | 100.0% (100.0–100.0) | 72.0% (66.3–77.6) | 52.0% (46.1–57.5) | 0.0% (0.0–0.0) | 11.0% (6.0–17.0) | 0.5% (0.0–1.5) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 100 | 100.0% (100.0–100.0) | 92.1% (88.9–94.9) | 91.2% (88.0–94.2) | 31.0% (24.0–38.0) | 58.0% (49.0–66.0) | 36.5% (28.5–44.0) | 0.0% (0.0–0.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | | | | |

Engine answer = gold, by register:

| Model | en | gulf |
|---|---|---|
| Jais 3 7B | 45.0% (31.0–58.0) | 40.0% (27.0–54.0) |
| Jais 3 32B (FP8) | 97.0% (92.0–100.0) | 80.0% (69.0–90.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 1.0% (0.0–3.0) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 66.0% (52.0–78.0) | 7.0% (2.0–14.0) |
| GPT-class model on Azure OpenAI | not run | not run |

Engine answer = gold, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 29.7% (14.1–46.9) | 60.3% (44.1–76.5) | 36.8% (23.5–51.5) |
| Jais 3 32B (FP8) | 85.9% (75.0–95.3) | 92.6% (79.4–100.0) | 86.8% (76.5–97.1) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 0.0% (0.0–0.0) | 1.5% (0.0–4.4) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 23.4% (10.9–35.9) | 41.2% (26.5–55.9) | 44.1% (33.8–52.9) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

#### T4 language consistency (from T1)

| Model | Items | All 4 registers same band | Mean SD of ln(p̂) | All 4 registers gave a number |
|---|---|---|---|---|
| Jais 3 7B | not run | not computed on the sample (needs all four registers) | | |
| Jais 3 32B (FP8) | not run | not computed on the sample (needs all four registers) | | |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | |
| BiMediX2 8B | not run | not computed on the sample (needs all four registers) | | |
| Llama3-Med42 8B | not run | not computed on the sample (needs all four registers) | | |
| gpt-oss-120b (Fireworks, frontier reference) | not run | not computed on the sample (needs all four registers) | | |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | |

#### T5 invented sources

| Model | Items | Answers citing PMIDs | PMIDs per answer | PMIDs not found | Existing PMIDs, title unrelated | Answers with a flagged PMID |
|---|---|---|---|---|---|---|
| Jais 3 7B | 50 | 6.0% (0.0–14.0) | 0.08 (0.00–0.18) | 0.0% (0.0–0.0) | 100.0% (100.0–100.0) | 100.0% (100.0–100.0) |
| Jais 3 32B (FP8) | 50 | 48.0% (34.0–62.0) | 0.94 (0.66–1.24) | 4.3% (0.0–10.5) | 95.6% (88.7–100.0) | 100.0% (100.0–100.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | started on the T5 sample (A12); not finished within budget (45 of 350 prompts answered), not scored | | | | |
| BiMediX2 8B | 50 | 50.0% (36.0–64.0) | 1.22 (0.38–2.76) | 0.0% (0.0–0.0) | 98.4% (97.7–100.0) | 100.0% (100.0–100.0) |
| Llama3-Med42 8B | 50 | 30.0% (18.0–44.0) | 0.42 (0.22–0.64) | 4.8% (0.0–17.6) | 95.0% (85.7–100.0) | 100.0% (100.0–100.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 50 | 80.0% (70.0–90.0) | 2.48 (2.02–2.90) | 3.2% (0.0–7.3) | 96.7% (93.4–99.2) | 100.0% (100.0–100.0) |
| GPT-class model on Azure OpenAI | not run | Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference | | | | |

PMIDs not found, by family type:

| Model | multiple | no_loop | one_loop |
|---|---|---|---|
| Jais 3 7B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Jais 3 32B (FP8) | 20.0% (0.0–40.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| K2-Think-V2 (72B, FP8 on load) | not run | not run | not run |
| BiMediX2 8B | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| Llama3-Med42 8B | 10.0% (0.0–40.0) | 0.0% (0.0–0.0) | 0.0% (0.0–0.0) |
| gpt-oss-120b (Fireworks, frontier reference) | 0.0% (0.0–0.0) | 5.4% (0.0–16.7) | 4.8% (0.0–11.4) |
| GPT-class model on Azure OpenAI | not run | not run | not run |

Limitations: synthetic families; Arabic, Gulf Arabic and Arabizi templates written without native-speaker review; one sample per prompt at temperature 0; PMID relatedness is a keyword check and every flagged case is reviewed by the team.
