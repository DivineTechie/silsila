# Model card: message triage classifier

**What it does.** Labels a free-text message (crisis, decision request, religious question, third-party
request, distress, booking, information) to order the counsellor queue and choose an approved reply.
**It never writes text.** Replies are approved templates or verbatim MedlinePlus paragraphs.

**Components (combined by union, so each can only add caution)**
1. Rules: patterns in English, Arabic and Arabizi (`backend/src/silsila/triage.py`).
2. Character n-gram model: TF-IDF over character 2-5-grams with Arabic letter normalisation, one logistic
   regression per label (`data/models/triage_ngram.joblib`, trained by `backend/evals/train_triage.py`).
3. Optional Azure OpenAI classifier (off unless configured). Receives redacted text; labels only.

**Training data.** 800 synthetic messages (`data/dev/triage_devset.jsonl`), 200 each in English, Modern
Standard Arabic, Gulf Arabic and Arabizi, written by an AI model (Claude) without access to the test set.
Thresholds chosen by 5-fold cross-validation to reach recall targets (crisis 0.95; decision, religious,
distress 0.85; others 0.75). Queue alerts use these thresholds; reply wording uses predictions at 0.5 or
above.

**Evaluation.** One scoring run on a separate blind 400-message test set (`data/eval/triage_testset.jsonl`),
written by another process that never saw the rules. Results with Wilson 95% intervals are in
`docs/evidence/triage_rules_ngram.json`; per-message results in the matching `_cases.csv`.

| Measure | Rules only | Rules + n-gram |
|---|---|---|
| Crisis alert sensitivity | 0.105 | 0.961 (0.890-0.986) |
| Crisis alert specificity | 0.985 | 0.648 (0.595-0.698) |
| Escalation sensitivity | 0.748 | 0.991 |
| Crisis replies containing 998/999 | 1.000 | 1.000 |

**Safety design that does not depend on the model.** Every message is read by a person; every reply ends
with the emergency line; the output gate blocks any unapproved wording.

**Limitations.** Synthetic training and test data written by an AI model; labels by that author; not
validated on real messages or by native-speaking clinicians. Gulf Arabic crisis sensitivity is the lowest
(0.895). Specificity is low by design. The model must be re-evaluated on consented real messages during a
pilot before any reliance on queue ordering.
