"""Rough token and GPU-hour estimates for the full pre-registered run (no model calls).

    uv run python -m silsila_bench.estimate [--h100-price 3.95]

Prompt tokens are estimated from the actual prompts (characters per token: English 4.0, Arabizi 3.5,
Arabic script 3.0). Output tokens per request use each model's `est_output_tokens` (reasoning models
think at length; Jais 3 and K2-Think-V2 default to high reasoning effort). Throughput figures are
assumed aggregate decode rates for vLLM at high concurrency and are the main uncertainty: treat the
results as order-of-magnitude planning numbers and check the first 50 items' real token counts and
wall time before launching the rest.
"""

from __future__ import annotations

import argparse
import json

from . import models
from .items import build_items, family_map
from .prompts import build_messages, tools_for

CHARS_PER_TOKEN = {"en": 4.0, "arabizi": 3.5, "msa": 3.0, "gulf": 3.0}
REQUESTS_PER_ITEM = {"T1": 1.0, "T2": 2.2, "T3": 1.0, "T5": 1.0}
TREE_TOKENS = 1500          # tool-call arguments (a family tree) added to T2 follow-up prompts / T3 output
THROUGHPUT = {               # assumed aggregate output tokens per second per deployment
    "jais-3-7b": 2500, "jais-3-32b": 1000, "k2-think-v2": 700, "bimedix2-8b": 2500, "llama3-med42-8b": 2500,
}
STARTUP_H = 0.4             # image pull, weight download (first time), CUDA graph capture, idle tail


def prompt_tokens() -> dict[str, dict[str, float]]:
    fams = family_map()
    out: dict[str, dict[str, float]] = {}
    for t in ("T1", "T2", "T3", "T5"):
        items = build_items(t)
        tot = 0.0
        for it in items:
            msgs = build_messages(it, fams[it.family_id])
            chars = sum(len(m["content"]) for m in msgs)
            tools = tools_for(t)
            tchars = len(json.dumps(tools)) if tools else 0
            tot += chars / CHARS_PER_TOKEN[it.register] + tchars / 4.0
        out[t] = {"items": len(items), "mean_prompt_tokens": tot / len(items)}
    return out


def estimate(h100_price: float) -> list[dict]:
    pt = prompt_tokens()
    rows = []
    for name in models.PREREGISTERED:
        spec = models.MODELS[name]
        tin = tout = req = 0.0
        for t, d in pt.items():
            n = d["items"] * REQUESTS_PER_ITEM[t]
            req += n
            extra_in = TREE_TOKENS * (REQUESTS_PER_ITEM[t] - 1) if t == "T2" else 0
            tin += d["items"] * (d["mean_prompt_tokens"] * REQUESTS_PER_ITEM[t] + extra_in)
            tout += n * spec.est_output_tokens + (d["items"] * TREE_TOKENS if t in ("T2", "T3") else 0)
        row = {"model": name, "requests": round(req), "input_Mtok": tin / 1e6, "output_Mtok": tout / 1e6}
        if spec.gpu:
            n_gpu = int(spec.gpu.split(":")[1]) if ":" in spec.gpu else 1
            hours = tout / THROUGHPUT[name] / 3600 + STARTUP_H
            row.update({"gpu": spec.gpu, "wall_h": hours, "gpu_h": hours * n_gpu, "usd": hours * n_gpu * h100_price})
        else:
            # Fireworks list price for gpt-oss-120b (USD per million tokens; check before running)
            row.update({"gpu": "API", "wall_h": None, "gpu_h": None, "usd": tin / 1e6 * 0.15 + tout / 1e6 * 0.60})
        rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h100-price", type=float, default=3.95, help="USD per H100-hour on Modal (check current price)")
    a = ap.parse_args()
    pt = prompt_tokens()
    for t, d in pt.items():
        print(f"{t}: {d['items']} items, ~{d['mean_prompt_tokens']:.0f} prompt tokens each")
    print("| Model | GPU | Requests | Input Mtok | Output Mtok | GPU-hours | Est. cost (USD) |")
    print("|---|---|---|---|---|---|---|")
    for r in estimate(a.h100_price):
        gh = "–" if r["gpu_h"] is None else f"{r['gpu_h']:.1f}"
        print(f"| {r['model']} | {r['gpu']} | {r['requests']:,} | {r['input_Mtok']:.1f} | {r['output_Mtok']:.1f} | {gh} | {r['usd']:.0f} |")


if __name__ == "__main__":
    main()
