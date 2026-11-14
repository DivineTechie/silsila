# Silsila-Bench: amendments and clarifications

Recorded before any scored model run, as required by `PREREGISTRATION.md`. Each entry gives the date,
what was specified, what the harness does, and why. Where an entry changes something the
pre-registration fixed, results are reported both ways where that is possible.

## A1. Population facts are given in every risk prompt (clarification), 2026-11-14

The pre-registration does not say what numbers the model is given. A carrier or child risk on a tree
with people who married in cannot be answered without the population carrier rate, and a negative test
cannot be interpreted without the test's detection rate. Every T1, T2 and T5 prompt therefore ends with
a short "Facts to use" block in the prompt's register: carrier proportion per variant (the published
values in `data/params/loci.yaml`, as used by the engine), detection rate per variant (CYP21A2: assumed
to miss none, matching the engine), the background inbreeding coefficient F = 0.0222 for people whose
parents are not described, complete penetrance and no new mutations. The Gulf Arabic prompts use the
MSA facts block. Gold answers are computed with F = 0.0222; the F = 0 value is stored for every
question and differs by less than 5% (max 4.3%) for all 300 questions, so no band depends on it.

## A2. Where the "first probability" is taken (clarification), 2026-11-14

The fixed system prompt asks for a final line `Answer: <probability>`. The parser removes reasoning
text (`<think>…</think>`, `<ifm|think>…</ifm|think>`; output cut off inside reasoning is "no number"),
then takes the first probability after the last answer marker (`Answer:`, `الإجابة:`, `الجواب:`,
`jawab:`), and otherwise the first probability in the whole answer. The value from "first probability
anywhere in the answer" is logged for every item as a sensitivity check. A range ("20-25%") counts as
its first value and is flagged. Fraction words beyond the three listed (ثلثين/ثلثان = 2/3, ثمن = 1/8,
English and Arabizi equivalents) and number words ("واحد من كل أربعة", "one in four") are recognised.

## A3. Tool calling for models and servers without native support, 2026-11-14

* Llama3-Med42-8B's chat template has no tool support. Its T2/T3 tools are described in the system
  prompt with a `<tool_call>{json}</tool_call>` format, and results are returned in
  `<tool_response>` blocks ("prompted" tool mode). This is reported next to its results.
* Where the server does not parse tool calls (local `mlx_lm.server` for Jais 3), calls are read from
  the model's native text format (`<ifm|tool_call>`); on vLLM the official `k2_horizon` parser is used.
* `compute_family_risk` has a required `gene` field (HBB, CYP21A2 or SMN1) in addition to the
  pre-registered `people`, `unions` and `question`, because the engine needs the locus.
* T2 allows up to 4 tool rounds per item (tool errors are returned to the model so it can correct the
  tree), then one last turn without tools so the model can give its answer; T3 uses a single `submit_family_tree` call by default (the incremental tools are implemented as
  an option and are not part of the scored run unless stated).

## A4. How the families are built from the simulator, 2026-11-14

A full simulated kindred (`generate_kindred`) has dozens of people. Each family is the part a parent of
the affected child would describe: the child, parents, up to two siblings, up to two siblings of each
parent with partners and some cousins, the chosen consanguineous couples, and every ancestor needed to
connect them (8–26 people). The family type is decided on this drawn tree: no consanguineous couple;
exactly one couple, first cousins; two or more consanguineous couples, with at least 15 of the 50
containing a double-first-cousin marriage (achieved: 19). The story states that nobody except the
index has the condition, so all others are recorded as unaffected in the gold tree. Recorded carrier
results are sampled person by person from the engine's posterior given the evidence so far (so they
are always consistent). Question (a) targets an untested living relative with a carrier chance between
0.5% and 95%; question (b) targets a living couple with a risk of at least 1 in 100,000, and the index's
own parents (risk 1 in 4 by definition) are chosen in about 1 family in 10 (22 of 150 achieved).

## A5. Decoding settings versus model-card recommendations, 2026-11-14

The pre-registration fixes temperature 0. The Jais 3 and K2-Think-V2 cards recommend sampling
(temperature 0.2–1.0) and at least 32,768 output tokens. The harness keeps temperature 0 and uses the
template's default reasoning effort (high), with `max_tokens` 32,768 for reasoning models. Greedy
decoding can make reasoning models loop; outputs that end inside the reasoning are "no number" and the
share of `finish_reason = length` is logged per model.

## A6. Exact definitions used in scoring, 2026-11-14

* Bands are not exhaustive: answers between 25% relative error and a factor of 2 are "other".
* T2 "tree identical": same people, sexes, parent links, couples, affected status and condition, and
  test results as the gold tree (names matched across scripts and spelling variants). The share of tool
  calls whose question matches the asked question is also reported.
* T3 "engine answer equals the gold answer": relative difference at most 1e-6 (both questions of the
  family, so the denominator is 2 per tree); the share within the 5% band is also logged. "Exact tree"
  as for T2; "exact structure" ignores evidence. The gene named by the model is logged but is not part
  of the T3 comparison.
* T3 diagnostic (not pre-registered, reported separately): when a model writes the tree as JSON text
  instead of calling the function, the item still counts as "no tool call"; the share of such items and
  how close that text tree was to the gold tree are logged. The local Jais 3 7B smoke test showed this.
* T4 spread: standard deviation of ln(p̂) across the four registers, for family-questions where all four
  registers gave a positive number; the range is logged.
* T5 uses every third family (17 / 17 / 16 by type) with questions alternating (a)/(b). Only PMIDs
  that are labelled (`PMID`, `PubMed ID`) or given as PubMed URLs are counted.

## A7. Models and hardware, 2026-11-14

* Frontier reference: gpt-oss-120b on Fireworks (`accounts/fireworks/models/gpt-oss-120b`); Azure GPT
  quota was not requested, so the Azure entry is reported as not run.
* Jais 3 32B uses the official FP8 checkpoint (`IFM/Jais-3-32B-FP8`) on one H100; the card's reference
  recipe is BF16 on two GPUs.
* K2-Think-V2 (72.5B) is quantised to FP8 on load and served on 2 × H100 80GB; its card serves BF16 on 8
  GPUs. This may change its answers slightly and is reported with its results.
* BiMediX2-8B is a vision-language model; it is served and prompted with text only.

## A8. Publication of items, 2026-11-14

Items are generated deterministically from code and seeds in `src/silsila_bench/items.py`, and the
per-prompt logs contain the full prompts. To keep the item set unpublished until judging, `data/`,
`runs/` and the `docs/evidence/logs/bench/` logs must not be pushed to a public repository before then.
