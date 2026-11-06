# Translation check

Compares independent English-to-Arabic translations of the quoted MedlinePlus
paragraphs and writes a review list for a native-speaking clinician.

Systems: Claude (stored in `data/content/translations/ar/medlineplus.json`),
Helsinki-NLP `opus-mt-tc-big-en-ar` (local), and Azure AI Translator when
`AZURE_TRANSLATOR_KEY` and `AZURE_TRANSLATOR_REGION` are set in `.env`
(copy `.env.example`). Checks: numbers preserved, LaBSE meaning similarity,
agreement between systems.

    uv run python translate_qc.py

Outputs: `qc_report.json`, `review_list.md`, and a `qc` block per paragraph.
Flags only order human review; every paragraph still needs native clinical review.
