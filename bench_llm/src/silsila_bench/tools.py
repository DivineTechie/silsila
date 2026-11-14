"""Function tools offered to models, their implementation on the exact Silsila engine, and family-tree
comparison against the gold tree.

T2: `compute_family_risk` takes a structured family tree plus a question and returns the exact answer.
T3: the model builds the tree either with one `submit_family_tree` call (default) or incrementally with
`add_person`, `set_parents`, `add_marriage`, `set_status`, `set_test_result` and `finish_family_tree`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from silsila import params
from silsila.engine import (
    InconsistentEvidence,
    Pedigree,
    PedigreeError,
    PedigreeTooComplex,
    Person,
    Phenotype,
    Sex,
    TestResult,
    Union,
    couple_risk,
    one_in,
    person_risks,
)

from . import names as N

GENES = ("HBB", "CYP21A2", "SMN1")
VARIANT_CODES = {"HBB": ("B", "S"), "CYP21A2": ("c",), "SMN1": ("del",)}
AFFECTED_LABELS = {
    "HBB": ("sickle cell disease", "sickle beta-thalassaemia", "beta-thalassaemia major or intermedia"),
    "CYP21A2": ("classic congenital adrenal hyperplasia",),
    "SMN1": ("spinal muscular atrophy",),
}

_PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "The person's first name exactly as written in the story (unique id)."},
        "sex": {"type": "string", "enum": ["female", "male"]},
        "mother": {"type": ["string", "null"], "description": "id of the mother, or null if not in the story"},
        "father": {"type": ["string", "null"], "description": "id of the father, or null if not in the story"},
        "status": {"type": "string", "enum": ["affected", "unaffected", "unknown"],
                   "description": "affected = has the condition; unaffected = known not to have it; unknown otherwise"},
        "affected_with": {"type": ["string", "null"],
                          "description": "For affected people, the condition. HBB: 'sickle cell disease', "
                                         "'sickle beta-thalassaemia' or 'beta-thalassaemia major or intermedia'; "
                                         "CYP21A2: 'classic congenital adrenal hyperplasia'; SMN1: 'spinal muscular atrophy'."},
        "test_detected": {"type": ["array", "null"], "items": {"type": "string"},
                          "description": "Carrier test result: null if never tested, [] if tested negative, otherwise "
                                         "the variant codes found. HBB: 'B' (beta-thalassaemia), 'S' (sickle); "
                                         "CYP21A2: 'c'; SMN1: 'del'."},
    },
    "required": ["id", "sex"],
}
_UNIONS_SCHEMA = {
    "type": "array",
    "description": "Married couples. Couples who share a child in the tree are detected automatically, but "
                   "listing every married couple is fine.",
    "items": {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}, "required": ["a", "b"]},
}
_GENE_SCHEMA = {"type": "string", "enum": list(GENES),
                "description": "HBB for haemoglobin disorders (beta-thalassaemia, sickle cell), CYP21A2 for congenital "
                               "adrenal hyperplasia, SMN1 for spinal muscular atrophy."}

COMPUTE_TOOL = {
    "type": "function",
    "function": {
        "name": "compute_family_risk",
        "description": (
            "Exact genetic risk calculation (Silsila engine) for an autosomal recessive condition on a family "
            "tree, including cousin marriages, carrier test results and population carrier rates. Give every "
            "person in the story with their parents, marriages, who is affected and test results, and the question. "
            "Returns the probability."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "gene": _GENE_SCHEMA,
                "people": {"type": "array", "items": _PERSON_SCHEMA},
                "unions": _UNIONS_SCHEMA,
                "question": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["carrier", "child_affected"],
                                 "description": "carrier: chance one person carries a variant; child_affected: chance a couple's child is affected"},
                        "person": {"type": "string", "description": "id, for type 'carrier'"},
                        "couple": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2,
                                   "description": "two ids, for type 'child_affected'"},
                    },
                    "required": ["type"],
                },
            },
            "required": ["gene", "people", "question"],
        },
    },
}

SUBMIT_TREE_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_family_tree",
        "description": "Submit the complete structured family tree described in the story (call once).",
        "parameters": {
            "type": "object",
            "properties": {"gene": _GENE_SCHEMA, "people": {"type": "array", "items": _PERSON_SCHEMA},
                           "unions": _UNIONS_SCHEMA},
            "required": ["gene", "people"],
        },
    },
}


def _fn(name: str, desc: str, props: dict, req: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


INCREMENTAL_TOOLS = [
    _fn("add_person", "Add one person to the family tree.",
        {"id": _PERSON_SCHEMA["properties"]["id"], "sex": _PERSON_SCHEMA["properties"]["sex"]}, ["id", "sex"]),
    _fn("set_parents", "Record a person's mother and father (both must be added first).",
        {"child": {"type": "string"}, "mother": {"type": "string"}, "father": {"type": "string"}},
        ["child", "mother", "father"]),
    _fn("add_marriage", "Record that two people are married.", {"a": {"type": "string"}, "b": {"type": "string"}}, ["a", "b"]),
    _fn("set_status", "Record whether a person is affected by the condition.",
        {"id": {"type": "string"}, "status": _PERSON_SCHEMA["properties"]["status"],
         "affected_with": _PERSON_SCHEMA["properties"]["affected_with"]}, ["id", "status"]),
    _fn("set_test_result", "Record a carrier test result.",
        {"id": {"type": "string"},
         "detected": {"type": "array", "items": {"type": "string"},
                      "description": "variant codes found; [] for a negative test. " + _PERSON_SCHEMA["properties"]["test_detected"]["description"]}},
        ["id", "detected"]),
    _fn("finish_family_tree", "Call when the whole family tree has been entered.", {"gene": _GENE_SCHEMA}, ["gene"]),
]


# ------------------------------------------------------------ helpers ---
def parse_arguments(args: Any) -> dict[str, Any]:
    """Tool arguments may arrive as a dict or a JSON string (sometimes wrapped in code fences)."""
    if isinstance(args, dict):
        return args
    if args is None:
        return {}
    s = str(args).strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        out = json.loads(s)
    except json.JSONDecodeError:
        raise ValueError("Tool arguments are not valid JSON")
    if not isinstance(out, dict):
        raise ValueError("Tool arguments must be a JSON object")
    return out


def _as_list(x: Any) -> list:
    if x is None:
        return []
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except json.JSONDecodeError:
            return [x]
    return list(x) if isinstance(x, (list, tuple)) else [x]


def normalise_affected(gene: str, label: Any) -> str:
    labels = AFFECTED_LABELS[gene]
    if len(labels) == 1:
        return labels[0]
    s = str(label or "").casefold()
    if "beta" in s and ("sickle" in s or "منجل" in s) or "s/b" in s or "hbs/b" in s:
        return "sickle beta-thalassaemia"
    if "sickle" in s or "منجل" in s or "s/s" in s or "hbss" in s:
        return "sickle cell disease"
    if "thal" in s or "ثلاس" in s or "b/b" in s:
        return "beta-thalassaemia major or intermedia"
    if s in (x.casefold() for x in labels):
        return s
    raise ValueError(f"Unknown condition '{label}' for HBB; use one of {list(labels)}")


def normalise_variants(gene: str, detected: Any) -> tuple[str, ...]:
    codes = VARIANT_CODES[gene]
    out = []
    for d in _as_list(detected):
        s = str(d).strip()
        hit = next((c for c in codes if c.casefold() == s.casefold()), None)
        if hit is None:
            low = s.casefold()
            if gene == "HBB":
                hit = "S" if ("sickle" in low or "hbs" in low) else ("B" if ("thal" in low or "beta" in low) else None)
            elif gene == "SMN1" and ("del" in low or "smn1" in low):
                hit = "del"
            elif gene == "CYP21A2" and ("cyp21a2" in low or low in ("c", "variant", "positive", "carrier")):
                hit = "c"
            elif gene != "HBB" and low in ("variant", "positive", "carrier", "pathogenic"):
                hit = codes[0]
        if hit is None:
            raise ValueError(f"Unknown variant code '{s}' for {gene}; use one of {list(codes)}")
        out.append(hit)
    return tuple(sorted(out))


@dataclass
class Tree:
    """A family tree in canonical form (ids are whatever the model used, mapped to gold ids if possible)."""

    gene: str
    people: dict[str, dict[str, Any]]
    unions: list[tuple[str, str]] = field(default_factory=list)

    def pedigree(self) -> Pedigree:
        persons = []
        for pid, p in self.people.items():
            status = p.get("status") or "unknown"
            ph = None
            if status == "affected":
                ph = Phenotype(normalise_affected(self.gene, p.get("affected_with")))
            elif status == "unaffected":
                ph = Phenotype(None)
            td = p.get("test_detected")
            test = None if td is None else TestResult(normalise_variants(self.gene, td))
            sex = str(p.get("sex", "")).casefold()
            if sex not in ("female", "male"):
                raise PedigreeError(f"{pid}: sex must be female or male")
            persons.append(Person(pid, Sex(sex), p.get("mother"), p.get("father"), phenotype=ph, test=test))
        return Pedigree.from_people(persons, [Union(a, b) for a, b in self.unions])


def tree_from_args(args: dict[str, Any], resolve: dict[str, str] | None = None) -> Tree:
    """Build a Tree from tool arguments. `resolve` maps normalised names to canonical ids (gold ids) so the
    tree can be compared with the gold tree; unknown names keep their own normalised form."""
    gene = str(args.get("gene") or "").strip().upper()
    gene = {"CYP21A2": "CYP21A2", "HBB": "HBB", "SMN1": "SMN1"}.get(gene, gene)
    if gene not in GENES:
        raise ValueError(f"gene must be one of {list(GENES)}")

    def rid(x: Any) -> str | None:
        if x is None or (isinstance(x, str) and x.strip().lower() in ("", "null", "none", "unknown")):
            return None
        key = N.normalise(str(x))
        if resolve is not None:
            return resolve.get(key, "?" + key)
        return str(x).strip()

    people: dict[str, dict[str, Any]] = {}
    raw = args.get("people")
    if isinstance(raw, str):
        raw = json.loads(raw)
    for p in raw or []:
        if not isinstance(p, dict) or rid(p.get("id")) is None:
            raise ValueError("Each person needs an id")
        pid = rid(p["id"])
        if pid in people:
            raise ValueError(f"Duplicate person id '{p['id']}'")
        td = p.get("test_detected")
        people[pid] = {  # type: ignore[index]
            "sex": str(p.get("sex", "")).strip().casefold(),
            "mother": rid(p.get("mother")),
            "father": rid(p.get("father")),
            "status": str(p.get("status") or "unknown").strip().casefold(),
            "affected_with": p.get("affected_with"),
            "test_detected": None if td is None else list(_as_list(td)),
        }
    unions = []
    for u in _as_list(args.get("unions")):
        if isinstance(u, dict):
            a, b = rid(u.get("a")), rid(u.get("b"))
        elif isinstance(u, (list, tuple)) and len(u) == 2:
            a, b = rid(u[0]), rid(u[1])
        else:
            raise ValueError("Each union needs two ids a and b")
        if a is None or b is None:
            raise ValueError("Each union needs two ids a and b")
        unions.append((a, b))
    return Tree(gene, people, unions)


def _answer(tree: Tree, question: dict[str, Any], resolve: dict[str, str] | None = None) -> float:
    rec = params.load()[tree.gene]
    ped = tree.pedigree()

    def rid(x: Any) -> str:
        key = N.normalise(str(x))
        if resolve is not None:
            return resolve.get(key, "?" + key)
        for pid in ped.people:
            if N.normalise(pid) == key:
                return pid
        raise PedigreeError(f"'{x}' is not in the family tree")

    qtype = str(question.get("type", "")).strip().casefold()
    if qtype == "carrier":
        pid = rid(question.get("person"))
        if pid not in ped.people:
            raise PedigreeError(f"'{question.get('person')}' is not in the family tree")
        return person_risks(ped, rec.locus, rec.background_f)[pid].p_carrier
    if qtype in ("child_affected", "child", "couple"):
        couple = _as_list(question.get("couple"))
        if len(couple) != 2:
            raise ValueError("question.couple must list two people")
        a, b = rid(couple[0]), rid(couple[1])
        for x in (a, b):
            if x not in ped.people:
                raise PedigreeError(f"'{x}' is not in the family tree")
        f, m = (a, b) if ped.people[a].sex == Sex.FEMALE else (b, a)
        return couple_risk(ped, rec.locus, f, m, rec.background_f).p_child_affected
    raise ValueError("question.type must be 'carrier' or 'child_affected'")


def compute_family_risk(args: Any) -> dict[str, Any]:
    """Implementation of the T2 tool. Never raises: errors are returned to the model as {'error': ...}."""
    try:
        a = parse_arguments(args)
        tree = tree_from_args(a)
        q = a.get("question")
        if isinstance(q, str):
            q = json.loads(q)
        if not isinstance(q, dict):
            raise ValueError("question must be an object with type and person or couple")
        p = _answer(tree, q)
    except (PedigreeError, InconsistentEvidence, PedigreeTooComplex, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as e:
        return {"error": str(e) or e.__class__.__name__}
    return {"probability": float(f"{p:.12g}"), "percent": f"{100 * p:.4g}%", "one_in": one_in(p)}


def engine_answer_on_tree(tree: Tree, question: dict[str, Any], resolve: dict[str, str] | None = None) -> float:
    return _answer(tree, question, resolve)


# ------------------------------------------------------- incremental T3 ---
class IncrementalTree:
    """State behind the incremental T3 tools."""

    def __init__(self) -> None:
        self.people: dict[str, dict[str, Any]] = {}
        self.unions: list[dict[str, str]] = []
        self.gene: str | None = None
        self.finished = False

    def call(self, name: str, args: Any) -> dict[str, Any]:
        try:
            a = parse_arguments(args)
            if name == "add_person":
                pid = str(a["id"]).strip()
                if pid in self.people:
                    return {"error": f"'{pid}' already added"}
                self.people[pid] = {"id": pid, "sex": a.get("sex"), "mother": None, "father": None,
                                    "status": "unknown", "affected_with": None, "test_detected": None}
            elif name == "set_parents":
                for k in ("child", "mother", "father"):
                    if str(a[k]).strip() not in self.people:
                        return {"error": f"'{a[k]}' has not been added"}
                p = self.people[str(a["child"]).strip()]
                p["mother"], p["father"] = str(a["mother"]).strip(), str(a["father"]).strip()
            elif name == "add_marriage":
                self.unions.append({"a": str(a["a"]).strip(), "b": str(a["b"]).strip()})
            elif name == "set_status":
                pid = str(a["id"]).strip()
                if pid not in self.people:
                    return {"error": f"'{pid}' has not been added"}
                self.people[pid]["status"] = a.get("status")
                self.people[pid]["affected_with"] = a.get("affected_with")
            elif name == "set_test_result":
                pid = str(a["id"]).strip()
                if pid not in self.people:
                    return {"error": f"'{pid}' has not been added"}
                self.people[pid]["test_detected"] = list(_as_list(a.get("detected")))
            elif name == "finish_family_tree":
                self.gene = a.get("gene")
                self.finished = True
            else:
                return {"error": f"unknown tool {name}"}
        except (KeyError, ValueError, TypeError) as e:
            return {"error": f"bad arguments: {e}"}
        return {"ok": True}

    def as_args(self) -> dict[str, Any]:
        return {"gene": self.gene, "people": list(self.people.values()), "unions": self.unions}


# ---------------------------------------------------------- comparison ---
def canonical(tree: Tree) -> dict[str, Any]:
    """Comparable view: people with sex, parents and evidence; parent-child edges; couple edges."""
    people = {}
    for pid, p in tree.people.items():
        status = p.get("status") or "unknown"
        aff = None
        if status == "affected":
            try:
                aff = normalise_affected(tree.gene, p.get("affected_with"))
            except ValueError:
                aff = str(p.get("affected_with"))
        td = p.get("test_detected")
        try:
            tdn = None if td is None else normalise_variants(tree.gene, td)
        except ValueError:
            tdn = ("?",)
        people[pid] = (p.get("sex"), p.get("mother"), p.get("father"), status, aff, tdn)
    pc = set()
    couples = set()
    for pid, p in tree.people.items():
        for par in (p.get("mother"), p.get("father")):
            if par is not None:
                pc.add((par, pid))
        if p.get("mother") is not None and p.get("father") is not None:
            couples.add(frozenset((p["mother"], p["father"])))
    for a, b in tree.unions:
        if a != b:
            couples.add(frozenset((a, b)))
    return {"gene": tree.gene, "people": people, "parent_child": pc, "couples": couples}


def compare_trees(pred: Tree, gold: Tree) -> dict[str, Any]:
    cp, cg = canonical(pred), canonical(gold)
    out: dict[str, Any] = {}
    for k in ("parent_child", "couples"):
        tp = len(cp[k] & cg[k])
        out[f"{k}_tp"], out[f"{k}_pred"], out[f"{k}_gold"] = tp, len(cp[k]), len(cg[k])
    out["edges_tp"] = out["parent_child_tp"] + out["couples_tp"]
    out["edges_pred"] = out["parent_child_pred"] + out["couples_pred"]
    out["edges_gold"] = out["parent_child_gold"] + out["couples_gold"]
    same_people = set(cp["people"]) == set(cg["people"])
    out["structure_identical"] = (same_people and cp["parent_child"] == cg["parent_child"]
                                  and cp["couples"] == cg["couples"]
                                  and all(cp["people"][x][0] == cg["people"][x][0] for x in cg["people"]))
    out["identical"] = (out["structure_identical"] and cp["gene"] == cg["gene"]
                        and all(cp["people"][x] == cg["people"][x] for x in cg["people"]))
    return out
