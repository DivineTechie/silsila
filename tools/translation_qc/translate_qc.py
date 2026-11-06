"""Multi-system translation check for patient-facing Arabic text.

No single machine translation is trusted. For each quoted MedlinePlus
paragraph this compares independent translations and flags any paragraph a
native-speaking clinician must look at first:

  System A  Claude (Anthropic), with its own back-translation, already stored in
            data/content/translations/ar/medlineplus.json
  System B  Helsinki-NLP/opus-mt-tc-big-en-ar, a dedicated English->Arabic
            neural MT model run locally (CC-BY 4.0)
  System C  Azure AI Translator, if AZURE_TRANSLATOR_KEY and
            AZURE_TRANSLATOR_REGION are set (optional)

Checks per paragraph
  * every number in the English appears in each translation;
  * cross-lingual meaning similarity (LaBSE, Apache-2.0) between the English
    and each translation;
  * agreement between systems (LaBSE similarity of the Arabic versions);
  * the translator's own fidelity note (System A).
Thresholds are screening heuristics to prioritise human review, not proof
of correctness. Output: qc_report.json and review_list.md next to the
translations, and a 'qc' block per paragraph in medlineplus.json.

Run: cd tools/translation_qc && uv run python translate_qc.py
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TDIR = ROOT / "data/content/translations/ar"
WORK = TDIR / "_to_translate.json"
STORE = TDIR / "medlineplus.json"
MT_MODEL = "Helsinki-NLP/opus-mt-tc-big-en-ar"
SIM_MODEL = "sentence-transformers/LaBSE"
SIM_FLOOR = 0.80        # English vs Arabic meaning similarity below this is flagged
AGREE_FLOOR = 0.85      # Arabic vs Arabic agreement between systems below this is flagged

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def numbers(text: str) -> set[str]:
    """The set of numbers in a text. A set, not a count: an Arabic translation
    may repeat a number when it adds the English term in brackets."""
    return set(re.findall(r"\d+(?:[.,]\d+)?", text.translate(AR_DIGITS).replace(",", "")))


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def system_b(texts: list[str]) -> list[str]:
    from transformers import MarianMTModel, MarianTokenizer

    tok = MarianTokenizer.from_pretrained(MT_MODEL)
    model = MarianMTModel.from_pretrained(MT_MODEL)
    prefix = ">>ara<< " if ">>ara<<" in tok.get_vocab() else ""
    out = []
    for t in texts:
        sents = sentences(t)
        batch = tok([prefix + s for s in sents], return_tensors="pt", padding=True, truncation=True)
        gen = model.generate(**batch, num_beams=4, max_new_tokens=400)
        out.append(" ".join(tok.batch_decode(gen, skip_special_tokens=True)))
    return out


def system_c(texts: list[str]) -> list[str] | None:
    key, region = os.environ.get("AZURE_TRANSLATOR_KEY"), os.environ.get("AZURE_TRANSLATOR_REGION")
    if not (key and region):
        return None
    out = []
    for t in texts:
        req = urllib.request.Request(
            "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=en&to=ar",
            data=json.dumps([{"Text": t}]).encode(), method="POST",
            headers={"Ocp-Apim-Subscription-Key": key, "Ocp-Apim-Subscription-Region": region,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            out.append(json.loads(r.read())[0]["translations"][0]["text"])
    return out


def load_env() -> None:
    """Read AZURE_TRANSLATOR_* from tools/translation_qc/.env if present (git-ignored)."""
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    load_env()
    work = json.loads(WORK.read_text())
    store = json.loads(STORE.read_text())
    ids = [w["id"] for w in work]
    en = [w["en"] for w in work]
    a = [store["paragraphs"][i]["ar"] for i in ids]
    print("System B (local MT) ...")
    b = system_b(en)
    c = system_c(en)
    print("System C (Azure Translator):", "used" if c else "not configured")

    from sentence_transformers import SentenceTransformer

    sim = SentenceTransformer(SIM_MODEL)
    E = sim.encode(en, normalize_embeddings=True)
    A = sim.encode(a, normalize_embeddings=True)
    B = sim.encode(b, normalize_embeddings=True)
    C = sim.encode(c, normalize_embeddings=True) if c else None

    report, flagged = [], []
    for k, pid in enumerate(ids):
        n_en = numbers(en[k])
        entry = {
            "id": pid,
            "similarity_en_vs": {"claude": float(E[k] @ A[k]), "opus_mt": float(E[k] @ B[k])},
            "agreement": {"claude_vs_opus_mt": float(A[k] @ B[k])},
            "numbers_ok": {"claude": numbers(a[k]) == n_en, "opus_mt": numbers(b[k]) == n_en},
            "fidelity_note": store["paragraphs"][pid].get("fidelity_note", ""),
            "opus_mt_ar": b[k],
        }
        if C is not None:
            entry["similarity_en_vs"]["azure"] = float(E[k] @ C[k])
            entry["agreement"]["claude_vs_azure"] = float(A[k] @ C[k])
            entry["numbers_ok"]["azure"] = numbers(c[k]) == n_en
            entry["azure_ar"] = c[k]
        flags = []
        if not entry["numbers_ok"]["claude"]:
            flags.append("numbers differ from English")
        if entry["similarity_en_vs"]["claude"] < SIM_FLOOR:
            flags.append(f"meaning similarity {entry['similarity_en_vs']['claude']:.2f} < {SIM_FLOOR}")
        if min(entry["agreement"].values()) < AGREE_FLOOR:
            flags.append(f"systems disagree ({min(entry['agreement'].values()):.2f} < {AGREE_FLOOR})")
        if entry["fidelity_note"]:
            flags.append("translator noted a fidelity issue")
        entry["flags"] = flags
        entry["status"] = "review_first" if flags else "consistent_across_systems"
        report.append(entry)
        store["paragraphs"][pid]["qc"] = {k2: v for k2, v in entry.items() if k2 not in ("id",)}
        if flags:
            flagged.append(entry)

    store["meta"]["qc"] = {"systems": ["Claude (Anthropic)", MT_MODEL] + (["Azure AI Translator"] if c else []),
                           "similarity_model": SIM_MODEL, "sim_floor": SIM_FLOOR, "agree_floor": AGREE_FLOOR,
                           "paragraphs": len(ids), "flagged_for_first_review": len(flagged),
                           "note": "Screening heuristics to order human review. Every paragraph still needs "
                                   "native clinical review before use with patients."}
    STORE.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n")
    (TDIR / "qc_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    lines = ["# Arabic translation review list", "",
             f"{len(flagged)} of {len(ids)} paragraphs are flagged for first review. All {len(ids)} still need native "
             "clinical review; flags only set the order.", ""]
    for e in sorted(flagged, key=lambda e: e["similarity_en_vs"]["claude"]):
        w = work[ids.index(e["id"])]
        lines += [f"## {e['id']}", f"Flags: {'; '.join(e['flags'])}", "", f"**English:** {w['en']}", "",
                  f"**Claude:** {store['paragraphs'][e['id']]['ar']}", "", f"**opus-mt:** {e['opus_mt_ar']}", ""]
        if "azure_ar" in e:
            lines += [f"**Azure:** {e['azure_ar']}", ""]
    (TDIR / "review_list.md").write_text("\n".join(lines) + "\n")
    sims = [e["similarity_en_vs"]["claude"] for e in report]
    print(f"flagged {len(flagged)}/{len(ids)}; Claude EN-AR similarity min {min(sims):.3f} median "
          f"{sorted(sims)[len(sims)//2]:.3f}; numbers ok {sum(e['numbers_ok']['claude'] for e in report)}/{len(ids)}")


if __name__ == "__main__":
    main()
