"""Score every run present and write the evidence files.

    uv run python -m silsila_bench.report [--skip-pubmed]

Writes
  ../docs/evidence/silsila_bench.json      all metrics with 95% family-bootstrap intervals and splits
  ../docs/evidence/silsila_bench.md        Markdown section with tables (all models together)
  ../docs/evidence/logs/bench/<model>_<track>.csv   per-prompt logs (prompt, raw answer, parsed, gold, band)

Reporting rules (pre-registered): every model is listed, including those not run (with the reason);
models appear in the fixed registry order, never sorted by a result; no ranking language.
NOTE: the per-prompt logs contain the item texts. The item set is not to be published before the
challenge is judged, so do not push docs/evidence/logs/bench/ until then.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

from . import models
from .items import BENCH_DIR, TRACK_REGISTERS, build_items, family_map
from .runner import RUNS_DIR, load_records, run_path
from .score import (
    T1_METRICS, T2_METRICS, T3_METRICS, T4_METRICS, T5_METRICS, PubMed, score_t1, score_t2, score_t3,
    score_t4, score_t5, summarise,
)

EVIDENCE = BENCH_DIR.parent / "docs" / "evidence"
TRACK_TITLES = {
    "T1": "T1 free-text risk", "T2": "T2 engine as a tool", "T3": "T3 story to tree",
    "T4": "T4 language consistency (from T1)", "T5": "T5 invented sources",
}
PCT = {"no_number", "exact", "within_25pct", "off_2x", "tool_call_rate", "tool_tree_identical", "tool_question_match",
       "final_exact", "final_off_2x", "edge_precision", "edge_recall", "exact_tree", "structure_exact",
       "engine_answer_correct", "tree_in_text_only", "all_same_band", "complete_share", "answers_with_pmids", "pmid_not_found",
       "pmid_unrelated_title", "answers_with_invalid_pmid"}
LABELS = {
    "no_number": "No number", "exact": "Exact (≤5%)", "within_25pct": "Within 25%", "off_2x": "Off by ≥2x",
    "tool_call_rate": "Called the tool", "tool_tree_identical": "Tool tree = gold tree",
    "tool_question_match": "Tool question = asked question", "final_exact": "Final answer exact",
    "final_off_2x": "Final off by ≥2x", "edge_precision": "Edge precision", "edge_recall": "Edge recall",
    "exact_tree": "Exact tree", "structure_exact": "Exact structure", "engine_answer_correct": "Engine answer = gold", "tree_in_text_only": "Tree written as text, no call",
    "all_same_band": "All 4 registers same band", "mean_sd_log_p": "Mean SD of ln(p̂)",
    "complete_share": "All 4 registers gave a number", "answers_with_pmids": "Answers citing PMIDs",
    "pmids_per_answer": "PMIDs per answer", "pmid_not_found": "PMIDs not found",
    "pmid_unrelated_title": "Existing PMIDs, title unrelated", "answers_with_invalid_pmid": "Answers with a flagged PMID",
}
METRICS = {"T1": T1_METRICS, "T2": T2_METRICS, "T3": T3_METRICS, "T4": T4_METRICS, "T5": T5_METRICS}
LOG_FIELDS = ["item_id", "family_id", "family_type", "register", "qid", "locus", "prompt", "raw_answer", "parsed",
              "parse_kind", "parse_source", "gold", "band"]


def fmt(name: str, ci: dict | None) -> str:
    if not ci or ci.get("value") is None:
        return "–"
    v, lo, hi = ci["value"], ci["lo"], ci["hi"]
    if name in PCT:
        return f"{100 * v:.1f}% ({100 * lo:.1f}–{100 * hi:.1f})"
    return f"{v:.2f} ({lo:.2f}–{hi:.2f})"


def _write_log(path: Path, rows: list[dict], extra: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = LOG_FIELDS + [f for f in extra if f not in LOG_FIELDS]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in r.items()})


def score_model(name: str, runs_dir: Path, fams, pubmed: PubMed | None, log_dir: Path | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    t1_rows = None
    for track in ("T1", "T2", "T3", "T5"):
        recs = load_records(run_path(name, track, runs_dir))
        expected = len(build_items(track))
        ok = {k: r for k, r in recs.items() if not r.get("error")}
        if not ok:
            out[track] = {"status": "not run", "expected": expected, "done": 0, "errors": len(recs)}
            continue
        if track == "T1":
            rows = score_t1(ok, fams)
            t1_rows = rows
        elif track == "T2":
            rows = score_t2(ok, fams)
        elif track == "T3":
            rows = score_t3(ok, fams)
        else:
            if pubmed is None:
                out[track] = {"status": "not scored (PubMed lookups skipped)", "expected": expected, "done": len(ok)}
                continue
            rows = score_t5(ok, fams, pubmed)
        tokens = {"prompt": sum(t.get("usage", {}).get("prompt_tokens", 0) for r in ok.values() for t in r["turns"]),
                  "completion": sum(t.get("usage", {}).get("completion_tokens", 0) for r in ok.values() for t in r["turns"])}
        splits = ("register", "family_type") if track != "T5" else ("family_type",)
        out[track] = {"status": "complete" if len(ok) == expected else "partial", "expected": expected,
                      "done": len(ok), "errors": len(recs) - len(ok), "tokens": tokens,
                      "metrics": summarise(rows, METRICS[track], splits)}
        if track == "T5":
            out[track]["flagged_for_review"] = [
                {"item_id": r["item_id"], **{k: x[k] for k in ("pmid", "exists", "title", "keyword_hits")}}
                for r in rows for x in r["refs"] if x["flag_for_review"]]
        if log_dir is not None:
            extra = {"T1": ["first_in_full_text", "is_range", "finish_reason", "parsed_text"],
                     "T2": ["n_tool_calls", "n_tool_ok", "n_tree_identical", "n_question_match", "tool_value_last"],
                     "T3": ["tree_submitted", "tree_valid", "gene_ok", "identical", "structure_identical", "edges_tp",
                            "edges_pred", "edges_gold", "engine_correct", "answers", "tree_error", "tree_in_text",
                            "text_tree_structure_identical", "text_tree_identical", "text_tree_edge_recall"],
                     "T5": ["n_refs", "n_exist", "n_related", "refs"]}[track]
            _write_log(log_dir / f"{name}_{track}.csv", rows, extra)
    if t1_rows:
        t4 = score_t4(t1_rows)
        out["T4"] = {"status": "computed from T1", "metrics": summarise(t4, T4_METRICS, ("family_type",))}
        if log_dir is not None:
            _write_log(log_dir / f"{name}_T4.csv", t4, ["n_registers", "complete", "same_band", "bands", "sd_log", "log_range"])
    else:
        out["T4"] = {"status": "not run"}
    return out


def markdown(result: dict[str, Any]) -> str:
    L: list[str] = []
    L.append("## Silsila-Bench: where language models can be used safely inside Silsila")
    L.append("")
    L.append("Pre-registered in `bench_llm/PREREGISTRATION.md`; changes in `bench_llm/AMENDMENTS.md`. "
             "150 synthetic families (fictional people), gold answers from the exact Silsila engine. "
             "All models are reported together in a fixed order; this is not a ranking. "
             "Values are shares with 95% intervals from a bootstrap over families. "
             "Band shares exclude answers with no number, which are reported separately.")
    L.append("")
    L.append(f"Generated {result['generated']}.")
    L.append("")
    L.append("### Models")
    L.append("")
    L.append("| Model | Licence | Status |")
    L.append("|---|---|---|")
    for name, m in result["models"].items():
        L.append(f"| {m['label']} | {m['licence']} | {m['status']} |")
    for track in ("T1", "T2", "T3", "T4", "T5"):
        mets = list(METRICS[track])
        L.append("")
        L.append(f"### {TRACK_TITLES[track]}")
        L.append("")
        L.append("| Model | Items | " + " | ".join(LABELS[x] for x in mets) + " |")
        L.append("|---|---|" + "---|" * len(mets))
        for name, m in result["models"].items():
            t = m["tracks"].get(track, {})
            if "metrics" not in t:
                reason = m.get("reason") or t.get("status", "not run")
                L.append(f"| {m['label']} | not run | {reason} |" + " |" * (len(mets) - 1))
                continue
            ov = t["metrics"]["overall"]
            L.append(f"| {m['label']} | {ov['n_items']} | " + " | ".join(fmt(x, ov.get(x)) for x in mets) + " |")
        key = {"T1": "exact", "T2": "final_exact", "T3": "engine_answer_correct", "T4": "all_same_band", "T5": "pmid_not_found"}[track]
        for split in ("register", "family_type"):
            levels = sorted({lv for m in result["models"].values()
                             for lv in m["tracks"].get(track, {}).get("metrics", {}).get(f"by_{split}", {})})
            if not levels:
                continue
            L.append("")
            L.append(f"{LABELS[key]}, by {split.replace('_', ' ')}:")
            L.append("")
            L.append("| Model | " + " | ".join(levels) + " |")
            L.append("|---|" + "---|" * len(levels))
            for name, m in result["models"].items():
                by = m["tracks"].get(track, {}).get("metrics", {}).get(f"by_{split}")
                if not by:
                    L.append(f"| {m['label']} | " + " | ".join("not run" for _ in levels) + " |")
                    continue
                L.append(f"| {m['label']} | " + " | ".join(fmt(key, by.get(lv, {}).get(key)) for lv in levels) + " |")
    L.append("")
    L.append("Limitations: synthetic families; Arabic, Gulf Arabic and Arabizi templates written without "
             "native-speaker review; one sample per prompt at temperature 0; PMID relatedness is a keyword check "
             "and every flagged case is reviewed by the team.")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-dir", default=str(RUNS_DIR))
    ap.add_argument("--out-dir", default=str(EVIDENCE))
    ap.add_argument("--skip-pubmed", action="store_true", help="do not query NCBI (T5 left unscored)")
    ap.add_argument("--models", default=None, help="comma-separated subset (default: all registered)")
    a = ap.parse_args(argv)
    runs_dir, out_dir = Path(a.runs_dir), Path(a.out_dir)
    fams = family_map()
    pubmed = None if a.skip_pubmed else PubMed()
    names = a.models.split(",") if a.models else [n for n in models.MODELS if n != "jais-3-7b-mlx"
                                                   or (runs_dir / n).exists()]
    prereg = (BENCH_DIR / "PREREGISTRATION.md").read_bytes()
    result: dict[str, Any] = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "preregistration_sha256": hashlib.sha256(prereg).hexdigest(),
        "amendments_file": (BENCH_DIR / "AMENDMENTS.md").exists(),
        "python": platform.python_version(),
        "items": {t: len(build_items(t)) for t in ("T1", "T2", "T3", "T5")},
        "registers": {t: list(v) for t, v in TRACK_REGISTERS.items()},
        "families": {"total": len(fams), "by_type": {t: sum(f.family_type == t for f in fams.values())
                                                     for t in ("no_loop", "one_loop", "multiple")}},
        "models": {},
    }
    for n in names:
        spec = models.get(n)
        tracks = score_model(n, runs_dir, fams, pubmed, out_dir / "logs" / "bench")
        statuses = {t: v.get("status") for t, v in tracks.items()}
        if all(s in ("not run",) for k, s in statuses.items() if k != "T4"):
            status, reason = "not run", spec.not_run_reason or "no results yet"
        else:
            status = "; ".join(f"{t} {v.get('status')} ({v.get('done', '-')}/{v.get('expected', '-')})"
                               for t, v in tracks.items() if t != "T4")
            reason = None
        result["models"][n] = {"label": spec.label, "model_id": spec.model_id, "provider": spec.provider,
                               "licence": spec.licence, "status": status, "reason": reason, "tracks": tracks}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "silsila_bench.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    (out_dir / "silsila_bench.md").write_text(markdown(result))
    print(f"wrote {out_dir / 'silsila_bench.json'} and {out_dir / 'silsila_bench.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
