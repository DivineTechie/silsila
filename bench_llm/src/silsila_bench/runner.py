"""Resumable runs: one JSONL file per model and track (runs/<model>/<track>.jsonl).

Items already answered without error are skipped on a rerun; items that failed after all retries are
retried. Every record keeps the prompt, every model turn (content, reasoning, tool calls, usage), every
tool result and the final answer text; scoring happens later in score.py so it can be rerun offline.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .clients import ChatClient, ChatResult
from .items import BENCH_DIR, Family, Item, build_items, family_map
from .prompts import build_messages, tools_for
from .tools import IncrementalTree, compute_family_risk

RUNS_DIR = BENCH_DIR / "runs"
MAX_TURNS_T2 = 4
MAX_TURNS_T3_INCREMENTAL = 60


def run_path(model: str, track: str, runs_dir: Path | None = None) -> Path:
    return (runs_dir or RUNS_DIR) / model / f"{track}.jsonl"


def load_records(path: Path) -> dict[str, dict]:
    """Latest record per item id (later lines win)."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # a line cut off by an interrupted run
            out[r["item_id"]] = r
    return out


def done_ids(path: Path) -> set[str]:
    return {k for k, r in load_records(path).items() if not r.get("error")}


def _turn(res: ChatResult) -> dict[str, Any]:
    return {
        "content": res.content, "raw_content": res.raw_content, "reasoning": res.reasoning,
        "tool_calls": [{"id": t.id, "name": t.name, "arguments": t.arguments} for t in res.tool_calls],
        "tool_calls_from_text": res.tool_calls_from_text, "truncated_in_reasoning": res.truncated_in_reasoning,
        "finish_reason": res.finish_reason, "usage": res.usage, "latency_s": round(res.latency_s, 3),
    }


async def run_item(client: ChatClient, item: Item, fam: Family, *, t3_mode: str = "single") -> dict[str, Any]:
    messages = build_messages(item, fam)
    tools = tools_for(item.track, t3_mode)
    rec: dict[str, Any] = {
        "item_id": item.item_id, "model": client.spec.name, "model_id": client.spec.model_id, **asdict(item),
        "messages": messages, "tools": [t["function"]["name"] for t in tools or []],
        "turns": [], "tool_results": [], "tool_args": [], "final_content": None, "error": None,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "t3_mode": t3_mode if item.track == "T3" else None,
    }
    convo = list(messages)
    try:
        if item.track in ("T1", "T5"):
            res = await client.chat(convo)
            rec["turns"].append(_turn(res))
            rec["final_content"] = res.content
        elif item.track == "T2":
            res = None
            for turn in range(MAX_TURNS_T2 + 1):
                # after MAX_TURNS_T2 tool rounds, one last turn without tools so the model can answer
                res = await client.chat(convo, tools if turn < MAX_TURNS_T2 else None)
                rec["turns"].append(_turn(res))
                if not res.tool_calls or turn == MAX_TURNS_T2:
                    break
                convo.append(client.assistant_message(res))
                for tc in res.tool_calls:
                    if tc.name == "compute_family_risk":
                        out = compute_family_risk(tc.arguments)
                        rec["tool_args"].append(tc.arguments)
                    else:
                        out = {"error": f"unknown tool {tc.name}"}
                    rec["tool_results"].append(out)
                    convo.append(client.tool_message(tc, out))
            rec["final_content"] = res.content if res is not None else None
        elif item.track == "T3" and t3_mode == "single":
            res = await client.chat(convo, tools)
            rec["turns"].append(_turn(res))
            for tc in res.tool_calls:
                if tc.name == "submit_family_tree":
                    rec["tool_args"].append(tc.arguments)
            rec["final_content"] = res.content
        elif item.track == "T3":
            state = IncrementalTree()
            for _ in range(MAX_TURNS_T3_INCREMENTAL):
                res = await client.chat(convo, tools)
                rec["turns"].append(_turn(res))
                if not res.tool_calls:
                    break
                convo.append(client.assistant_message(res))
                for tc in res.tool_calls:
                    out = state.call(tc.name, tc.arguments)
                    rec["tool_results"].append(out)
                    convo.append(client.tool_message(tc, out))
                if state.finished:
                    break
            rec["tool_args"].append(state.as_args())
        else:
            raise ValueError(item.track)
    except Exception as e:  # recorded; the item is retried on the next run
        rec["error"] = f"{e.__class__.__name__}: {e}"
        rec["traceback"] = traceback.format_exc(limit=3)
    rec["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return rec


def select_items(track: str, *, limit: int | None = None, registers: list[str] | None = None,
                 family_types: list[str] | None = None, families: list[str] | None = None) -> list[Item]:
    items = build_items(track)
    if registers:
        items = [i for i in items if i.register in registers]
    if family_types:
        items = [i for i in items if i.family_type in family_types]
    if families:
        items = [i for i in items if i.family_id in families]
    return items[:limit] if limit else items


async def run_track(client: ChatClient, track: str, items: list[Item], *, runs_dir: Path | None = None,
                    concurrency: int | None = None, t3_mode: str = "single", progress: bool = True) -> Path:
    path = run_path(client.spec.name, track, runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    done = done_ids(path)
    todo = [i for i in items if i.item_id not in done]
    fams = family_map()
    sem = asyncio.Semaphore(concurrency or client.spec.concurrency)
    lock = asyncio.Lock()
    n_done = 0
    if progress:
        print(f"[{client.spec.name} {track}] {len(items) - len(todo)} already done, {len(todo)} to run -> {path}")

    async def one(item: Item) -> None:
        nonlocal n_done
        async with sem:
            rec = await run_item(client, item, fams[item.family_id], t3_mode=t3_mode)
        async with lock:
            with path.open("a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_done += 1
            if progress and (n_done % 10 == 0 or n_done == len(todo) or rec["error"]):
                print(f"  {n_done}/{len(todo)}" + (f"  error on {item.item_id}: {rec['error']}" if rec["error"] else ""))

    await asyncio.gather(*(one(i) for i in todo))
    return path
