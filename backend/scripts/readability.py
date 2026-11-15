"""Readability of the English text a relative can be shown.

    uv run --with textstat==0.7.3 --with "setuptools<70" python scripts/readability.py

Standard formulas (textstat): Flesch Reading Ease and Flesch-Kincaid Grade Level for every text, and SMOG for
the pooled groups with at least 30 sentences (the minimum the SMOG formula was designed for). Variable parts
of templates are filled with the example values listed in the output, so the scores describe what a person
would actually read. No formula is applied to the Arabic text: these formulas are defined for English, and no
readability measure validated for Arabic health text has been applied here.

Writes docs/evidence/readability.json.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from importlib.metadata import version
from pathlib import Path

import textstat

from silsila.content import RELATIVE_INFO, registry

OUT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "readability.json"
EXAMPLE = {"person": "Noura", "gene": "CYP21A2", "chance": "about 5 in 10", "baseline": "about 1 in 14,000",
           "a": "Noura", "b": "Khalfan", "condition": "congenital adrenal hyperplasia", "sender": "Mariam"}
# What a relative meets, in order, on an anonymous invitation link.
RELATIVE_TEMPLATES = ("invite.anonymous", "invite.anonymity_notice", "reply.booking")
OPTIONS_TOPIC = "faq.reproductive_options"


def score(text: str, smog: bool = False) -> dict[str, float | int | None]:
    sentences = textstat.sentence_count(text)
    return {"words": textstat.lexicon_count(text), "sentences": sentences,
            "flesch_reading_ease": round(textstat.flesch_reading_ease(text), 1),
            "flesch_kincaid_grade": round(textstat.flesch_kincaid_grade(text), 1),
            "smog": round(textstat.smog_index(text), 1) if smog and sentences >= 30 else None}


def main() -> None:
    reg = registry()

    def template(tid: str) -> str:
        raw = re.sub(r"\s+", " ", reg.templates[tid]["en"]).strip()
        return raw.format(**{k: EXAMPLE[k] for k in re.findall(r"\{(\w+)\}", raw)})

    templates = {tid: template(tid) for tid in reg.templates}
    teachback = {q["id"]: " ".join([q["en"], *(o["en"] + "." for o in q["options"])]) for q in reg.teachback}
    topic = next(t for t in reg.faq if t["id"] == OPTIONS_TOPIC)
    faq_ids = sorted({p for t in reg.faq for p in t["paragraphs"]} | set(RELATIVE_INFO))

    def pooled(texts: list[str]) -> dict[str, float | int | None]:
        return score(" ".join(texts), smog=True)

    groups = {
        "approved_wording_relative_invitation": {
            "what": "Approved wording on an anonymous invitation link: " + ", ".join(RELATIVE_TEMPLATES),
            **pooled([templates[t] for t in RELATIVE_TEMPLATES])},
        "approved_wording_all_templates": {
            "what": f"All {len(templates)} approved templates (variable parts filled with the example values)",
            **pooled(list(templates.values()))},
        "comprehension_check": {
            "what": f"The {len(teachback)} comprehension questions with their answers", **pooled(list(teachback.values()))},
        "quoted_relative_information": {
            "what": "MedlinePlus paragraphs every relative is shown (quoted, not written by Silsila): " + ", ".join(RELATIVE_INFO),
            **pooled([reg.paragraphs[p].text for p in RELATIVE_INFO])},
        "quoted_reproductive_options": {
            "what": "MedlinePlus paragraphs behind the options question (quoted): " + ", ".join(topic["paragraphs"]),
            **pooled([reg.paragraphs[p].text for p in topic["paragraphs"]])},
        "quoted_all_common_questions": {
            "what": f"All {len(faq_ids)} MedlinePlus paragraphs behind the relative's page and common questions (quoted)",
            **pooled([reg.paragraphs[p].text for p in faq_ids])},
    }
    doc = {
        "benchmark": "Readability of the English text a relative can be shown",
        "generated": dt.date.today().isoformat(),
        "tool": f"textstat {version('textstat')}: Flesch Reading Ease, Flesch-Kincaid Grade Level, SMOG (pooled groups of 30+ sentences only)",
        "language": "English only. No formula was applied to the Arabic text: these formulas are defined for English, "
                    "and no readability measure validated for Arabic health text has been applied.",
        "reference_targets": {
            "text": "Patient materials are commonly recommended at a sixth grade (AMA) to eighth grade (NIH) reading level.",
            "source": "Rooney MK, et al. Readability of Patient Education Materials From High-Impact Medical Journals: "
                      "A 20-Year Analysis. J Patient Exp 2021.",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8205335/"},
        "example_values": EXAMPLE,
        "groups": groups,
        "templates": {tid: {"kind": reg.templates[tid]["kind"], **score(text)} for tid, text in templates.items()},
        "quoted_paragraphs": {p: score(reg.paragraphs[p].text) for p in faq_ids},
        "limits": [
            "Formulas count syllables, words and sentences. They do not measure whether a reader understands; the "
            "comprehension check and the pilot's usability sessions do that.",
            "Scores for single short texts (a few sentences) are unstable; the pooled group scores are the ones to read.",
            "Quoted MedlinePlus text is shown word for word and cannot be simplified without ceasing to be a quotation.",
        ],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    for name, g in groups.items():
        print(f"{name:42s} words {g['words']:5d}  FRE {g['flesch_reading_ease']:5.1f}  FK grade {g['flesch_kincaid_grade']:4.1f}  SMOG {g['smog']}")
    worst = sorted(doc["templates"].items(), key=lambda kv: -kv[1]["flesch_kincaid_grade"])[:5]
    print("hardest templates:", [(k, v["flesch_kincaid_grade"]) for k, v in worst])


if __name__ == "__main__":
    main()
