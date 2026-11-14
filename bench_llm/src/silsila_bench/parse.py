"""Probability parser (pre-registered: "the first probability in the answer is extracted").

Recognised forms, in English, Arabic and Arabizi:
  * percentages: "25%", "25 percent", "٢٥٪", "25 بالمئة", "25 في المائة", "25 bil miya"
  * decimals in [0, 1]: "0.25", "٠٫٢٥", ".25", "2.5e-3"
  * "1 in N" / "N in M": "1 in 4", "1 out of 1,000", "2/3", "1:4", "١ من ٤", "واحد من كل أربعة",
    "1 min 4", "wa7id min kil arba3a", "one in four", "two in three"
  * fraction words: half, a quarter, one third, two thirds, an eighth; نصف/نص, ربع, ثلث, ثلثين/ثلثان,
    ثمن; Arabizi nus, rub3, thilth/thulth, thumn
  * "50/50", "fifty-fifty" -> 0.5

Where to look (see AMENDMENTS.md, A2): the system prompt asks for a final line "Answer: ...". If an
answer line is present (English "Answer:", Arabic "الإجابة:"/"الجواب:", Arabizi "jawab:"), the first
probability on or after the LAST such marker is used; otherwise the first probability in the whole
answer. Reasoning ("thinking") text is removed before parsing. No probability, or a refusal, is
"no number".
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# number words (English, Arabic, Arabizi) -> value
_EN_WORDS = {
    "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
}
_AR_WORDS = {
    "واحد": 1, "واحدة": 1, "اثنين": 2, "اثنان": 2, "إثنين": 2, "اثنتين": 2, "ثنتين": 2, "ثلاثة": 3, "ثلاث": 3,
    "أربعة": 4, "اربعة": 4, "أربع": 4, "اربع": 4, "خمسة": 5, "خمس": 5, "ستة": 6, "ست": 6, "سبعة": 7,
    "سبع": 7, "ثمانية": 8, "ثمان": 8, "ثماني": 8, "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
    "عشرين": 20, "عشرون": 20, "ثلاثين": 30, "أربعين": 40, "اربعين": 40, "خمسين": 50, "ستين": 60,
    "سبعين": 70, "ثمانين": 80, "تسعين": 90, "مئة": 100, "مائة": 100, "مية": 100, "ميه": 100, "ألف": 1000,
    "الف": 1000,
    # Arabizi
    "wa7id": 1, "wa7ed": 1, "wa7da": 1, "wahid": 1, "ithnain": 2, "ithnein": 2, "thnain": 2, "ethnain": 2,
    "thalatha": 3, "thalath": 3, "arba3a": 4, "arba3": 4, "arba": 4, "5amsa": 5, "khamsa": 5, "sitta": 6,
    "sab3a": 7, "thamanya": 8, "thmanya": 8, "tis3a": 9, "3ashra": 10, "3ashara": 10, "3eshreen": 20,
    "3ishreen": 20, "5amseen": 50, "miya": 100, "mya": 100, "alf": 1000,
}
_WORDS = {**_EN_WORDS, **_AR_WORDS}
_WORD_RE = "|".join(sorted((re.escape(w) for w in _WORDS if w not in ("a", "an")), key=len, reverse=True))

# fraction words -> value (checked as whole words)
_FRACTIONS = [
    (r"\btwo[\s-]+thirds?\b", 2 / 3), (r"\bthree[\s-]+quarters?\b", 0.75),
    (r"\b(?:one|a)[\s-]+half\b|\bhalf\b", 0.5), (r"\b(?:one|a)[\s-]+quarter\b|\bquarter\b", 0.25),
    (r"\b(?:one|a)[\s-]+third\b", 1 / 3), (r"\b(?:one|an)[\s-]+eighth\b", 0.125),
    (r"\b(?:one|a)[\s-]+sixteenth\b", 1 / 16),
    (r"(?<![\w؀-ۿ])(?:ال)?(?:ثلثين|ثلثان|ثلثي)(?![؀-ۿ])", 2 / 3),
    (r"(?<![\w؀-ۿ])(?:ال)?(?:نصف|نص)(?![؀-ۿ])", 0.5),
    (r"(?<![\w؀-ۿ])(?:ال)?ربع(?![؀-ۿ])", 0.25),
    (r"(?<![\w؀-ۿ])(?:ال)?ثلث(?![؀-ۿ])", 1 / 3),
    (r"(?<![\w؀-ۿ])(?:ال)?ثمن(?![؀-ۿ])", 0.125),
    (r"\b(?:el[\s-]?)?(?:nus|nuss|nos|nisf)\b", 0.5), (r"\b(?:el[\s-]?)?rub3\b", 0.25),
    (r"\b(?:el[\s-]?)?(?:thilth|thulth|thelth)\b", 1 / 3), (r"\b(?:el[\s-]?)?(?:thilthain|thulthain)\b", 2 / 3),
    (r"\b(?:el[\s-]?)?thumn\b", 0.125),
]

_NUM = r"\d{1,3}(?:[,٬]\d{3})+(?:[.٫]\d+)?|\d+(?:[.٫]\d+)?(?:e-?\d+)?|[.٫]\d+"
_PCT = r"(?:%|٪|\s?per\s?cent\b|\s?percent\b|\s?pct\b|\s*(?:بال|في\s?ال|في\s?ال)?(?:مئة|مائة|مية|ميه)(?![؀-ۿ])|\s?(?:bil|fil|b|f)\s?(?:miya|mya|meya)\b)"
_IN = r"(?:in|out\s+of|of|من\s+(?:كل|بين)|من|min\s+kil|min\s+kel|min|men|:|/|إلى|لكل)"

_ANSWER_MARK = re.compile(
    r"(?:\bfinal\s+answer\b|\banswer\b|الإجابة\s*النهائية|الإجابة|الاجابة|الجواب|\bjawab\b|\bel\s*jawab\b|\bal-?jawab\b)\s*\**\s*[:：\-–]",
    re.I,
)
_THINK_CLOSE = re.compile(r"</(?:ifm\|)?think(?:_fast|_faster)?>", re.I)
_THINK_OPEN = re.compile(r"<(?:ifm\|)?think(?:_fast|_faster)?>", re.I)


@dataclass
class Parsed:
    value: float | None        # probability in [0, 1], or None ("no number")
    kind: str                  # percent | decimal | ratio | words | fraction_word | none
    text: str                  # matched text
    source: str                # answer_line | full_text | none
    is_range: bool = False

    @property
    def no_number(self) -> bool:
        return self.value is None


def strip_reasoning(text: str | None) -> tuple[str, str]:
    """Split model output into (answer, reasoning). Text up to the last closing think tag is reasoning.
    An opening tag without a closing tag means the output was cut off inside the reasoning: no answer."""
    t = text or ""
    closes = list(_THINK_CLOSE.finditer(t))
    if closes:
        last = closes[-1]
        return t[last.end():].strip(), t[: last.start()]
    if _THINK_OPEN.search(t):
        return "", t
    return t.strip(), ""


def _num(s: str) -> float:
    s = s.translate(_DIGITS).replace("٫", ".").replace("٬", ",").replace(",", "")
    return float(s)


def _word_num(s: str) -> float | None:
    s = s.strip().casefold()
    if s.isdigit():
        return float(s)
    total = 0
    parts = re.split(r"[\s\-]+|\s+و", s)
    for p in parts:
        p = p.strip()
        if p.startswith("و") and p[1:] in _WORDS:
            p = p[1:]
        if not p:
            continue
        if p not in _WORDS:
            return None
        v = _WORDS[p]
        if v in (100, 1000) and total:
            total *= v
        else:
            total += v
    return float(total) if total else None


def _candidates(text: str) -> list[tuple[int, float, str, str, bool]]:
    """All probability expressions found: (start, value, kind, matched, is_range)."""
    t = text.translate(_DIGITS)
    out: list[tuple[int, float, str, str, bool]] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= x or a >= y for x, y in taken)

    def add(m: re.Match, value: float, kind: str, rng: bool = False, span: tuple[int, int] | None = None) -> None:
        a, b = span or m.span()
        if 0 <= value <= 1 and free(a, b):
            out.append((a, value, kind, t[a:b], rng))
            taken.append((a, b))

    # 50/50
    for m in re.finditer(r"\b50\s*[/\-]\s*50\b|\bfifty[\s-]+fifty\b", t, re.I):
        add(m, 0.5, "ratio")
    # ranges of percentages "20-25%" -> first number (pre-registered: first probability)
    for m in re.finditer(rf"({_NUM})\s*(?:%|٪)?\s*(?:-|–|—|to|إلى|الى|ila)\s*({_NUM})\s*{_PCT}", t, re.I):
        add(m, _num(m.group(1)) / 100, "percent", rng=True)
    # N in M with digits
    for m in re.finditer(rf"(?<![\d.,/])({_NUM})\s*{_IN}\s*({_NUM})(?![\d/]|\s*{_PCT})", t, re.I):
        n, d = _num(m.group(1)), _num(m.group(2))
        if d > 0 and n <= d and n == int(n):
            add(m, n / d, "ratio")
    # percent
    for m in re.finditer(rf"(?<![\d.])({_NUM})\s*{_PCT}", t, re.I):
        add(m, _num(m.group(1)) / 100, "percent")
    # "%25" (percent sign first, as sometimes written in Arabic)
    for m in re.finditer(rf"(?:%|٪)\s*({_NUM})(?![\d.])", t):
        add(m, _num(m.group(1)) / 100, "percent")
    # number words: "one in four", "واحد من كل أربعة", "wa7id min kil arba3a"
    wnc = rf"(?:{_WORD_RE})(?:[\s\-]+(?:و)?(?:{_WORD_RE}))*"
    wr = rf"({wnc})"
    for m in re.finditer(rf"(?<![\w؀-ۿ]){wr}\s+{_IN}\s+{wr}(?![\w؀-ۿ])", t, re.I):
        n, d = _word_num(m.group(1)), _word_num(m.group(2))
        if n and d and n <= d:
            add(m, n / d, "words")
    for m in re.finditer(rf"\b(?:a|an|one)\s+in\s+(?:a\s+|an\s+|every\s+)?({_NUM}|{wnc})\b", t, re.I):
        d = _word_num(m.group(1)) if not re.match(r"\d", m.group(1)) else _num(m.group(1))
        if d:
            add(m, 1 / d, "words")
    # mixed: "1 in four" / "واحد من 4"
    def val(s: str) -> float | None:
        return _num(s) if re.match(r"^[\d.,]", s) else _word_num(s)

    for m in re.finditer(rf"(?<![\d.\w])({_NUM}|{wnc})\s+{_IN}\s+({_NUM}|{wnc})(?![\w؀-ۿ\d])", t, re.I):
        n, d = val(m.group(1)), val(m.group(2))
        if n and d and n <= d:
            add(m, n / d, "ratio")
    # fraction words
    for pat, v in _FRACTIONS:
        for m in re.finditer(pat, t, re.I):
            add(m, v, "fraction_word")
    # decimals in [0, 1] and scientific notation
    for m in re.finditer(r"(?<![\d.,/:])(0?[.٫]\d+|\d(?:\.\d+)?e-\d+|1\.0+)(?![\d%٪/]|\s*(?:%|٪|per\s?cent|percent))", t, re.I):
        add(m, _num(m.group(1)), "decimal")
    # zero chance, spelled out: "0%" handled above; "zero"/"no chance" are not numbers by rule
    out.sort(key=lambda x: x[0])
    return out


def parse_probability(text: str | None) -> Parsed:
    """Extract the first probability from a model answer (after removing reasoning text)."""
    answer, _ = strip_reasoning(text)
    if not answer:
        return Parsed(None, "none", "", "none")
    marks = list(_ANSWER_MARK.finditer(answer.translate(_DIGITS)))
    if marks:
        tail = answer[marks[-1].end():]
        c = _candidates(tail)
        if c:
            a, v, k, s, r = c[0]
            return Parsed(v, k, s, "answer_line", r)
    c = _candidates(answer)
    if c:
        a, v, k, s, r = c[0]
        return Parsed(v, k, s, "full_text", r)
    return Parsed(None, "none", "", "none")


def first_in_full_text(text: str | None) -> float | None:
    """Sensitivity variant: first probability anywhere in the answer, ignoring the answer line."""
    answer, _ = strip_reasoning(text)
    c = _candidates(answer)
    return c[0][1] if c else None


def log_or_none(p: float | None) -> float | None:
    return math.log(p) if p is not None and p > 0 else None
