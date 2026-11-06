"""Import public-domain MedlinePlus Genetics text verbatim.

Usage:  uv run python scripts/import_medlineplus.py

For each page listed in data/content/sources.yaml this writes
data/content/sources/medlineplus/<id>.json with every section heading and
paragraph exactly as published, the source URL, retrieval time, the page's own
review date where given, and a SHA-256 hash per paragraph. The app only ever
displays paragraphs whose hash is in this store (see silsila.content).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/content/sources.yaml"
OUT = ROOT / "data/content/sources/medlineplus"
UA = "Silsila-prototype content importer (public-domain MedlinePlus Genetics text)"
SKIP_HEADINGS = {"other names for this condition", "additional information & resources", "references",
                 "learn more", "more about this health topic", "related health topics", "genetic testing information",
                 "patient support and advocacy resources", "clinical trials", "catalog of genes and diseases from omim",
                 "scientific articles on pubmed", "genetic and rare diseases information center",
                 "additional information from ncbi gene:", "related condition(s)"}


# Paragraphs about United States law or programmes are kept for completeness
# but flagged, and the app never shows them to UAE users.
US_SPECIFIC = re.compile(r"United States|\bGINA\b|federal law|state laws?|Genetic Information Nondiscrimination", re.I)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract(html: str) -> tuple[str, list[dict], dict]:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one(".page-title h1") or soup.find("h1")
    title = clean(title_el.get_text(" ")) if title_el else ""
    main = soup.select_one("div.main") or soup
    sections: list[dict] = []
    current = {"heading": "", "paragraphs": []}
    seen: set[str] = set()
    for el in main.find_all(["h2", "h3", "p", "li"]):
        if el.name in ("h2", "h3"):
            if current["paragraphs"]:
                sections.append(current)
            current = {"heading": clean(el.get_text(" ")), "paragraphs": []}
            continue
        if current["heading"].lower() in SKIP_HEADINGS:
            continue
        if el.find_parent(["nav", "aside"]) or el.find_parent(class_="side"):
            continue
        if el.name == "li" and el.find_parent("ul") is None:
            continue
        txt = clean(el.get_text(" "))
        if len(txt) < 25 or txt.lower().startswith(("from genetics home reference", "the information on this site")):
            continue
        if txt in seen:  # the same text can appear as both <p> and <li>
            continue
        seen.add(txt)
        current["paragraphs"].append(txt)
    if current["paragraphs"]:
        sections.append(current)
    meta = {}
    m = re.search(r"Last updated\s+([A-Za-z]+ \d{1,2}, \d{4})", soup.get_text(" "))
    if m:
        meta["page_last_updated"] = m.group(1)
    return title, sections, meta


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for kind in ("conditions", "handbook"):
        for item in cfg.get(kind, []):
            url = item["url"]
            html = fetch(url)
            title, sections, meta = extract(html)
            if kind == "conditions":
                slug = url.rstrip("/").split("/")[-1]
                api = json.loads(fetch(f"https://medlineplus.gov/download/genetics/condition/{slug}.json"))
                meta.update({"medlineplus_reviewed": api.get("reviewed"), "medlineplus_published": api.get("published"),
                             "inheritance": [x["inheritance-pattern"]["memo"] for x in api.get("inheritance-pattern-list", [])],
                             "genes": [x["related-gene"]["gene-symbol"] for x in api.get("related-gene-list", [])]})
            doc = {
                "id": f"mp:{item['id']}",
                "kind": kind[:-1] if kind == "conditions" else "handbook",
                "title": title,
                "url": url,
                "retrieved_at": now,
                "publisher": cfg["publisher"],
                "licence": cfg["licence"],
                "licence_url": cfg["licence_url"],
                "attribution": cfg["attribution"],
                **meta,
                "sections": [
                    {
                        "heading": s["heading"],
                        "paragraphs": [
                            {"id": f"mp:{item['id']}:{k}:{j}", "text": t, "sha256": sha(t),
                             "us_specific": bool(US_SPECIFIC.search(t))}
                            for j, t in enumerate(s["paragraphs"])
                        ],
                    }
                    for k, s in enumerate(sections)
                ],
            }
            (OUT / f"{item['id']}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            n = sum(len(s["paragraphs"]) for s in sections)
            print(f"{item['id']:28s} {len(sections):2d} sections {n:3d} paragraphs  {title}")
            time.sleep(1.0)  # be polite to NLM servers
    return 0


if __name__ == "__main__":
    sys.exit(main())
