"""Approved-content registry and output gate.

Everything Silsila shows a person comes from one of two places:

  1. verbatim MedlinePlus Genetics paragraphs (public domain), imported with a
     SHA-256 hash per paragraph (scripts/import_medlineplus.py);
  2. approved templates (data/content/templates.yaml) whose only variable parts
     are names chosen by the family and numbers computed by the engine.

`render` builds a message and records exactly which registry items it used.
`gate` re-derives the message from those items and refuses anything that does
not match, so text that did not come from the registry (for example text
altered after rendering, or written by a language model) cannot be sent.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from .params import DATA

CONTENT = DATA / "content"
AUDIO = CONTENT / "audio"
Lang = Literal["en", "ar"]
# The two paragraphs every relative is shown (service.relative_view).
RELATIVE_INFO = ("mp:inheritance-patterns:0:3", "mp:risk-assessment:0:2")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Paragraph:
    id: str
    text: str
    sha256: str
    source_title: str
    url: str
    attribution: str
    us_specific: bool


@dataclass
class Message:
    """A message ready to show or send, with its provenance."""

    lang: str
    parts: list[dict[str, Any]] = field(default_factory=list)  # {type, id, text, params?}
    escalate: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(p["text"] for p in self.parts)

    @property
    def digest(self) -> str:
        return sha256(json.dumps(self.parts, ensure_ascii=False, sort_keys=True))


class GateError(ValueError):
    """Raised when a message contains text that is not approved content."""


def teachback_text(q: dict[str, Any], lang: str) -> str:
    """A comprehension question as it is read aloud: the question, then each answer on its own line."""
    return "\n".join([q[lang], *(o[lang] for o in q["options"])])


class Registry:
    def __init__(self, root: Path = CONTENT) -> None:
        self.paragraphs: dict[str, Paragraph] = {}
        self.documents: dict[str, dict[str, Any]] = {}
        for f in sorted((root / "sources" / "medlineplus").glob("*.json")):
            doc = json.loads(f.read_text())
            self.documents[doc["id"]] = doc
            for s in doc["sections"]:
                for p in s["paragraphs"]:
                    if sha256(p["text"]) != p["sha256"]:
                        raise ValueError(f"Content hash mismatch for {p['id']}: file was edited")
                    self.paragraphs[p["id"]] = Paragraph(
                        p["id"], p["text"], p["sha256"], doc["title"], doc["url"], doc["attribution"],
                        p.get("us_specific", False),
                    )
        tdoc = yaml.safe_load((root / "templates.yaml").read_text())
        self.templates: dict[str, dict[str, Any]] = tdoc["templates"]
        self.template_meta: dict[str, Any] = tdoc["meta"]
        self.teachback: list[dict[str, Any]] = tdoc["teachback"]
        self.faq: list[dict[str, Any]] = yaml.safe_load((root / "faq.yaml").read_text())["topics"]
        # Arabic translations of quoted paragraphs, each tied to the hash of its
        # English source. A translation whose source changed is ignored.
        self.translations: dict[str, dict[str, Any]] = {}
        self.translation_meta: dict[str, Any] = {}
        tfile = root / "translations" / "ar" / "medlineplus.json"
        if tfile.exists():
            tdoc = json.loads(tfile.read_text())
            self.translation_meta = tdoc.get("meta", {})
            for pid, t in tdoc.get("paragraphs", {}).items():
                p = self.paragraphs.get(pid)
                if p is not None and t.get("source_sha256") == p.sha256 and t.get("ar"):
                    self.translations[pid] = t
        # Read-aloud clips (scripts/make_read_aloud.py): a synthetic voice reading approved text, each clip
        # keyed by the SHA-256 of the exact text it reads. A text without a matching clip gets no audio,
        # so the voice can never say something other than what is on screen.
        self.audio: dict[str, Any] = {"meta": {}, "clips": {"en": {}, "ar": {}}}
        afile = root / "audio" / "manifest.json"
        if afile.exists():
            self.audio = json.loads(afile.read_text())
        self._audio_root = root / "audio"
        self._check_references()

    # ----------------------------------------------------------- read aloud --
    def read_aloud_texts(self) -> list[dict[str, str]]:
        """Every fixed text a relative can be shown, in both languages: templates with no variable parts,
        the paragraphs behind the relative's page and the common questions, and the comprehension check.
        Texts with names or numbers in them are not pre-recorded."""
        out: list[dict[str, str]] = []
        for tid, t in self.templates.items():
            if re.search(r"\{\w+\}", t["en"]):
                continue
            for lang in ("en", "ar"):
                out.append({"lang": lang, "kind": "template", "id": tid, "text": _norm(t[lang])})
        pids = list(RELATIVE_INFO)
        for topic in self.faq:
            pids += [p for p in topic["paragraphs"] if p not in pids]
        for q in self.teachback:
            if q["evidence"].startswith("mp:") and q["evidence"] not in pids:
                pids.append(q["evidence"])
        for pid in pids:
            p = self.paragraphs[pid]
            if p.us_specific:
                continue
            out.append({"lang": "en", "kind": "source", "id": pid, "text": p.text})
            t = self.translations.get(pid)
            if t is not None:
                out.append({"lang": "ar", "kind": "translation", "id": pid, "text": t["ar"]})
        for q in self.teachback:
            for lang in ("en", "ar"):
                out.append({"lang": lang, "kind": "teachback", "id": q["id"], "text": teachback_text(q, lang)})
        return out

    def audio_for(self, lang: str, text: str) -> dict[str, Any] | None:
        """The clip that reads exactly `text`, or None. Never a clip of a different or older wording."""
        clip = self.audio.get("clips", {}).get(lang, {}).get(sha256(text))
        if clip is None or not (self._audio_root / clip["file"]).exists():
            return None
        return {"url": f"/api/audio/{clip['file']}", "voice": clip["voice"], "seconds": clip.get("seconds"),
                "synthetic": True, "provider": self.audio.get("meta", {}).get("provider", "Azure AI Speech")}

    def with_audio(self, parts: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
        """Copies of message parts with a read-aloud clip attached where one matches the exact text. Called
        after the gate, on the way out; the gated parts and their digest are not changed."""
        out = []
        for p in parts:
            spoken_lang = lang if (p["type"] == "template" or "translation" in p) else "en"
            a = self.audio_for(spoken_lang, p["text"])
            out.append({**p, "audio": {**a, "lang": spoken_lang}} if a else p)
        return out

    def _check_references(self) -> None:
        for t in self.faq:
            for pid in t["paragraphs"]:
                if pid not in self.paragraphs:
                    raise ValueError(f"FAQ {t['id']} cites unknown paragraph {pid}")
                if self.paragraphs[pid].us_specific:
                    raise ValueError(f"FAQ {t['id']} cites US-specific paragraph {pid}")
        for q in self.teachback:
            ev = q["evidence"]
            if ev.startswith("mp:") and ev not in self.paragraphs:
                raise ValueError(f"Teach-back {q['id']} cites unknown paragraph {ev}")
            if ev.startswith("template:") and ev.split(":", 1)[1] not in self.templates:
                raise ValueError(f"Teach-back {q['id']} cites unknown template {ev}")

    # ------------------------------------------------------------ rendering --
    def template_text(self, template_id: str, lang: Lang, params: dict[str, Any] | None = None) -> str:
        t = self.templates[template_id]
        raw = _norm(t[lang])
        needed = set(re.findall(r"\{(\w+)\}", raw))
        given = set((params or {}).keys())
        if needed != given:
            raise KeyError(f"{template_id} needs {sorted(needed)}, got {sorted(given)}")
        for k, v in (params or {}).items():
            if re.search(r"[<>{}]|https?://", str(v)):
                raise GateError(f"Parameter {k} contains markup or a link")
        return raw.format(**(params or {}))

    def template(self, msg: Message, template_id: str, params: dict[str, Any] | None = None) -> Message:
        text = self.template_text(template_id, msg.lang, params)  # type: ignore[arg-type]
        msg.parts.append({"type": "template", "id": template_id, "params": dict(params or {}), "text": text})
        if self.templates[template_id]["kind"] == "safety":
            msg.escalate = msg.escalate or template_id.startswith("reply.")
        return msg

    def quote(self, msg: Message, paragraph_id: str) -> Message:
        p = self.paragraphs[paragraph_id]
        if p.us_specific:
            raise GateError(f"{paragraph_id} is about US law or programmes and is not shown to UAE users")
        part = {"type": "source", "id": p.id, "text": p.text, "sha256": p.sha256,
                "url": p.url, "attribution": p.attribution, "source_title": p.source_title}
        t = self.translations.get(p.id) if msg.lang == "ar" else None
        if t is not None:
            part.update(text=t["ar"], original_text=p.text,
                        translation={"language": "ar", "method": self.translation_meta.get("method"),
                                     "reviewed_by_native_clinician": self.translation_meta.get(
                                         "reviewed_by_native_clinician", False),
                                     "sha256": sha256(t["ar"])})
        msg.parts.append(part)
        return msg

    def condition_paragraphs(self, content_id: str, headings: tuple[str, ...] = ("Description", "Inheritance")) -> list[Paragraph]:
        doc = self.documents[content_id]
        out = []
        for s in doc["sections"]:
            if s["heading"] in headings:
                out.extend(self.paragraphs[p["id"]] for p in s["paragraphs"] if not p.get("us_specific"))
        return out

    # ----------------------------------------------------------------- gate --
    def gate(self, msg: Message) -> Message:
        """Verify every part of a message against the registry. Raises GateError."""
        if not msg.parts:
            raise GateError("Empty message")
        for part in msg.parts:
            if part["type"] == "template":
                expected = self.template_text(part["id"], msg.lang, part.get("params"))  # type: ignore[arg-type]
                if part["text"] != expected:
                    raise GateError(f"Text for template {part['id']} does not match the approved wording")
            elif part["type"] == "source":
                p = self.paragraphs.get(part["id"])
                if p is None:
                    raise GateError(f"Unknown quoted paragraph {part['id']}")
                if "translation" in part:
                    t = self.translations.get(p.id)
                    if (t is None or part["text"] != t["ar"] or part.get("original_text") != p.text
                            or part["translation"].get("sha256") != sha256(t["ar"])):
                        raise GateError(f"Translated text {part['id']} does not match the stored translation")
                elif part["text"] != p.text or sha256(part["text"]) != p.sha256:
                    raise GateError(f"Quoted text {part['id']} does not match the imported source")
                if p.us_specific:
                    raise GateError(f"{p.id} is not shown to UAE users")
            else:
                raise GateError(f"Unknown message part type '{part['type']}'")
        return msg


@lru_cache(maxsize=1)
def registry() -> Registry:
    return Registry()
