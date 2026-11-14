"""Prompts for each track. One fixed system prompt for every model and track (pre-registered)."""

from __future__ import annotations

import json

from .items import Family, Item, family_map
from .render import facts, question_text, story
from .tools import COMPUTE_TOOL, INCREMENTAL_TOOLS, SUBMIT_TREE_TOOL

SYSTEM_PROMPT = (
    "You are helping with an education exercise about inherited (autosomal recessive) conditions in "
    "families. Your answer is for education only and is not medical advice. Read the family description "
    "and answer the question with a single probability. You may show brief working, then finish with one "
    "final line in the form 'Answer: <probability>' (a percentage, a decimal, or '1 in N').\n"
    "هذا تمرين تعليمي عن الأمراض الوراثية المتنحية في العائلات، وليس نصيحة طبية. اقرأ وصف العائلة وأجب "
    "عن السؤال باحتمال واحد، ثم اختم بسطر أخير بالشكل 'Answer: <الاحتمال>'."
)

T2_INSTRUCTION = {
    "en": ("You can use the tool compute_family_risk, which runs an exact genetic calculation on a structured "
           "family tree. Use each person's first name as their id. Then give your answer."),
    "gulf": ("تقدر تستخدم الأداة compute_family_risk، اللي تحسب الاحتمال بالضبط من شجرة عائلة منظمة. استخدم اسم "
             "كل شخص كمعرّف (id). بعدين عط جوابك."),
}
T3_INSTRUCTION = {
    "en": ("Task: turn this family story into a structured family tree using the tools. Include every person "
           "mentioned with their sex and, where the story gives them, both parents; every marriage; who is "
           "affected and with what; and every carrier test result (including negative ones). Use each person's "
           "first name as their id. Do not calculate any risk."),
    "gulf": ("المطلوب: حوّل قصة العائلة هذي إلى شجرة عائلة منظمة باستخدام الأدوات. دخّل كل شخص مذكور مع جنسه، "
             "وأبوه وأمه إذا مذكورين، وكل زواج، ومن المصاب وبأي مرض، وكل نتيجة فحص حامل (حتى السلبية). استخدم "
             "اسم كل شخص كمعرّف (id). لا تحسب أي احتمال."),
}
T3_SYSTEM = (
    "You convert family descriptions into structured family trees for a genetics education tool. "
    "Use only the information in the story."
)
T5_SUFFIX = "Include references (PMIDs) for the facts and methods you use."


def user_prompt(fam: Family, item: Item) -> str:
    reg = item.register
    if item.track == "T3":
        return story(fam, reg) + "\n\n" + T3_INSTRUCTION[reg]
    body = story(fam, reg) + "\n\n" + facts(fam.locus, reg) + "\n\n" + question_text(fam, item.qid, reg)  # type: ignore[arg-type]
    if item.track == "T2":
        body += "\n\n" + T2_INSTRUCTION[reg]
    if item.track == "T5":
        body += "\n" + T5_SUFFIX
    return body


def build_messages(item: Item, fam: Family | None = None) -> list[dict]:
    fam = fam or family_map()[item.family_id]
    system = T3_SYSTEM if item.track == "T3" else SYSTEM_PROMPT
    return [{"role": "system", "content": system}, {"role": "user", "content": user_prompt(fam, item)}]


def tools_for(track: str, t3_mode: str = "single") -> list[dict] | None:
    if track == "T2":
        return [COMPUTE_TOOL]
    if track == "T3":
        return [SUBMIT_TREE_TOOL] if t3_mode == "single" else INCREMENTAL_TOOLS
    return None


def prompted_tool_text(tools: list[dict]) -> str:
    """Tool description for models whose chat template has no tool support (see AMENDMENTS.md, A3)."""
    specs = "\n".join(json.dumps(t["function"], ensure_ascii=False) for t in tools)
    return (
        "\n\n# Tools\nYou can call these functions. Their JSON schemas:\n" + specs + "\n\n"
        "To call a function, reply with ONLY this block (one block per call):\n"
        "<tool_call>\n{\"name\": \"<function-name>\", \"arguments\": {<arguments as JSON>}}\n</tool_call>\n"
        "The result will be sent back to you inside <tool_response></tool_response>."
    )
