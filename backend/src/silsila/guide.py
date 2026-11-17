"""The Silsila guide: answers questions about the tool without a language model.

How it works:
  1. A question is matched to one entry in data/guide/guide.yaml by its words (a small keyword score with
     inverse-document-frequency weights; no embeddings, no model).
  2. The entry's fixed text is returned as written.
  3. If the entry names a tool, the tool is run now and its values are shown with their sources: the exact
     engine, the evidence files, the audit chain, the parameter register, the FHIR importer.
  4. If nothing matches well enough, the guide says so and offers what it can answer. It never guesses.
  5. A question about the asker's own health, results or family is not answered: the guide says it only
     explains the tool and points to a genetic counsellor and the emergency numbers.
  6. A misspelt word is matched to the closest word the guide knows ("acurate" -> "accurate") and the answer
     says which words were read that way.
  7. Every answer carries the steps that produced it (what was read, what was checked, what was compared,
     which lookup ran and how long it took), so a reader can see that nothing was generated.

The guide explains the tool to visitors, judges and staff. It is not part of what a relative or a family is
shown: there, every sentence is approved wording or a verbatim quotation through the output gate.
The question text is not stored; the audit log records only which entry was matched.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

from . import params, twin
from .content import RELATIVE_INFO, GateError, Message, registry
from .engine import Pedigree, Person, Phenotype, Sex, family_report, one_in
from .params import DATA
from .triage import normalise, rule_labels

GUIDE_FILE = DATA / "guide" / "guide.yaml"
EVIDENCE = Path(__file__).resolve().parents[3] / "docs" / "evidence"
MIN_SCORE = 3.4  # below this the guide does not answer; set from the questions in tests/test_guide.py

STOP = set("a an the is are was were be been do does did of to in on for and or with it its this that these those how what "
           "which who whom when where why can could would should will you your i we my our me us they them there any "
           "some about from by as at if so not no yes please tell show give explain work use get make mean happen need come".split())
STOP_AR = {"ما", "ماذا", "هل", "من", "في", "على", "عن", "الى", "إلى", "او", "أو", "و", "هذا", "هذه", "ذلك", "كيف", "لماذا", "اي",
           "أي", "هو", "هي", "ان", "أن", "لا", "مع", "كل", "سلسله", "سلسلة", "التي", "الذي"}
# A question about the asker's own health, results or family. The guide does not answer these.
PERSONAL = re.compile(
    r"\b(my (result|results|test|baby|wife|husband|child|children|son|daughter|family|pregnancy|cousin|fiance|fiancee|sister|brother|"
    r"mother|father|parents|doctor|risk|chance)|should (i|we)\b|am i (a |at )|i am (pregnant|a carrier|affected|sick|ill)|"
    r"i'm (pregnant|a carrier|affected)|our (baby|child|pregnancy|marriage)|(can|will|could) (i|we) (have|get|marry|pass)|"
    r"do i (have|carry|need a test))\b|"
    r"نتيجتي|فحصي|زوجي|زوجتي|طفلي|ابني|ابنتي|حملي|عائلتي|خطيبي|خطيبتي|هل يجب علي|هل اتزوج|هل نتزوج|هل انا حامل|انا حامل|هل ننجب", re.I)
FIRST_PERSON = re.compile(r"\b(i|i'm|me|my|myself|we|our)\b|انا|نفسي|حياتي", re.I)


def _stem(tok: str) -> str:
    if re.fullmatch(r"[a-z0-9]+", tok):
        for suf in ("ing", "ed", "es", "s"):
            if len(tok) > len(suf) + 3 and tok.endswith(suf):
                return tok[: -len(suf)]
        return tok
    for pre in ("وال", "بال", "لل", "ال", "و"):  # light Arabic prefix stripping
        if tok.startswith(pre) and len(tok) > len(pre) + 2:
            return tok[len(pre):]
    return tok


def tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*|[؀-ۿ]+", re.sub(r"['’]s\b", "", normalise(text)))
    out = []
    for t in raw:
        for part in t.split("-") if "-" in t else [t]:
            if len(part) > 1 and part not in STOP and part not in STOP_AR:
                out.append(_stem(part))
    return out


def plain(text: str) -> str:
    """Lower-case words only, for whole-phrase matching ("why not", "is this a chatbot")."""
    return " " + " ".join(re.findall(r"[a-z0-9]+|[؀-ۿ]+", re.sub(r"['’]", "", normalise(text)))) + " "


class Guide:
    def __init__(self, path: Path = GUIDE_FILE) -> None:
        doc = yaml.safe_load(path.read_text())
        self.meta: dict[str, Any] = doc["meta"]
        self.entries: list[dict[str, Any]] = doc["entries"]
        self.by_id = {e["id"]: e for e in self.entries}
        self.index: dict[str, dict[str, Any]] = {}
        df: dict[str, int] = {}
        for e in self.entries:
            kw = list(e["keywords_en"]) + list(e["keywords_ar"])
            strong = {t for k in kw for t in tokens(k)}
            weak = set(tokens(e["q_en"])) | set(tokens(e["q_ar"]))
            phrases = [plain(k) for k in kw if len(plain(k).split()) > 1]
            self.index[e["id"]] = {"strong": strong, "weak": weak - strong, "phrases": phrases,
                                   "questions": {plain(e["q_en"]), plain(e["q_ar"])}}
            for t in strong | weak:
                df[t] = df.get(t, 0) + 1
        n = len(self.entries)
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self.vocab = sorted(t for t in self.idf if len(t) >= 4)
        for e in self.entries:
            if e.get("tool") and e["tool"] not in TOOLS:
                raise ValueError(f"Guide entry {e['id']} names an unknown tool {e['tool']}")

    def respell(self, text: str) -> tuple[set[str], dict[str, str]]:
        """The question's words, with a misspelt word replaced by the closest word the guide knows.
        Returns the words and the replacements made ({"acurate": "accurate"}). A lone replacement in a question
        with no other known word must be a near-certain one, so that "world" is not read as "word"."""
        toks = tokens(text)
        known = [t for t in toks if t in self.idf]
        found: dict[str, tuple[str, float]] = {}
        for t in toks:
            if t in self.idf or len(t) < 5 or not re.fullmatch(r"[a-z]+", t):
                continue
            close = difflib.get_close_matches(t, self.vocab, n=1, cutoff=0.82)
            if close:
                found[t] = (close[0], difflib.SequenceMatcher(None, t, close[0]).ratio())
        if not known and len(found) == 1 and next(iter(found.values()))[1] < 0.9:
            found = {}
        fixed = {t: w for t, (w, _) in found.items()}
        return {fixed.get(t, t) for t in toks}, fixed

    def scores(self, text: str, words: set[str] | None = None) -> list[tuple[float, str]]:
        qset, whole = (words if words is not None else set(tokens(text))), plain(text)
        out = []
        for eid, ix in self.index.items():
            s = sum(self.idf.get(t, 0) * 1.6 for t in qset & ix["strong"]) + sum(self.idf.get(t, 0) for t in qset & ix["weak"])
            s += 3.0 * sum(1 for p in ix["phrases"] if p in whole)  # a whole keyword phrase is in the question
            if whole in ix["questions"]:
                s += 20  # the question as listed
            if s > 0:
                out.append((round(s, 2), eid))
        return sorted(out, key=lambda x: -x[0])

    def topics(self) -> list[dict[str, str]]:
        return [{"id": e["id"], "q_en": e["q_en"], "q_ar": e["q_ar"]} for e in self.entries]

    def ask(self, store: Any, text: str | None, entry_id: str | None, lang: str) -> dict[str, Any]:
        q = "q_ar" if lang == "ar" else "q_en"
        base = {"not_ai": self.meta["not_ai"][lang], "lang": lang}
        t_start = time.perf_counter()
        steps: list[dict[str, Any]] = []

        def step(kind: str, detail: str) -> None:
            steps.append({"kind": kind, "detail": detail, "ms": round(1000 * (time.perf_counter() - t_start), 1)})

        if entry_id:
            entry, score = self.by_id.get(entry_id), None
            if entry is None:
                return {**base, "kind": "no_match", "answer": self.meta["no_match"][lang], "suggestions": self._suggest([], q), "steps": steps}
            step("read", "A question from the list: no matching needed.")
        else:
            text = (text or "").strip()
            words, fixed = self.respell(text)
            known = sorted(w for w in words if w in self.idf)
            step("read", f"Read {len(text.split())} words; {len(known)} are words the guide knows"
                         + (f": {', '.join(known[:8])}" if known else "") + "."
                         + ("".join(f" Read '{a}' as '{b}'." for a, b in fixed.items()) if fixed else ""))
            ranked = self.scores(text, words)
            personal = bool(PERSONAL.search(normalise(text)) or PERSONAL.search(text))
            crisis = "crisis" in rule_labels(text)
            # "What happens to a suicidal message?" is a question about the tool; "I want to die" is not.
            about_tool = bool(ranked) and ranked[0][1] == "hard_questions" and not FIRST_PERSON.search(normalise(text))
            if personal or (crisis and not about_tool):
                step("safety", "Fixed rules recognised a personal or urgent question. The guide does not answer those.")
                return {**base, "kind": "handoff", "answer": self.meta["handoff"][lang], "suggestions": self._suggest([], q),
                        "method": "Recognised as a personal or urgent question by fixed rules. Not answered.", "steps": steps}
            step("safety", "Checked the fixed safety rules: not a personal or urgent question.")
            if not ranked or ranked[0][0] < MIN_SCORE:
                step("match", f"Compared with {len(self.entries)} fixed answers: none matched well enough"
                              + (f" (closest: '{self.by_id[ranked[0][1]]['q_en']}', score {ranked[0][0]}, needs {MIN_SCORE})." if ranked else "."))
                step("answer", "No answer given. The guide does not guess.")
                return {**base, "kind": "no_match", "answer": self.meta["no_match"][lang],
                        "suggestions": self._suggest([i for _, i in ranked[:3]], q),
                        "method": "No fixed answer matched the words of the question well enough.", "steps": steps}
            score, entry = ranked[0][0], self.by_id[ranked[0][1]]
            step("match", f"Compared with {len(self.entries)} fixed answers: best match '{entry['q_en']}' (score {score})"
                          + (f"; next '{self.by_id[ranked[1][1]]['q_en']}' ({ranked[1][0]})." if len(ranked) > 1 else "."))
        facts: list[dict[str, Any]] = []
        tool = None
        if entry.get("tool"):
            fn, describe = TOOLS[entry["tool"]]
            t0 = time.perf_counter()
            try:
                facts = fn(store, text or "", lang)
            except Exception as e:  # a lookup that fails is reported, never hidden and never made up
                facts = [{"label": "Lookup failed", "value": type(e).__name__, "source": entry["tool"]}]
            tool = {"name": entry["tool"], "description": describe, "ms": round(1000 * (time.perf_counter() - t0), 1)}
            step("lookup", f"{describe} {len(facts)} values read in {tool['ms']:.0f} ms.")
        step("answer", "Returned the fixed text as written. Nothing was generated.")
        others = [i for _, i in self.scores(entry["q_en"])[1:4]]
        return {**base, "kind": "answer", "id": entry["id"], "question": entry[q], "answer": entry["a_ar" if lang == "ar" else "a_en"],
                "facts": facts, "tool": tool, "sources": entry.get("sources", []),
                "method": ("Chosen from the list." if score is None else f"Matched by the words of the question (score {score}).")
                          + " Fixed text, not generated.",
                "suggestions": self._suggest([i for i in others if i != entry["id"]], q), "steps": steps}

    def _suggest(self, ids: list[str], q: str) -> list[dict[str, str]]:
        ids = [i for i in ids if i in self.by_id] or ["what", "no_ai_text", "accuracy", "relationship", "limits"]
        return [{"id": i, "question": self.by_id[i][q]} for i in ids[:5]]


# ------------------------------------------------------------------- tools --
def _ev(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE / f"{name}.json").read_text())


def _fact(label: str, value: Any, source: str) -> dict[str, Any]:
    return {"label": label, "value": str(value), "source": source}


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%" if x < 0.9995 else "100%"


def t_gate_check(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    reg = registry()
    msg = reg.template(Message(lang), "reply.decision_request")
    approved = msg.parts[0]["text"]
    msg.parts[0]["text"] = ("Based on your results, it would be better not to go ahead with the marriage." if lang == "en"
                            else "بناءً على نتائجكما، من الأفضل عدم إتمام الزواج.")
    try:
        reg.gate(msg)
        verdict = "NOT blocked (this would be a defect)"
    except GateError as e:
        verdict = f"Blocked: {e}"
    return [_fact("Text the gate was given", msg.parts[0]["text"], "altered copy of template reply.decision_request"),
            _fact("Gate result, just now", verdict, "silsila.content.Registry.gate"),
            _fact("Approved wording that can be sent instead", approved, "data/content/templates.yaml"),
            _fact("Approved templates / quoted paragraphs available", f"{len(reg.templates)} / {len(reg.paragraphs)}", "content registry")]


def t_guide_facts(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    g = guide()
    return [_fact("Fixed answers", len(g.entries), "data/guide/guide.yaml"),
            _fact("Answers that run a live lookup", sum(1 for e in g.entries if e.get("tool")), "data/guide/guide.yaml"),
            _fact("Lookups available", ", ".join(sorted(TOOLS)), "silsila/guide.py"),
            _fact("Language model calls", 0, "silsila/guide.py"),
            _fact("Your question is stored", "No; only which answer was matched", "audit log, action guide.ask")]


def t_engine_evidence(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    b1, b2 = _ev("b1_engine"), _ev("b2_robustness")
    x = b1["pgmpy_crosscheck"]
    return [_fact("Textbook cases passed", f"{b1['textbook']['n_pass']} of {b1['textbook']['n_cases']}", "docs/evidence/b1_engine.json"),
            _fact("Probabilities agreeing with an independent exact solver (pgmpy) within 1e-9",
                  f"{x['pct_within_1e-9']:.2f}% of {x['n_queries']:,}, on {x['n_pedigrees']:,} random families", "docs/evidence/b1_engine.json"),
            _fact("Largest difference from the independent solver", f"{x['max_abs_error']:.1e}", "docs/evidence/b1_engine.json"),
            _fact("Families in that check with a cousin-marriage loop", f"{x['pct_pedigrees_with_consanguineous_loop']:.0f}%", "docs/evidence/b1_engine.json"),
            _fact("Malformed or impossible inputs answered silently", f"{b2['silent_failures']} of {b2['n_malformed_or_impossible']}",
                  "docs/evidence/b2_robustness.json")]


LOCUS_WORDS = {"HBB": ("thalass", "sickle", "hbb", "haemoglobin", "hemoglobin", "ثلاسيميا", "منجلي"),
               "SMN1": ("sma", "spinal", "smn1", "ضمور"),
               "CYP21A2": ("cah", "adrenal", "cyp21a2", "كظري")}


def _locus_in(text: str) -> str:
    t = normalise(text)
    for locus, words in LOCUS_WORDS.items():
        if any(normalise(w) in t for w in words):
            return locus
    return "CYP21A2"


def t_relationship_chances(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    """Run the exact engine on a simple family: one affected child, unrelated parents, the father's side drawn."""
    locus_id = _locus_in(text)
    rec = params.load()[locus_id]
    allele = "S" if locus_id == "HBB" and any(w in normalise(text) for w in ("sickle", normalise("منجلي"))) else \
        next(a.id for a in rec.locus.alleles if a.pathogenic)
    affected = rec.locus.phenotypes[(allele, allele)]
    people = [
        Person("grandfather", Sex.MALE), Person("grandmother", Sex.FEMALE),
        Person("mothers_father", Sex.MALE), Person("mothers_mother", Sex.FEMALE),
        Person("father", Sex.MALE, "grandmother", "grandfather"), Person("mother", Sex.FEMALE, "mothers_mother", "mothers_father"),
        Person("uncle", Sex.MALE, "grandmother", "grandfather"), Person("uncles_wife", Sex.FEMALE),
        Person("child", Sex.MALE, "mother", "father", phenotype=Phenotype(affected)),
        Person("sibling", Sex.FEMALE, "mother", "father", phenotype=Phenotype(None)),
        Person("cousin", Sex.FEMALE, "uncles_wife", "uncle"),
    ]
    t0 = time.perf_counter()
    rep = family_report(Pedigree.from_people(people), rec.locus, rec.background_f)
    ms = 1000 * (time.perf_counter() - t0)
    rows = [("Parent of the affected child", "father"), ("Brother or sister with no signs of the condition", "sibling"),
            ("Grandparent", "grandfather"), ("Aunt or uncle (the parent's brother or sister)", "uncle"),
            ("First cousin", "cousin"), ("Someone who married into the family (the UAE background rate)", "uncles_wife")]
    src = f"exact engine, {rec.locus.gene}, run now ({ms:.0f} ms)"
    out = [_fact("Condition used", f"{rec.display} ({rec.locus.gene}); affected child: {affected}", "data/params/loci.yaml")]
    for label, pid in rows:
        p = rep.people[pid].p_any_pathogenic
        out.append(_fact(label, f"{_pct(p)} ({one_in(p, lang)})", src))
    return out


def t_register(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    out = []
    for lid, rec in params.load().items():
        for a, raw in zip([x for x in rec.locus.alleles if x.pathogenic], rec.raw["alleles"]):
            s = raw.get("source") or {}
            cite = s.get("citation", "")[:110] + (f" PMID {s['pmid']}" if s.get("pmid") else "")
            out.append(_fact(f"{rec.display}: allele {a.id} ({a.label}), frequency used", f"{a.frequency:.5f} (about 1 carrier in {round(1 / (2 * a.frequency * (1 - a.frequency))):,})",
                             cite or "data/params/loci.yaml"))
    for e in params.register().get("excluded_loci", []):
        out.append(_fact(f"Not calculated: {e['display']}", e["reason"][:200], "data/params/loci.yaml, excluded_loci"))
    return out


def _b4_row(locus: str, budget: int = 5) -> dict[str, Any]:
    rows = _ev("b4_uae")["results"]["theta_calibrated"]["loci"][locus]["atrisk_couples"]
    return next(r for r in rows if r["budget_tests_per_family"] == budget)


def t_yield_evidence(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    out = []
    for locus in ("HBB", "CYP21A2", "SMN1"):
        r = _b4_row(locus)
        ratio = r["ranked_per_1000_tests"] / r["unranked_per_1000_tests"]
        out.append(_fact(f"{locus}: at-risk couples found per 1,000 tests, 5 tests offered per family",
                         f"Silsila's order {r['ranked_per_1000_tests']:.0f} (95% interval {r['ranked_ci95'][0]:.0f} to {r['ranked_ci95'][1]:.0f}); "
                         f"unranked {r['unranked_per_1000_tests']:.0f}; ratio {ratio:.2f}",
                         "docs/evidence/b4_uae.json (simulated UAE clans)"))
    return out


def t_scenario(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", text)]
    n = next((x for x in nums if 1 <= x <= 100000), 100)
    tests = n * 5
    out = [_fact("Index families a year (from your question, or 100)", f"{n:,}", "your question"),
           _fact("Tests, at 5 offered per family", f"{tests:,}", "arithmetic")]
    for locus, name in (("CYP21A2", "CAH"), ("HBB", "haemoglobin disorders")):
        r, k = _b4_row(locus), tests / 1000
        out.append(_fact(f"{name}: at-risk couples found (PROJECTION)",
                         f"Silsila's order about {r['ranked_per_1000_tests'] * k:.0f} (95% interval {r['ranked_ci95'][0] * k:.0f} to "
                         f"{r['ranked_ci95'][1] * k:.0f}); unranked about {r['unranked_per_1000_tests'] * k:.0f}",
                         "docs/evidence/b4_uae.json scaled linearly; not an observed outcome"))
    return out


def t_model_contrast(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    doc = json.loads((DATA / "demo" / "contrast" / "cah_noura_khalfan.json").read_text())
    src = "data/demo/contrast/cah_noura_khalfan.json (RECORDED answers, one fictional family)"
    out = [_fact("Question put to each model", doc["question"]["en"].removeprefix("Question: "), src)]
    p = doc.get("gold", {}).get("probability")
    if isinstance(p, (int, float)):
        out.append(_fact("Exact answer from the engine", f"{100 * p:.1f}%", src))
    for m in list(doc.get("models", {}).values())[:6]:
        for row in m.get("rows", []):
            if row.get("register") != "en":
                continue
            val = row.get("value")
            shown = "no number given" if val is None else (f"{100 * val:.1f}%" if val < 0.1 else f"{100 * val:.0f}%")
            out.append(_fact(f"{m.get('label')}: {row.get('mode')}, English", shown, src))
    return out


def t_privacy_evidence(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    d = _ev("privacy_api")
    return [_fact("Unauthorised requests tried", f"{d['attempts']:,} across {len(d['by_attack'])} kinds of attack", "docs/evidence/privacy_api.json"),
            _fact("Unauthorised disclosures", d["unauthorised_disclosures"], "docs/evidence/privacy_api.json"),
            _fact("Invitation wording that leaked a name or a condition it should not", d["disclosure_violations"], "docs/evidence/privacy_api.json"),
            _fact("Refused attempts recorded on the audit chain", f"{d['denied_attempts_in_audit']:,}", "docs/evidence/privacy_api.json")]


def t_audit_chain(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    c = store.verify_chain()
    return [_fact("Audit chain on this server, verified just now", "intact" if c["intact"] else f"BROKEN at entry {c['first_broken_seq']}", "store.verify_chain()"),
            _fact("Entries in the chain", f"{c['events']:,}", "audit table"),
            _fact("Hash of the latest entry (SHA-256)", (c.get("head") or "")[:32] + "…", "audit table")]


def t_system(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    r = twin.what_if({})
    perf = _ev("perf_engine")["results"]["HBB_60"]
    hosted = _ev("twin_hosted_timing") if (EVIDENCE / "twin_hosted_timing.json").exists() else None
    out = [_fact("One exact recalculation of the 61-person clan, measured on this server just now", f"{r['ms']:.0f} ms", "twin.what_if, run now"),
           _fact("Benchmark: 60-person families with cousin loops, median", f"{perf['median_ms']:.0f} ms (95th percentile {perf['p95_ms']:.0f} ms)",
                 "docs/evidence/perf_engine.json (development laptop)")]
    if hosted:
        w = hosted["warm_one_recorded_result"]["server_ms"]
        out.append(_fact("Hosted server, with one recorded result (recorded 16 Nov 2026)", f"median {w['median']} ms ({w['min']} to {w['max']})",
                         "docs/evidence/twin_hosted_timing.json"))
    out += [_fact("Language model calls needed at run time", 0, "architecture"),
            _fact("Genes calculated", ", ".join(params.load()), "data/params/loci.yaml"),
            _fact("Hosting", "Azure Container Apps, UAE North (the prototype); demo database, one replica", "docs/deployment.md")]
    return out


def t_access_evidence(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    reg = registry()
    m = reg.audio.get("meta", {})
    r = _ev("readability")["groups"]
    return [_fact("Read-aloud clips", f"{m.get('clips', 0)} clips, {m.get('minutes', 0)} minutes, voices {', '.join((m.get('voices') or {}).values())}",
                  "data/content/audio/manifest.json"),
            _fact("How a clip is tied to its text", "stored under the SHA-256 of the exact text; offered only when the hash matches", "silsila/content.py"),
            _fact("Reading level of Silsila's own English wording (Flesch-Kincaid grade)", r["approved_wording_all_templates"]["flesch_kincaid_grade"],
                  "docs/evidence/readability.json"),
            _fact("Reading level of the quoted MedlinePlus text (Flesch-Kincaid grade)", f"{r['quoted_all_common_questions']['flesch_kincaid_grade']} (a college level; quoted text is not simplified)",
                  "docs/evidence/readability.json"),
            _fact("Arabic reviewed by a native-speaking clinician", "Not yet", "docs/limitations.md")]


def t_triage_evidence(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    d = _ev("triage_rules_ngram")
    c = d["overall"]["crisis"]
    return [_fact("Crisis messages alerted, blind synthetic test set", f"{c['sensitivity']['k']} of {c['sensitivity']['n']} "
                  f"(sensitivity {c['sensitivity']['value']:.3f}, 95% interval {c['sensitivity']['ci95'][0]:.3f} to {c['sensitivity']['ci95'][1]:.3f})",
                  "docs/evidence/triage_rules_ngram.json"),
            _fact("Specificity (deliberately low: it over-alerts)", f"{c['specificity']['value']:.3f}", "docs/evidence/triage_rules_ngram.json"),
            _fact("Messages in the test set", d["n_messages"], "docs/evidence/triage_rules_ngram.json"),
            _fact("Messages read by a person, whatever the classifier says", "all of them", "service.queue")]


def t_fhir_sample(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    from .api import fhir_import
    sample = json.loads((DATA / "demo" / "fhir" / "newborn_cah_index_result.json").read_text())
    d = fhir_import.read_index_result(sample, "newborn_screen")
    src = "fhir_import.read_index_result on the fictional sample, run now"
    return [_fact("Condition read", f"{d['condition']} ({d['gene']})", src),
            _fact("Index person", d["summary"], src),
            _fact("Variant copies recorded", " / ".join(d["index"]["test"]["detected"]) if d["index"]["test"] else "none", src),
            _fact("In the record but NOT stored", ", ".join(d["not_stored"]) or "nothing", src),
            _fact("Fingerprint of the record kept with the case (SHA-256)", d["source"]["sha256"][:32] + "…", src)]


def t_uae_context(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    d = _ev("uae_context")
    out = [_fact(it["source"], it["fact_ar" if lang == "ar" else "fact_en"], it["url"]) for it in d["items"]]
    out.append(_fact("Cascade testing announced?", d["not_found"], "docs/evidence/uae_context.json"))
    return out


def t_outcomes(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    from .api import service
    o = service.outcomes(store)
    src = "service.outcomes, this server's demo activity now (fictional families)"
    return [_fact("Invitations", o["invitations"], src),
            _fact("Comprehension check passed", f"{o['comprehension']['passed']} of {o['comprehension']['submitted']} who answered it", src),
            _fact("Booked counselling or tested", f"{o['uptake']['booked_or_tested']} of {o['uptake']['opened']} who opened their link", src),
            _fact("Refused requests / blocked outputs", f"{o['privacy']['denied_requests']} / {o['privacy']['blocked_outputs']}", src),
            _fact("Never measured", o["not_measured"], "service.outcomes")]


def t_twin_facts(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    clan = twin.public()
    r = twin.what_if({})
    src = "data/demo/twin/clan.json (fictional, simulated)"
    return [_fact("People in the Family Twin's clan", len(clan["people"]), src),
            _fact("Generations", 1 + max(p["generation"] for p in clan["people"]), src),
            _fact("Marriages between relatives", len(clan["consanguineous"]), src),
            _fact("One exact recalculation of the whole clan, measured on this server just now", f"{r['ms']:.0f} ms", "twin.what_if, run now"),
            _fact("Real people or patients anywhere in Silsila", 0, "README.md: data and licences")]


def t_source_quote(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    reg = registry()
    out = []
    for pid in RELATIVE_INFO:
        p = reg.paragraphs[pid]
        tr = reg.translations.get(pid) if lang == "ar" else None
        out.append(_fact(f"{p.source_title} ({p.attribution})" + (" · Arabic: machine translation, pending review" if tr else ""),
                         tr["ar"] if tr else p.text, p.url))
    return out


def t_hazard_log(store: Any, text: str, lang: str) -> list[dict[str, Any]]:
    rows = [ln.split("|") for ln in (EVIDENCE.parent / "governance" / "hazard-log.md").read_text().splitlines() if re.match(r"\| H\d+ \|", ln)]
    src = "docs/governance/hazard-log.md, read now"
    out = [_fact("Hazards in the log", len(rows), src)]
    for r in rows[:4]:
        out.append(_fact(f"{r[1].strip()}: {r[2].strip()}", f"Control: {r[4].strip()}", src))
    out.append(_fact("Clauses of the DoH Responsible AI Standard mapped", "see the clause map", "docs/governance/doh-rai-clause-map.md"))
    return out


TOOLS: dict[str, tuple[Callable[[Any, str, str], list[dict[str, Any]]], str]] = {
    "twin_facts": (t_twin_facts, "Counted the Family Twin's clan and timed the engine on it."),
    "source_quote": (t_source_quote, "Read the quoted source paragraphs from the content register."),
    "hazard_log": (t_hazard_log, "Read the hazard log."),
    "gate_check": (t_gate_check, "Ran the output gate on an altered message."),
    "guide_facts": (t_guide_facts, "Counted this guide's own entries and lookups."),
    "engine_evidence": (t_engine_evidence, "Read the engine benchmark files."),
    "relationship_chances": (t_relationship_chances, "Ran the exact engine on a simple family."),
    "register": (t_register, "Read the parameter register."),
    "yield_evidence": (t_yield_evidence, "Read the cascade benchmark file."),
    "scenario": (t_scenario, "Scaled the cascade benchmark to a number of families."),
    "model_contrast": (t_model_contrast, "Read the recorded model answers."),
    "privacy_evidence": (t_privacy_evidence, "Read the privacy test file."),
    "audit_chain": (t_audit_chain, "Verified the audit chain on this server."),
    "system": (t_system, "Timed the engine on this server and read the latency files."),
    "access_evidence": (t_access_evidence, "Read the read-aloud manifest and the readability file."),
    "triage_evidence": (t_triage_evidence, "Read the message-triage evaluation file."),
    "fhir_sample": (t_fhir_sample, "Ran the FHIR importer on the fictional sample record."),
    "uae_context": (t_uae_context, "Read the announced-programmes file."),
    "outcomes": (t_outcomes, "Computed the outcome measures on this server."),
}


@lru_cache(maxsize=1)
def guide() -> Guide:
    return Guide()
