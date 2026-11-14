"""Draft a family tree from a spoken family story: transcript -> model tool call -> structured tree.

This is the input side of Silsila's voice intake. The model only proposes structure (people, parents,
marriages); a counsellor confirms every person and link before the exact engine computes anything, and
diagnoses are taken from records, not from speech. The same `submit_family_tree` tool is scored in
Silsila-Bench track T3, so the demo and the benchmark test the same capability.

Usage:
  uv run python -m silsila_bench.voice_tree --model jais-3-7b \
      --transcript ../data/demo/voice/story_mariam_ae_fatima.jais_asr.txt \
      --out ../data/demo/voice/story_mariam_ae_fatima.jais3_tree.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import time
from pathlib import Path

from .clients import ChatClient, load_env
from .models import get as get_model
from .prompts import T3_INSTRUCTION, T3_SYSTEM
from .run import wait_until_ready
from .tools import SUBMIT_TREE_TOOL, parse_arguments, tree_from_args

INTAKE_SYSTEM = T3_SYSTEM + (
    " The story is a transcript of speech and may contain small spelling errors in names. Keep names as "
    "written. If the story names a diagnosis, record it, but it will be checked against the medical record."
)


def clean_transcript(text: str) -> str:
    """Drop the ASR dialect tag (e.g. '[AE] ') and surrounding whitespace."""
    return re.sub(r"^\s*\[[A-Za-z]{2,3}\]\s*", "", text.strip())


async def draft(model: str, transcript: str) -> dict:
    spec = get_model(model)
    if spec.provider == "vllm":
        await wait_until_ready(spec.resolved_base_url(), 30 * 60)
    client = ChatClient(spec)
    messages = [{"role": "system", "content": INTAKE_SYSTEM},
                {"role": "user", "content": transcript + "\n\n" + T3_INSTRUCTION["gulf"]}]
    msgs, tools = client.prepare(messages, [SUBMIT_TREE_TOOL])
    t0 = time.perf_counter()
    try:
        res = await client.chat(msgs, tools)
    finally:
        await client.aclose()
    latency = time.perf_counter() - t0
    call = next((tc for tc in (res.tool_calls or []) if tc.name == "submit_family_tree"), None)
    out: dict = {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model": spec.model_id, "model_label": spec.label, "transcript": transcript,
        "latency_s": round(latency, 2), "tool_called": call is not None,
        "raw_content": res.content, "arguments": None, "valid_tree": False, "error": None,
    }
    if call is not None:
        try:
            args = parse_arguments(call.arguments)
            out["arguments"] = args
            tree = tree_from_args(args)
            tree.pedigree()  # validates structure with the engine's own checks
            out["valid_tree"] = True
        except Exception as e:  # recorded, never hidden
            out["error"] = f"{type(e).__name__}: {e}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="jais-3-7b")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    load_env()
    text = clean_transcript(Path(a.transcript).read_text())
    result = asyncio.run(draft(a.model, text))
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("model", "latency_s", "tool_called", "valid_tree", "error")}))
    if result["arguments"]:
        people = result["arguments"].get("people", [])
        print(len(people), "people;", len(result["arguments"].get("unions", []) or []), "unions")


if __name__ == "__main__":
    main()
