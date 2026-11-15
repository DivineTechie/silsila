"""'Why not just ask a chatbot?': the demo family's question put to every benchmark model, RECORDED.

The family is the fictional Mariam family used across the demo (not a benchmark item). Each model gets the
same question in English and in Gulf Arabic, once answering in free text and once with the Silsila engine
offered as a tool (the T2 set-up). The exact answer comes from the engine. Results are written to
data/demo/contrast/ and shown in the app labelled RECORDED, with the model, date and settings.

    uv run python -m silsila_bench.demo_contrast [--models gpt-oss-120b,jais-3-7b,...]
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import time
from pathlib import Path

from . import models
from .clients import ChatClient, load_env
from .parse import parse_probability, strip_reasoning
from .prompts import SYSTEM_PROMPT, T2_INSTRUCTION
from .render import facts
from .run import wait_until_ready
from .tools import COMPUTE_TOOL, compute_family_risk

OUT = Path(__file__).resolve().parents[3] / "data" / "demo" / "contrast" / "cah_noura_khalfan.json"
DEFAULT_MODELS = ["jais-3-7b", "jais-3-32b", "llama3-med42-8b", "bimedix2-8b", "gpt-oss-120b"]

STORY = {
    "gulf": ("أنا مريم. ولدي زايد طلع عنده تضخم الغدة الكظرية الخلقي في فحص المواليد. أبوي سعيد، وعمي راشد، وعمتي "
             "سلمى، الثلاثة عيال سيدي عبيد ويدتي موزة، الله يرحمهم. ريلي أحمد هو ولد عمي راشد، وأمه حصة، وعنده أخت "
             "اسمها ميثاء. أختي نورة معرسة على خلفان، ولد عمتي سلمى، وأبوه جمعة، ونورة الحين حامل. أخوي حمدان معرس "
             "على شمّة. وعندنا بنت ثانية اسمها سارة، ما فيها شي. وما حد غير زايد في العايلة عنده هالمرض."),
    "en": ("I am Mariam. Newborn screening found that my son Zayed has congenital adrenal hyperplasia. My father "
           "Saeed, my uncle Rashid and my aunt Salma are the three children of my grandfather Obaid and my "
           "grandmother Moza, may they rest in peace. My husband Ahmed is my uncle Rashid's son; his mother is "
           "Hessa and he has a sister, Maitha. My sister Noura is married to Khalfan, my aunt Salma's son, whose "
           "father is Juma, and Noura is pregnant now. My brother Hamdan is married to Shamma. We also have a "
           "daughter, Sara, who is healthy. No one in the family other than Zayed has this condition."),
}
QUESTION = {
    "en": "Question: What is the chance that Noura and Khalfan's baby will have congenital adrenal hyperplasia?",
    "gulf": "السؤال: شو احتمال إن ياهل نورة وخلفان يكون عنده تضخم الغدة الكظرية الخلقي؟",
}


def gold() -> dict:
    """The exact answer: the story's tree, computed by the engine through the same tool the models get."""
    P = lambda i, s, m=None, f=None, st="unaffected", aff=None: {  # noqa: E731
        "id": i, "sex": s, "mother": m, "father": f, "status": st, "affected_with": aff}
    people = [
        P("Obaid", "male"), P("Moza", "female"),
        P("Saeed", "male", "Moza", "Obaid"), P("Rashid", "male", "Moza", "Obaid"), P("Salma", "female", "Moza", "Obaid"),
        P("Mariam's mother", "female"), P("Hessa", "female"), P("Juma", "male"),
        P("Mariam", "female", "Mariam's mother", "Saeed"), P("Noura", "female", "Mariam's mother", "Saeed"),
        P("Hamdan", "male", "Mariam's mother", "Saeed"), P("Shamma", "female"),
        P("Ahmed", "male", "Hessa", "Rashid"), P("Maitha", "female", "Hessa", "Rashid"),
        P("Khalfan", "male", "Salma", "Juma"),
        P("Zayed", "male", "Mariam", "Ahmed", "affected", "classic congenital adrenal hyperplasia"),
        P("Sara", "female", "Mariam", "Ahmed"),
    ]
    args = {"gene": "CYP21A2", "people": people,
            "unions": [{"a": "Noura", "b": "Khalfan"}, {"a": "Hamdan", "b": "Shamma"}],
            "question": {"type": "couple", "couple": ["Noura", "Khalfan"]}}
    return {"tree": args, **compute_family_risk(args)}


def messages(reg: str, with_tool: bool) -> list[dict]:
    body = STORY[reg] + "\n\n" + facts("CYP21A2", reg) + "\n\n" + QUESTION[reg]
    if with_tool:
        body += "\n\n" + T2_INSTRUCTION[reg]
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": body}]


async def ask(client: ChatClient, reg: str, with_tool: bool) -> dict:
    convo = messages(reg, with_tool)
    tools = [COMPUTE_TOOL] if with_tool else None
    t0 = time.perf_counter()
    out: dict = {"register": reg, "mode": "engine as a tool" if with_tool else "free text", "tool_calls": 0,
                 "tool_values": [], "tool_errors": [], "error": None}
    try:
        msgs, tl = client.prepare(convo, tools)
        res = await client.chat(msgs, tl)
        rounds = 0
        while with_tool and res.tool_calls and rounds < 3:
            msgs = list(msgs) + [client.assistant_message(res)]
            for tc in res.tool_calls:
                r = compute_family_risk(tc.arguments) if tc.name == "compute_family_risk" else {"error": "unknown tool"}
                out["tool_calls"] += 1
                (out["tool_values"] if "probability" in r else out["tool_errors"]).append(r.get("probability", r.get("error")))
                msgs.append(client.tool_message(tc, r))
            res = await client.chat(msgs, tl)
            rounds += 1
        answer = res.content or ""
        out["answer_tail"] = strip_reasoning(answer)[0][-700:]
        p = parse_probability(answer)
        out["value"] = p.value
        out["finish_reason"] = res.finish_reason
    except Exception as e:  # recorded, never hidden
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    out["latency_s"] = round(time.perf_counter() - t0, 1)
    return out


async def run_model(name: str) -> dict:
    spec = models.get(name)
    if spec.provider == "vllm":
        await wait_until_ready(spec.resolved_base_url(), 30 * 60)
    client = ChatClient(spec)
    try:
        rows = await asyncio.gather(*(ask(client, reg, tool) for reg in ("en", "gulf") for tool in (False, True)))
    finally:
        await client.aclose()
    return {"model": spec.model_id, "label": spec.label, "rows": rows}


async def main_async(names: list[str]) -> dict:
    g = gold()
    results = await asyncio.gather(*(run_model(n) for n in names), return_exceptions=True)
    out = {"created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "recorded": True,
           "family": "Fictional Mariam family (the app's demo family); not a benchmark item.",
           "question": QUESTION, "story": STORY, "settings": "temperature 0, one sample, the benchmark's system prompt",
           "gold": {"probability": g.get("probability"), "one_in": g.get("one_in"), "tree": g["tree"]},
           "models": {}}
    for n, r in zip(names, results):
        out["models"][n] = r if not isinstance(r, Exception) else {"label": models.get(n).label, "error": str(r)}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    a = ap.parse_args()
    load_env()
    out = asyncio.run(main_async(a.models.split(",")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print("gold", out["gold"]["probability"], out["gold"]["one_in"])
    for n, m in out["models"].items():
        for r in m.get("rows", []):
            print(f"{n:16s} {r['register']:4s} {r['mode']:17s} value={r.get('value')} tool={r['tool_values']} err={r['error']}")


if __name__ == "__main__":
    main()
