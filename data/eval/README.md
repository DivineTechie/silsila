# Triage evaluation data

- `triage_testset.jsonl`: 400 messages (100 each: English, MSA, Gulf colloquial Arabic, Arabizi), multi-label (crisis, decision_request, religious, third_party, distress, booking, information; empty = none). `hard: true` marks negations, idioms, sarcasm, indirect phrasing, typos, mixed language, very short and long messages.
- `privacy_attacks.jsonl`: 60 prompts attempting to extract another person's data or identity (impersonation, entitlement claims, indirect inference, admin-mode, enumeration).

Provenance and limits:
- Authored by an AI model (Claude), blind to the classifier's rules (its source was not read).
- Synthetic; not real user messages.
- Labels were assigned by the author, conservatively (possible risk to life => crisis). They have NOT been validated by native-speaking clinicians or genetic counsellors; Arabic dialect and Arabizi usage may contain errors.
- Intended as a stress test, not a clinical validation.
