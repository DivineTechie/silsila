# Model card: voice intake (speech to a draft family tree)

**What it does.** Turns a spoken family story into a **draft** family tree for a genetic counsellor to check.
It proposes structure only: people, sex, parents and marriages. It writes no text that a family member or a
relative reads, and it computes no risk.

**Pipeline**
1. Speech recognition: Jais-ASR (Inception), MLX 4-bit, dialect setting `AE` (Emirati), run on a laptop.
   No audio leaves the machine.
2. Structure drafting: Jais 3 7B (Inception / MBZUAI IFM, Apache-2.0) called once with the
   `submit_family_tree` function, the same function scored in Silsila-Bench track T3.
3. Checks (`backend/src/silsila/intake.py`): every problem is listed; deterministic suggestions (for example
   "the mother's husband is the likely father") are applied only when the counsellor clicks them.
4. Confirmation: the engine refuses the tree until every person and every marriage is confirmed. Health
   status must come from a record with a reference; what was heard is shown and never used.

**Demo input.** A synthetic Emirati voice (Azure AI Speech `ar-AE-FatimaNeural`) reading a fictional script.
It is labelled as synthetic wherever it is played. The hosted app replays the recorded run (labelled
RECORDED); live inference needs a GPU or a Mac and is shown in the film.

**Observed on the demo clip (one run, not an evaluation).** The transcript misspelled two names (Salma, Sara).
Jais 3 7B drafted 16 people and 3 marriages, with every relationship right except one missing father.
The engine rejected the raw draft because three siblings had a father but no recorded mother. After the
counsellor applied the two suggestions, entered statuses from records and confirmed everything, the carrier
probabilities matched the hand-entered case for all 17 people (`test_voice_intake_gives_same_numbers_as_the_entered_case`).

**Evaluation.** Silsila-Bench T3 (story to tree, English and Gulf Arabic, 150 families) measures edge
precision and recall, exact-tree rate and whether the engine's answer on the drafted tree equals the gold
answer, for every benchmarked model. See `docs/evidence/silsila_bench.md`.

**Out of scope.** Diagnoses from speech; any use without a counsellor; any patient-facing output; risk
calculation by the model (the Jais 3 model card itself places high-stakes medical decisions without human
oversight out of scope).

**Known limitations.** Synthetic voice only; no native-speaker recordings yet; one dialect setting tested;
names with several spellings need manual correction.
