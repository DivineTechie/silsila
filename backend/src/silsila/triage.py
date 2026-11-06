"""Message triage: decide which approved reply a person's message gets and
whether a human counsellor must be alerted.

The triage step classifies; it never writes. Replies are built only from
approved templates and verbatim MedlinePlus paragraphs (silsila.content), and
every reply passes the output gate.

Two classifiers can run:
  * deterministic rules (always on): keyword and pattern lists in English,
    Arabic and Arabizi (Arabic written in Latin letters);
  * an optional language-model classifier (off unless configured), which may
    only ADD labels. Labels from either source are combined, so the model can
    make the system more cautious but never less.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .content import Message, registry

LABELS = ("crisis", "decision_request", "religious", "third_party", "distress", "booking", "information")
ESCALATE = {"crisis", "decision_request", "religious", "distress"}

# Arabic text is matched after normalising letter variants (أ إ آ -> ا, ة -> ه, ى -> ي)
_AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": ""})

RULES: dict[str, list[str]] = {
    "crisis": [
        r"\b(kill|hurt|harm)(ing)? (my ?self|myself)\b", r"\bsuicid", r"\bend (my|this) life\b",
        r"\b(want|wanna) to die\b", r"\bdon'?t want to (live|be alive)\b", r"\bself[- ]?harm",
        r"\boverdose\b", r"\bnot breathing\b", r"\bunconscious\b", r"\bbleeding (heavily|a lot)\b",
        r"\bemergency\b",
        r"انتحار", r"انتحر", r"اقتل نفسي", r"انهي حياتي", r"اريد ان اموت", r"ابي اموت", r"ودي اموت",
        r"اذي نفسي", r"ايذاء النفس", r"لا اريد ان اعيش", r"طوارئ", r"نزيف",
        r"\bentehar\b", r"\ba[8q]tel nafsi\b", r"\bab[iy] a?moo?t\b", r"\bwedi a?moo?t\b",
    ],
    "decision_request": [
        r"\bshould (we|i)\b", r"\bcancel (the )?(wedding|marriage|engagement)\b", r"\bcall (it )?off\b",
        r"\b(break|broke) (it )?off\b", r"\babort", r"\bterminat", r"\bdivorce\b", r"\bwhat should (we|i) do\b",
        r"\bis it (safe|ok|okay) to (marry|get married|have (a )?(baby|child|children))\b",
        r"\b(can|could) (we|i) (still )?(marry|get married|have (a )?(baby|kids|children))\b",
        r"نلغي", r"الغاء (الزواج|العرس|الخطوبه)", r"هل نتزوج", r"نتزوج ولا", r"اجهاض", r"انهاء الحمل",
        r"طلاق", r"نطلق", r"ماذا افعل", r"شو اسوي", r"وش اسوي", r"ايش اسوي", r"هل يجب", r"لازم نتزوج",
        r"\bnelghi\b", r"\bejhad\b", r"\bshu asawi\b", r"\bwesh asawi\b", r"\bnetzawaj\b",
    ],
    "religious": [
        r"\bharam\b", r"\bhalal\b", r"\bfatwa\b", r"\bshari'?a\b", r"\b(allowed|permitted|forbidden) in islam\b",
        r"\bislam(ic)?ally\b", r"\bsin\b",
        r"حرام", r"حلال", r"فتوي", r"فتوى", r"الشرع", r"شرعا", r"الشريعه", r"يجوز", r"جائز", r"اثم",
        r"\b7aram\b", r"\b7alal\b", r"\byajoo?z\b",
    ],
    "third_party": [
        r"\b(my )?(wife|husband|fianc[eé]e?|cousin|brother|sister|mother|father|mum|mom|dad|uncle|aunt)'?s? (test |carrier )?results?\b",
        r"\bwho (sent|is) (this|the carrier|it)\b", r"\bwho in (my|our|the) family\b", r"\btell me if (he|she|they)\b",
        r"\bis (he|she|my \w+) a carrier\b",
        r"نتيجه (زوجي|زوجتي|خطيبي|خطيبتي|اخي|اختي|ابي|امي|ابن عمي|بنت عمي)", r"من ارسل", r"مين ارسل",
        r"من هو الحامل", r"من في عائلتي", r"هل (هو|هي) حامل",
    ],
    "distress": [
        r"\bscared\b", r"\bafraid\b", r"\bworried\b", r"\banxious\b", r"\bpanic", r"\bcan'?t sleep\b", r"\bcrying\b",
        r"\bdepress", r"\bupset\b", r"\bashamed\b", r"\bguilt", r"\bmy fault\b", r"\bblame", r"\bdevastat",
        r"خايف", r"خائف", r"قلق", r"ابكي", r"حزين", r"مكتئب", r"خجل", r"ذنبي", r"غلطتي", r"يلوم", r"متضايق",
        r"\bkhayef\b", r"\b[9s]ayi[ce]\b",
    ],
    "booking": [
        r"\bbook\b", r"\bappointment\b", r"\bwhere (can|do) i (get )?test", r"\bhow (do|can) i (get )?test",
        r"\bget tested\b", r"\bcounsel+or\b",
        r"موعد", r"حجز", r"احجز", r"وين افحص", r"كيف افحص", r"مستشار",
    ],
}
_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in RULES.items()}


@dataclass
class TriageResult:
    labels: set[str]
    rule_labels: set[str]
    model_labels: set[str] = field(default_factory=set)
    ngram_labels: set[str] = field(default_factory=set)
    topic: str | None = None
    model_used: str | None = None
    # Labels used to order the counsellor queue (recall-tuned, over-alerts by design).
    alert_labels: set[str] = field(default_factory=set)

    @property
    def escalate(self) -> bool:
        return bool((self.labels | self.alert_labels) & ESCALATE)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_AR_NORM)).strip().lower()


def rule_labels(text: str) -> set[str]:
    t = normalise(text)
    return {label for label, pats in _COMPILED.items() if any(p.search(t) for p in pats)}


def match_topic(text: str, lang: str) -> str | None:
    t = normalise(text)
    best, best_score = None, 0
    for topic in registry().faq:
        kws = topic["keywords_ar"] if lang == "ar" else topic["keywords_en"]
        score = sum(1 for k in kws if normalise(k) in t)
        if score > best_score:
            best, best_score = topic["id"], score
    return best


# ------------------------------------------------------- optional LLM layer --
_LLM_SYSTEM = (
    "You label messages sent to a genetic-counselling service. Return JSON only: "
    '{"labels": [...]} using any of: crisis (risk to life or safety, self-harm, medical emergency), '
    "decision_request (asks whether to marry, cancel, have children, test or end a pregnancy, divorce), "
    "religious (asks for a religious ruling), third_party (asks for someone else's results or identity), "
    "distress (expresses fear, guilt, sadness, shame), booking (wants an appointment or a test), "
    "information (asks a factual question). Messages may be English, Arabic (any dialect) or Arabizi. "
    "Do not answer the message. Do not add any other text."
)
_REDACT = [(re.compile(r"\+?\d[\d\s-]{6,}\d"), "[number]"), (re.compile(r"\S+@\S+"), "[email]")]


def redact(text: str) -> str:
    for pat, rep in _REDACT:
        text = pat.sub(rep, text)
    return text


def model_labels(text: str) -> tuple[set[str], str | None]:
    """Optional Azure OpenAI classifier. Returns (labels, model name) or (empty, None)
    when not configured or on any failure (rules still apply)."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    if not (endpoint and key and deployment):
        return set(), None
    import httpx

    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version=" + os.environ.get(
        "AZURE_OPENAI_API_VERSION", "2024-10-21")
    body = {"messages": [{"role": "system", "content": _LLM_SYSTEM}, {"role": "user", "content": redact(text)}],
            "temperature": 0, "response_format": {"type": "json_object"}}
    try:
        r = httpx.post(url, json=body, headers={"api-key": key}, timeout=15)
        r.raise_for_status()
        out = json.loads(r.json()["choices"][0]["message"]["content"])
        return {lab for lab in out.get("labels", []) if lab in LABELS}, deployment
    except Exception:
        return set(), None


# --------------------------------------------- character n-gram classifier --
NGRAM_MODEL = Path(__file__).resolve().parents[3] / "data" / "models" / "triage_ngram.joblib"
_ngram: dict | None = None


def ngram_model() -> dict | None:
    """Load the trained n-gram classifier (evals/train_triage.py) if present."""
    global _ngram
    if _ngram is None and NGRAM_MODEL.exists():
        import joblib

        _ngram = joblib.load(NGRAM_MODEL)
    return _ngram


REPLY_THRESHOLD = 0.5  # conventional default; replies use confident predictions only


def ngram_labels(text: str) -> tuple[set[str], set[str]]:
    """Return (alert labels at the recall-tuned thresholds, reply labels at >= 0.5)."""
    m = ngram_model()
    if not m:
        return set(), set()
    probs = {lab: clf.predict_proba([text])[0, 1] for lab, clf in m["models"].items()}
    alert = {lab for lab, p in probs.items() if p >= m["thresholds"][lab]}
    reply = {lab for lab, p in probs.items() if p >= max(m["thresholds"][lab], REPLY_THRESHOLD)}
    return alert, reply


def classify(text: str, lang: str = "en", use_model: bool = True, use_ngram: bool = True) -> TriageResult:
    """Combine classifiers by union: each layer can only add labels, so adding
    a layer can make the system more cautious, never less."""
    rl = rule_labels(text)
    n_alert, n_reply = ngram_labels(text) if use_ngram else (set(), set())
    ml, used = model_labels(text) if use_model else (set(), None)
    labels = rl | n_reply | ml
    alert = rl | n_alert | ml
    topic = match_topic(text, lang)
    if topic and not labels:
        labels.add("information")
    return TriageResult(labels, rl, ml, n_alert, topic, used, alert)


def reply_for(result: TriageResult, lang: str) -> Message:
    """Build the approved reply. Order: safety first, then information."""
    reg = registry()
    msg = Message(lang=lang)
    order = [("crisis", "reply.crisis"), ("decision_request", "reply.decision_request"),
             ("religious", "reply.religious"), ("third_party", "reply.third_party"),
             ("distress", "reply.distress")]
    for label, tid in order:
        if label in result.labels:
            reg.template(msg, tid)
    if "crisis" not in result.labels:
        if "booking" in result.labels:
            reg.template(msg, "reply.booking")
        if result.topic and not msg.parts:
            reg.template(msg, "reply.information")
            topic = next(t for t in reg.faq if t["id"] == result.topic)
            for pid in topic["paragraphs"]:
                reg.quote(msg, pid)
    if not msg.parts:
        reg.template(msg, "reply.forwarded")
    # Safety by design: every message is read by a person (see service.queue),
    # and every reply that is not already a crisis reply ends with the
    # emergency numbers, so a misclassified crisis message still gets them.
    if "crisis" not in result.labels:
        reg.template(msg, "safety.footer")
    msg.escalate = msg.escalate or result.escalate
    return reg.gate(msg)
