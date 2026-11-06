"""Evaluate message triage on the blind test set (data/eval/triage_testset.jsonl).

The test set was written by a separate process that never saw the rules
(see data/eval/README.md). For each label we report sensitivity, specificity
and positive predictive value with Wilson 95% intervals, overall and per
language variety, plus the safety outcomes that matter most:
  * escalation sensitivity: messages a counsellor must see (crisis, decision,
    religious, distress) that were escalated;
  * crisis-first: crisis messages whose reply starts with emergency numbers;
  * approved-only replies: replies that pass the output gate (by construction
    every reply is gated; this checks it on real inputs).

Run: cd backend && uv run python -m evals.triage_eval [--model]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from silsila.content import registry
from silsila.triage import ESCALATE, LABELS, classify, reply_for

ROOT = Path(__file__).resolve().parents[2]
TESTSET = ROOT / "data/eval/triage_testset.jsonl"
PRIVACY = ROOT / "data/eval/privacy_attacks.jsonl"
OUT = ROOT / "docs/evidence"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None, float | None]:
    if n == 0:
        return None, None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def metric(k: int, n: int) -> dict:
    p, lo, hi = wilson(k, n)
    return {"k": k, "n": n, "value": p, "ci95": [lo, hi]}


def lang_of(variety: str) -> str:
    return "ar" if variety in ("msa", "gulf") else "en"


def run(use_model: bool) -> dict:
    rows = [json.loads(line) for line in TESTSET.read_text().splitlines() if line.strip()]
    per_case = []
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    reg = registry()
    gate_failures = 0
    for r in rows:
        res = classify(r["text"], lang_of(r["variety"]), use_model=use_model)
        try:
            reply = reply_for(res, lang_of(r["variety"]))
            reg.gate(reply)
            first = reply.parts[0]["id"]
            escalated = reply.escalate
            has_emergency = any("998" in p["text"] for p in reply.parts)
        except Exception:
            gate_failures += 1
            first, escalated, has_emergency = "GATE_FAILURE", False, False
        gold = set(r["labels"])
        pred = set(res.labels)
        for scope in ("all", r["variety"]):
            for lab in LABELS:
                c = counts[(scope, lab)]
                c["tp"] += lab in gold and lab in pred
                c["fn"] += lab in gold and lab not in pred
                c["fp"] += lab not in gold and lab in pred
                c["tn"] += lab not in gold and lab not in pred
            must = bool(gold & ESCALATE)
            c = counts[(scope, "_escalation")]
            c["tp"] += must and escalated
            c["fn"] += must and not escalated
            c["fp"] += (not must) and escalated
            c["tn"] += (not must) and not escalated
            if "crisis" in gold:
                c = counts[(scope, "_crisis_first")]
                c["tp"] += first == "reply.crisis"
                c["fn"] += first != "reply.crisis"
                c = counts[(scope, "_crisis_emergency_numbers")]
                c["tp"] += has_emergency
                c["fn"] += not has_emergency
        per_case.append({"id": r["id"], "variety": r["variety"], "hard": r.get("hard", False), "text": r["text"],
                         "expected": sorted(gold), "predicted": sorted(pred), "rule_labels": sorted(res.rule_labels),
                         "model_labels": sorted(res.model_labels), "first_reply": first, "escalated": escalated,
                         "missed": sorted(gold - pred), "extra": sorted(pred - gold),
                         "error_source": ("rules" if not use_model else "rules+model") if gold != pred else ""})

    def summarise(scope: str) -> dict:
        out = {}
        for lab in list(LABELS) + ["_escalation"]:
            c = counts[(scope, lab)]
            out[lab] = {"sensitivity": metric(c["tp"], c["tp"] + c["fn"]),
                        "specificity": metric(c["tn"], c["tn"] + c["fp"]),
                        "ppv": metric(c["tp"], c["tp"] + c["fp"])}
        c = counts[(scope, "_crisis_first")]
        out["_crisis_reply_first"] = metric(c["tp"], c["tp"] + c["fn"])
        c = counts[(scope, "_crisis_emergency_numbers")]
        out["_crisis_reply_has_emergency_numbers"] = metric(c["tp"], c["tp"] + c["fn"])
        out["_human_review_reach"] = {"value": 1.0, "basis": "by design: every message enters the counsellor queue"}
        return out

    varieties = sorted({r["variety"] for r in rows})
    result = {"testset": str(TESTSET.relative_to(ROOT)), "n_messages": len(rows), "use_model": use_model,
              "gate_failures": gate_failures, "overall": summarise("all"),
              "by_variety": {v: summarise(v) for v in varieties},
              "note": "Synthetic messages written blind to the rules by an AI model; labels by that author; "
                      "not validated by native-speaking clinicians. A stress test, not a clinical validation."}

    if PRIVACY.exists():
        attacks = [json.loads(line) for line in PRIVACY.read_text().splitlines() if line.strip()]
        refused, leaks = 0, 0
        for a in attacks:
            rep = reply_for(classify(a["text"], lang_of(a["variety"]), use_model=use_model), lang_of(a["variety"]))
            ids = [p["id"] for p in rep.parts]
            refused += "reply.third_party" in ids
            # replies are built from templates and public paragraphs only; they cannot contain case data
            leaks += any(p["type"] not in ("template", "source") for p in rep.parts)
        result["privacy_prompts"] = {"n": len(attacks), "refusal_template": metric(refused, len(attacks)),
                                     "replies_containing_case_data": leaks}
    return result, per_case


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true", help="also use the configured Azure OpenAI classifier")
    args = ap.parse_args()
    result, per_case = run(args.model)
    OUT.mkdir(parents=True, exist_ok=True)
    name = "triage_rules_plus_model" if args.model else "triage_rules"
    (OUT / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    with open(OUT / f"{name}_cases.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_case[0].keys()))
        w.writeheader()
        for row in per_case:
            w.writerow({k: (";".join(v) if isinstance(v, list) else v) for k, v in row.items()})
    o = result["overall"]
    print(f"{result['n_messages']} messages, gate failures {result['gate_failures']}")
    for lab in list(LABELS) + ["_escalation"]:
        s, sp = o[lab]["sensitivity"], o[lab]["specificity"]
        if s["n"]:
            print(f"{lab:18s} sens {s['value']:.3f} [{s['ci95'][0]:.3f},{s['ci95'][1]:.3f}] n={s['n']:3d}   "
                  f"spec {sp['value']:.3f} [{sp['ci95'][0]:.3f},{sp['ci95'][1]:.3f}]")
    cf = o["_crisis_reply_first"]
    print(f"crisis reply first {cf['value']}  ({cf['k']}/{cf['n']})")
    ce = o["_crisis_reply_has_emergency_numbers"]
    print(f"crisis reply contains 998/999 {ce['value']}  ({ce['k']}/{ce['n']})")
    if "privacy_prompts" in result:
        print("privacy:", result["privacy_prompts"])


if __name__ == "__main__":
    main()
