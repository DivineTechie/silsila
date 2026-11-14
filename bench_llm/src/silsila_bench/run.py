"""Run one model on one track (resumable).

    uv run python -m silsila_bench.run --model jais-3-7b --track T1 --limit 20
    uv run python -m silsila_bench.run --model gpt-oss-120b --track all
    uv run python -m silsila_bench.run --model jais-3-7b-mlx --track T1 --limit 4 --dry-run

T4 is computed from T1 and needs no run. Results go to bench_llm/runs/<model>/<track>.jsonl; score and
write the evidence files with `uv run python -m silsila_bench.report`.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys

from . import models
from .clients import ChatClient, load_env
from .items import family_map
from .prompts import build_messages, tools_for
from .runner import run_track, select_items

TRACKS = ("T1", "T2", "T3", "T5")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help=f"one of: {', '.join(models.MODELS)}")
    ap.add_argument("--track", required=True, help="T1, T2, T3, T5 or all")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N items of the track")
    ap.add_argument("--register", action="append", help="en, msa, gulf, arabizi (repeatable)")
    ap.add_argument("--family-type", action="append", help="no_loop, one_loop, multiple (repeatable)")
    ap.add_argument("--family", action="append", help="family id, e.g. one_loop-11 (repeatable)")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--base-url", default=None, help="override the endpoint (e.g. a Modal URL ending in /v1)")
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--t3-mode", choices=["single", "incremental"], default="single")
    ap.add_argument("--chat-template-kwargs", default=None,
                    help='JSON passed to the server, e.g. \'{"reasoning_effort": "low"}\' (smoke tests only; '
                         "pre-registered runs use the model's template defaults)")
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt and the item count; no calls")
    a = ap.parse_args(argv)

    load_env()
    spec = models.get(a.model)
    overrides = {}
    if a.max_tokens:
        overrides["max_tokens"] = a.max_tokens
    if a.chat_template_kwargs:
        overrides["extra_body"] = {**spec.extra_body, "chat_template_kwargs": json.loads(a.chat_template_kwargs)}
    if overrides:
        spec = dataclasses.replace(spec, **overrides)
    tracks = TRACKS if a.track.lower() == "all" else tuple(t.strip().upper() for t in a.track.split(","))
    for t in tracks:
        if t not in TRACKS:
            print(f"Unknown track {t}; T4 is computed from T1.", file=sys.stderr)
            return 2

    if a.dry_run:
        fams = family_map()
        for t in tracks:
            items = select_items(t, limit=a.limit, registers=a.register, family_types=a.family_type, families=a.family)
            print(f"== {t}: {len(items)} items for {spec.name}")
            if items:
                msgs = build_messages(items[0], fams[items[0].family_id])
                for m in msgs:
                    print(f"--- {m['role']}\n{m['content']}")
                tl = tools_for(t, a.t3_mode)
                if tl:
                    print("--- tools:", [x["function"]["name"] for x in tl], f"(mode: {spec.tool_mode})")
        return 0

    from pathlib import Path

    async def go() -> None:
        client = ChatClient(spec, base_url=a.base_url)
        try:
            for t in tracks:
                items = select_items(t, limit=a.limit, registers=a.register, family_types=a.family_type,
                                     families=a.family)
                await run_track(client, t, items, runs_dir=Path(a.runs_dir) if a.runs_dir else None,
                                concurrency=a.concurrency, t3_mode=a.t3_mode)
        finally:
            await client.aclose()

    asyncio.run(go())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
