"""Scoring, fixed before runs (PREREGISTRATION.md "Scoring").

* Bands for a returned probability p_hat against the exact p: exact (relative error <= 5%), close
  (<= 25%), off by 2x or more (p_hat/p >= 2 or <= 0.5); answers between 25% and 2x are "other".
  "No number" is reported separately and never counted as right or wrong (it is excluded from the
  denominators of the band shares).
* T2: tool-call rate, share of tool calls whose tree is identical to the gold tree, final answer exact.
* T3: edge precision and recall (parent-child and couple links, micro-averaged), exact-tree rate, and the
  share of (tree, question) pairs for which the engine's answer on the model's tree equals the gold answer.
* T4 (from T1): share of family-questions whose four registers' numbers are all in the same band, and
  the spread (SD) of log(p_hat) across the four registers.
* T5: PMIDs checked against NCBI E-utilities (existence, title keyword overlap; flagged cases go to the
  team for review).
* 95% intervals: percentile bootstrap over families (families are the resampling unit), 2,000 resamples.
* Splits: overall, by register and by family type.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
import numpy as np

from . import names as N
from .items import BENCH_DIR, Family, family_map
from .parse import first_in_full_text, parse_probability
from .tools import compare_trees, engine_answer_on_tree, parse_arguments, tree_from_args

BOOT_B = 2000
BOOT_SEED = 20261114
EQUAL_TOL = 1e-6   # "engine answer equals the gold answer" (relative)


# ------------------------------------------------------------------ bands ---
def band(p_hat: float | None, p: float) -> str:
    if p_hat is None:
        return "no_number"
    if p <= 0:
        return "exact" if p_hat == 0 else "off2x"
    rel = abs(p_hat - p) / p
    if rel <= 0.05 + 1e-12:
        return "exact"
    if rel <= 0.25 + 1e-12:
        return "close"
    ratio = p_hat / p
    if ratio >= 2 or ratio <= 0.5:
        return "off2x"
    return "other"


def rel_equal(a: float, b: float, tol: float = EQUAL_TOL) -> bool:
    return abs(a - b) <= tol * max(abs(b), 1e-300)


# -------------------------------------------------------------- bootstrap ---
def bootstrap_ratio(groups: dict[str, tuple[float, float]], B: int = BOOT_B, seed: int = BOOT_SEED) -> dict[str, Any]:
    """Ratio of sums with a percentile bootstrap over groups (families)."""
    keys = sorted(groups)
    num = np.array([groups[k][0] for k in keys], dtype=float)
    den = np.array([groups[k][1] for k in keys], dtype=float)
    if not keys or den.sum() <= 0:
        return {"value": None, "lo": None, "hi": None, "num": float(num.sum()), "den": float(den.sum()), "n_families": len(keys)}
    value = float(num.sum() / den.sum())
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(keys), np.full(len(keys), 1 / len(keys)), size=B).astype(float)
    dn = w @ den
    ok = dn > 0
    stats = (w @ num)[ok] / dn[ok]
    lo, hi = (np.percentile(stats, [2.5, 97.5]) if len(stats) else (np.nan, np.nan))
    return {"value": value, "lo": float(lo), "hi": float(hi), "num": float(num.sum()), "den": float(den.sum()),
            "n_families": len(keys)}


Metric = tuple[Callable[[dict], float], Callable[[dict], float]]


def summarise(rows: list[dict], metrics: dict[str, Metric], splits: Iterable[str] = ("register", "family_type")) -> dict:
    """{"overall": {metric: ci}, "by_register": {reg: {...}}, "by_family_type": {...}}"""

    def one(rs: list[dict]) -> dict:
        out = {"n_items": len(rs)}
        for name, (fn_num, fn_den) in metrics.items():
            g: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
            for r in rs:
                g[r["family_id"]][0] += fn_num(r)
                g[r["family_id"]][1] += fn_den(r)
            out[name] = bootstrap_ratio({k: (v[0], v[1]) for k, v in g.items()})
        return out

    res: dict[str, Any] = {"overall": one(rows)}
    for s in splits:
        levels = sorted({r[s] for r in rows if r.get(s) is not None})
        res[f"by_{s}"] = {lv: one([r for r in rows if r.get(s) == lv]) for lv in levels}
    return res


def _b(x: bool) -> float:
    return 1.0 if x else 0.0


# ---------------------------------------------------------------- per item ---
def _gold(fam: Family, qid: str) -> float:
    return fam.question(qid).gold


def score_t1(records: dict[str, dict], fams: dict[str, Family] | None = None, track: str = "T1") -> list[dict]:
    fams = fams or family_map()
    rows = []
    for r in records.values():
        if r.get("error"):
            continue
        fam = fams[r["family_id"]]
        gold = _gold(fam, r["qid"])
        p = parse_probability(r.get("final_content"))
        rows.append({
            "item_id": r["item_id"], "track": track, "family_id": r["family_id"], "family_type": r["family_type"],
            "register": r["register"], "qid": r["qid"], "locus": r["locus"], "gold": gold,
            "parsed": p.value, "parse_kind": p.kind, "parse_source": p.source, "parsed_text": p.text,
            "is_range": p.is_range, "band": band(p.value, gold),
            "first_in_full_text": first_in_full_text(r.get("final_content")),
            "finish_reason": (r["turns"][-1]["finish_reason"] if r.get("turns") else None),
            "raw_answer": r.get("final_content") or "",
            "prompt": r["messages"][-1]["content"] if r.get("messages") else "",
        })
    return rows


T1_METRICS: dict[str, Metric] = {
    "no_number": (lambda r: _b(r["band"] == "no_number"), lambda r: 1.0),
    "exact": (lambda r: _b(r["band"] == "exact"), lambda r: _b(r["band"] != "no_number")),
    "within_25pct": (lambda r: _b(r["band"] in ("exact", "close")), lambda r: _b(r["band"] != "no_number")),
    "off_2x": (lambda r: _b(r["band"] == "off2x"), lambda r: _b(r["band"] != "no_number")),
}


def _question_dict(fam: Family, qid: str, use_ids: bool = True) -> dict:
    q = fam.question(qid)
    if q.type == "carrier":
        return {"type": "carrier", "person": q.person}
    return {"type": "child_affected", "couple": list(q.couple)}  # type: ignore[arg-type]


def score_t2(records: dict[str, dict], fams: dict[str, Family] | None = None) -> list[dict]:
    fams = fams or family_map()
    rows = []
    for r in records.values():
        if r.get("error"):
            continue
        fam = fams[r["family_id"]]
        resolve = fam.name_index()
        gold_tree = tree_from_args(fam.gold_tree(), resolve)
        gold = _gold(fam, r["qid"])
        n_calls = len(r.get("tool_args") or [])
        identical = 0
        q_match = 0
        tool_ok = 0
        for args, res in zip(r.get("tool_args") or [], r.get("tool_results") or []):
            try:
                a = parse_arguments(args)
                t = tree_from_args(a, resolve)
                identical += compare_trees(t, gold_tree)["identical"]
                qa = a.get("question") or {}
                gq = _question_dict(fam, r["qid"])
                if isinstance(qa, dict) and str(qa.get("type", "")).casefold() == gq["type"]:
                    if gq["type"] == "carrier":
                        q_match += resolve.get(N.normalise(str(qa.get("person"))), None) == gq["person"]
                    else:
                        got = {resolve.get(N.normalise(str(x))) for x in (qa.get("couple") or [])}
                        q_match += got == set(gq["couple"])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                pass
            tool_ok += "probability" in (res or {})
        p = parse_probability(r.get("final_content"))
        tool_values = [x["probability"] for x in (r.get("tool_results") or []) if "probability" in (x or {})]
        rows.append({
            "item_id": r["item_id"], "track": "T2", "family_id": r["family_id"], "family_type": r["family_type"],
            "register": r["register"], "qid": r["qid"], "locus": r["locus"], "gold": gold,
            "n_tool_calls": n_calls, "n_tool_ok": tool_ok, "n_tree_identical": identical, "n_question_match": q_match,
            "tool_value_last": tool_values[-1] if tool_values else None,
            "parsed": p.value, "parse_kind": p.kind, "parse_source": p.source, "band": band(p.value, gold),
            "raw_answer": r.get("final_content") or "",
            "prompt": r["messages"][-1]["content"] if r.get("messages") else "",
        })
    return rows


T2_METRICS: dict[str, Metric] = {
    "tool_call_rate": (lambda r: _b(r["n_tool_calls"] > 0), lambda r: 1.0),
    "tool_tree_identical": (lambda r: float(r["n_tree_identical"]), lambda r: float(r["n_tool_calls"])),
    "tool_question_match": (lambda r: float(r["n_question_match"]), lambda r: float(r["n_tool_calls"])),
    "no_number": (lambda r: _b(r["band"] == "no_number"), lambda r: 1.0),
    "final_exact": (lambda r: _b(r["band"] == "exact"), lambda r: _b(r["band"] != "no_number")),
    "final_off_2x": (lambda r: _b(r["band"] == "off2x"), lambda r: _b(r["band"] != "no_number")),
}


def score_t3(records: dict[str, dict], fams: dict[str, Family] | None = None) -> list[dict]:
    fams = fams or family_map()
    rows = []
    for r in records.values():
        if r.get("error"):
            continue
        fam = fams[r["family_id"]]
        resolve = fam.name_index()
        gold_tree = tree_from_args(fam.gold_tree(), resolve)
        row = {
            "item_id": r["item_id"], "track": "T3", "family_id": r["family_id"], "family_type": r["family_type"],
            "register": r["register"], "locus": r["locus"], "tree_submitted": False, "tree_valid": False,
            "identical": False, "structure_identical": False, "edges_tp": 0, "edges_pred": 0,
            "edges_gold": len(_gold_edges(gold_tree)), "engine_correct": 0, "engine_exact_band": 0,
            "tree_error": None, "answers": {}, "gene_ok": None,
            "raw_answer": json.dumps(r.get("tool_args")[-1] if r.get("tool_args") else None, ensure_ascii=False),
            "prompt": r["messages"][-1]["content"] if r.get("messages") else "",
        }
        args = (r.get("tool_args") or [None])[-1]
        if args:
            row["tree_submitted"] = True
            try:
                a = parse_arguments(args)
                # T3 measures the family structure; the gene is recorded but does not change the comparison
                row["gene_ok"] = str(a.get("gene") or "").strip().upper() == fam.locus.upper()
                a = {**a, "gene": fam.locus}
                t = tree_from_args(a, resolve)
                cmp = compare_trees(t, gold_tree)
                row.update({k: cmp[k] for k in ("identical", "structure_identical", "edges_tp", "edges_pred", "edges_gold")})
                t.pedigree()
                row["tree_valid"] = True
                for qid in ("a", "b"):
                    try:
                        v = engine_answer_on_tree(t, _question_dict(fam, qid), resolve)
                    except Exception as e:  # missing person, invalid evidence ... -> not correct
                        row["answers"][qid] = f"error: {e}"
                        continue
                    row["answers"][qid] = v
                    row["engine_correct"] += rel_equal(v, _gold(fam, qid))
                    row["engine_exact_band"] += band(v, _gold(fam, qid)) == "exact"
            except Exception as e:
                row["tree_error"] = f"{e.__class__.__name__}: {e}"
        else:
            # Secondary diagnostic only (not a pre-registered T3 metric): the model wrote the tree as JSON
            # text instead of calling the function. Recorded so this failure mode is visible in the logs.
            row["tree_in_text"] = False
            from .clients import _json_objects
            for obj in reversed(_json_objects(r.get("final_content") or "")):
                if isinstance(obj.get("people"), list):
                    row["tree_in_text"] = True
                    try:
                        t = tree_from_args({**obj, "gene": fam.locus}, resolve)
                        cmp = compare_trees(t, gold_tree)
                        row["text_tree_structure_identical"] = cmp["structure_identical"]
                        row["text_tree_identical"] = cmp["identical"]
                        row["text_tree_edge_recall"] = cmp["edges_tp"] / max(cmp["edges_gold"], 1)
                    except Exception as e:
                        row["text_tree_error"] = f"{e.__class__.__name__}: {e}"
                    break
        rows.append(row)
    return rows


def _gold_edges(tree) -> set:
    from .tools import canonical
    c = canonical(tree)
    return c["parent_child"] | c["couples"]


T3_METRICS: dict[str, Metric] = {
    "tool_call_rate": (lambda r: _b(r["tree_submitted"]), lambda r: 1.0),
    "edge_precision": (lambda r: float(r["edges_tp"]), lambda r: float(r["edges_pred"])),
    "edge_recall": (lambda r: float(r["edges_tp"]), lambda r: float(r["edges_gold"])),
    "exact_tree": (lambda r: _b(r["identical"]), lambda r: 1.0),
    "structure_exact": (lambda r: _b(r["structure_identical"]), lambda r: 1.0),
    "engine_answer_correct": (lambda r: float(r["engine_correct"]), lambda r: 2.0),
    "tree_in_text_only": (lambda r: _b(bool(r.get("tree_in_text"))), lambda r: 1.0),   # diagnostic (AMENDMENTS A6)
}


def score_t4(t1_rows: list[dict]) -> list[dict]:
    by: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for r in t1_rows:
        by[(r["family_id"], r["qid"])][r["register"]] = r
    rows = []
    for (fid, qid), regs in sorted(by.items()):
        any_r = next(iter(regs.values()))
        complete = len(regs) == 4 and all(x["parsed"] is not None for x in regs.values())
        bands = {k: v["band"] for k, v in regs.items()}
        logs = [math.log(v["parsed"]) for v in regs.values() if v["parsed"] is not None and v["parsed"] > 0]
        sd = float(np.std(logs, ddof=1)) if complete and len(logs) == 4 else None
        rows.append({
            "item_id": f"T4:{fid}:{qid}", "track": "T4", "family_id": fid, "family_type": any_r["family_type"],
            "register": None, "qid": qid, "n_registers": len(regs), "complete": complete,
            "same_band": complete and len(set(bands.values())) == 1, "bands": bands, "sd_log": sd,
            "log_range": (max(logs) - min(logs)) if sd is not None else None,
        })
    return rows


T4_METRICS: dict[str, Metric] = {
    "all_same_band": (lambda r: _b(r["same_band"]), lambda r: _b(r["complete"])),
    "mean_sd_log_p": (lambda r: r["sd_log"] or 0.0, lambda r: _b(r["sd_log"] is not None)),
    "complete_share": (lambda r: _b(r["complete"]), lambda r: 1.0),
}


# --------------------------------------------------------------------- T5 ---
_PMID_RES = [
    re.compile(r"PMID\s*[:#]?\s*(\d{4,9})", re.I),
    re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{4,9})", re.I),
    re.compile(r"PubMed\s*(?:ID)?\s*[:#]?\s*(\d{4,9})", re.I),
    re.compile(r"ncbi\.nlm\.nih\.gov/pubmed/(\d{4,9})", re.I),
]
STOP = set("""a an and are as at be by for from in into is of on or the to with without among between study
analysis report case cases patients patient population review using based new its their this that these""".split())
TOPIC = {
    "HBB": {"thalassemia", "thalassaemia", "sickle", "hemoglobin", "haemoglobin", "hbb", "hemoglobinopathy",
            "hemoglobinopathies", "haemoglobinopathies", "globin", "anemia", "anaemia"},
    "CYP21A2": {"adrenal", "hyperplasia", "cyp21a2", "21-hydroxylase", "hydroxylase", "steroid", "cah"},
    "SMN1": {"spinal", "muscular", "atrophy", "smn1", "smn2", "sma", "motor", "neuron"},
}
GENERAL = {"consanguineous", "consanguinity", "cousin", "cousins", "inbreeding", "carrier", "carriers", "recessive",
           "premarital", "screening", "emirati", "emirates", "uae", "arab", "arabs", "pedigree", "kinship", "genetic",
           "counseling", "counselling", "hardy-weinberg", "heterozygote", "heterozygotes", "inherited", "mendelian"}


def extract_pmids(text: str | None) -> list[tuple[str, str]]:
    """(pmid, surrounding text) in order of first citation."""
    t = text or ""
    seen: dict[str, str] = {}
    for rx in _PMID_RES:
        for m in rx.finditer(t):
            pm = m.group(1)
            if pm not in seen:
                seen[pm] = t[max(0, m.start() - 250): m.end() + 50]
    order = sorted(seen, key=lambda k: t.find(k))
    return [(k, seen[k]) for k in order]


def _tokens(s: str) -> set[str]:
    toks = re.findall(r"[a-z0-9][a-z0-9\-]+", s.casefold())
    return {w.rstrip("s") if len(w) > 4 else w for w in toks if w not in STOP}


def related(title: str, claim: str, locus: str) -> tuple[bool, list[str]]:
    """Keyword overlap between a paper title and (claim context + topic keywords)."""
    tt = _tokens(title)
    keys = {w.rstrip("s") if len(w) > 4 else w for w in TOPIC[locus] | GENERAL}
    claim_words = {w for w in _tokens(claim) if len(w) >= 5}
    hits = sorted(tt & (keys | claim_words))
    return bool(hits), hits


class PubMed:
    """NCBI E-utilities esummary lookups with an on-disk cache. Free public API; no model calls."""

    URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    def __init__(self, cache_path: Path | None = None, client: httpx.Client | None = None,
                 api_key: str | None = None, min_interval: float | None = None):
        self.cache_path = cache_path or BENCH_DIR / ".cache" / "pubmed_esummary.json"
        self.cache: dict[str, dict] = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {}
        self.client = client or httpx.Client(timeout=30.0)
        self.api_key = api_key if api_key is not None else os.environ.get("NCBI_API_KEY")
        self.min_interval = min_interval if min_interval is not None else (0.11 if self.api_key else 0.34)
        self._last = 0.0

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=0, sort_keys=True))

    def lookup(self, pmids: Iterable[str]) -> dict[str, dict]:
        want = sorted({p for p in pmids if p not in self.cache})
        for i in range(0, len(want), 200):
            batch = want[i:i + 200]
            params = {"db": "pubmed", "id": ",".join(batch), "retmode": "json", "tool": "silsila-bench"}
            if self.api_key:
                params["api_key"] = self.api_key
            for attempt in range(5):
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
                try:
                    resp = self.client.get(self.URL, params=params)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise httpx.HTTPStatusError("retry", request=resp.request, response=resp)
                    resp.raise_for_status()
                    data = resp.json().get("result", {})
                    break
                except (httpx.HTTPError, ValueError):
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
            for pm in batch:
                d = data.get(pm)
                if isinstance(d, dict) and not d.get("error") and d.get("title"):
                    self.cache[pm] = {"exists": True, "title": d["title"], "pubdate": d.get("pubdate", ""),
                                      "source": d.get("source", "")}
                else:
                    self.cache[pm] = {"exists": False, "title": "", "error": (d or {}).get("error", "not found")}
        if want:
            self._save()
        return {p: self.cache[p] for p in pmids if p in self.cache}


def score_t5(records: dict[str, dict], fams: dict[str, Family] | None = None, pubmed: PubMed | None = None) -> list[dict]:
    fams = fams or family_map()
    found = {r["item_id"]: extract_pmids(r.get("final_content")) for r in records.values() if not r.get("error")}
    all_ids = {p for v in found.values() for p, _ in v}
    info = (pubmed or PubMed()).lookup(all_ids) if all_ids else {}
    rows = []
    for r in records.values():
        if r.get("error"):
            continue
        fam = fams[r["family_id"]]
        refs = []
        for pm, ctx in found[r["item_id"]]:
            meta = info.get(pm, {"exists": False, "title": ""})
            rel, hits = related(meta.get("title", ""), ctx, fam.locus) if meta.get("exists") else (False, [])
            refs.append({"pmid": pm, "exists": meta.get("exists", False), "title": meta.get("title", ""),
                         "related": rel, "keyword_hits": hits, "flag_for_review": not (meta.get("exists") and rel),
                         "context": ctx})
        gold = _gold(fam, r["qid"])
        p = parse_probability(r.get("final_content"))
        rows.append({
            "item_id": r["item_id"], "track": "T5", "family_id": r["family_id"], "family_type": r["family_type"],
            "register": r["register"], "qid": r["qid"], "gold": gold, "parsed": p.value, "band": band(p.value, gold),
            "n_refs": len(refs), "n_exist": sum(x["exists"] for x in refs),
            "n_related": sum(x["exists"] and x["related"] for x in refs), "refs": refs,
            "raw_answer": r.get("final_content") or "", "prompt": r["messages"][-1]["content"] if r.get("messages") else "",
        })
    return rows


T5_METRICS: dict[str, Metric] = {
    "answers_with_pmids": (lambda r: _b(r["n_refs"] > 0), lambda r: 1.0),
    "pmids_per_answer": (lambda r: float(r["n_refs"]), lambda r: 1.0),
    "pmid_not_found": (lambda r: float(r["n_refs"] - r["n_exist"]), lambda r: float(r["n_refs"])),
    "pmid_unrelated_title": (lambda r: float(r["n_exist"] - r["n_related"]), lambda r: float(r["n_exist"])),
    "answers_with_invalid_pmid": (lambda r: _b(r["n_refs"] > r["n_related"]), lambda r: _b(r["n_refs"] > 0)),
}
