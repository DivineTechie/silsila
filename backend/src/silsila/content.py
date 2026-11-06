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
Lang = Literal["en", "ar"]


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
        self._check_references()

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
        msg.parts.append({"type": "source", "id": p.id, "text": p.text, "sha256": p.sha256,
                          "url": p.url, "attribution": p.attribution, "source_title": p.source_title})
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
                if p is None or part["text"] != p.text or sha256(part["text"]) != p.sha256:
                    raise GateError(f"Quoted text {part['id']} does not match the imported source")
                if p.us_specific:
                    raise GateError(f"{p.id} is not shown to UAE users")
            else:
                raise GateError(f"Unknown message part type '{part['type']}'")
        return msg


@lru_cache(maxsize=1)
def registry() -> Registry:
    return Registry()
