# Triage development set

`triage_devset.jsonl` is a **synthetic development set written by an AI model (Claude)**. It contains 800 invented messages (200 each: `en`, `msa`, `gulf`, `arabizi`) with multi-label annotations (crisis, decision_request, religious, third_party, distress, booking, information; empty = none).

- Used **only for tuning** the message-triage component.
- **Separate from and blind to** the held-out test set (`data/eval/`), which the author did not open or read.
- No real user messages or personal data; names and scenarios are fictional. Labels are the author's judgement and may contain errors.
- Format: one JSON object per line: `id`, `variety`, `text`, `labels`.
