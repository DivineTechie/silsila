# Person-facing content

- `sources/medlineplus/*.json`: paragraphs imported verbatim from MedlinePlus Genetics (public domain, US
  National Library of Medicine; licence verified at https://medlineplus.gov/copyright.html), with URL,
  retrieval time and a SHA-256 hash per paragraph. Paragraphs about US law or programmes are flagged and
  never shown. Re-import with `backend/scripts/import_medlineplus.py`.
- `templates.yaml`: the approved procedural sentences (English; Arabic machine-translated, pending native
  clinical review). Numbers inside them come only from the engine.
- `faq.yaml`: information topics, each answered only by cited MedlinePlus paragraphs.

Purpose: the only text Silsila may show people. The output gate in `backend/src/silsila/content.py` blocks
anything else.
