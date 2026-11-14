"""Voice intake: a spoken family story becomes a checked DRAFT family tree for a counsellor.

Pipeline (see docs/governance): speech -> Jais-ASR transcript -> Jais 3 drafts the tree through the
`submit_family_tree` tool -> this module lists every problem with the draft -> a counsellor confirms each
person and each link -> only then does the exact engine compute anything.

Rules enforced here, not left to the model:
  * The draft never reaches the engine until every person and every marriage is confirmed by a person.
  * Health status heard in speech is never used. A status other than "unknown" must come from a record
    (`status_source == "record"`); what was heard is shown to the counsellor as a prompt to check.
  * Problems are listed all at once (not stopped at the first) so the counsellor sees the whole picture.
  * Suggestions are deterministic rules (e.g. "the mother's husband is the likely father"), shown as
    suggestions and applied only when the counsellor clicks them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEMO_DIR = Path(__file__).resolve().parents[3] / "data" / "demo" / "voice"
DEMO_STEM = "story_mariam_ae_fatima"
SEXES = ("female", "male")


class IntakeError(ValueError):
    pass


def _clean(x: Any) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    return None if s.lower() in ("", "null", "none", "unknown") else s


def to_draft(args: dict[str, Any]) -> dict[str, Any]:
    """Convert `submit_family_tree` arguments into a draft with stable ids (p1, p2, ...).

    Parents and spouses are referenced by name in the model output; names that match no listed person
    are kept as `mother_name` / `father_name` so the counsellor can see what was said."""
    raw = args.get("people") or []
    if isinstance(raw, str):
        raw = json.loads(raw)
    people: list[dict[str, Any]] = []
    by_name: dict[str, str] = {}
    for i, p in enumerate(raw, 1):
        name = _clean(p.get("id")) or f"Person {i}"
        pid = f"p{i}"
        by_name.setdefault(name, pid)
        status = (_clean(p.get("status")) or "unknown").lower()
        people.append({
            "id": pid, "name": name, "sex": (_clean(p.get("sex")) or "").lower(),
            "mother_name": _clean(p.get("mother")), "father_name": _clean(p.get("father")),
            # What was heard is kept for the counsellor; the engine-facing status starts as unknown.
            "heard_status": status if status in ("affected", "unaffected") else None,
            "heard_diagnosis": _clean(p.get("affected_with")),
            "status": "unknown", "affected_with": None, "status_source": None,
            "confirmed": False,
        })
    for p in people:
        p["mother"] = by_name.get(p["mother_name"]) if p["mother_name"] else None
        p["father"] = by_name.get(p["father_name"]) if p["father_name"] else None
    unions = []
    for u in args.get("unions") or []:
        a, b = (u.get("a"), u.get("b")) if isinstance(u, dict) else (u[0], u[1]) if len(u) == 2 else (None, None)
        a, b = _clean(a), _clean(b)
        unions.append({"a": by_name.get(a or ""), "b": by_name.get(b or ""), "a_name": a, "b_name": b,
                       "confirmed": False})
    gene = (_clean(args.get("gene")) or "").upper()
    return {"locus_id": gene, "people": people, "unions": unions}


def _issue(code: str, severity: str, message: str, person: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "person": person, "message": message, **extra}


def review(draft: dict[str, Any]) -> list[dict[str, Any]]:
    """Every problem with a draft. severity 'block' stops the engine; 'check' needs a person's attention."""
    people = {p["id"]: p for p in draft.get("people", [])}
    names = {pid: p.get("name") or pid for pid, p in people.items()}
    issues: list[dict[str, Any]] = []

    spouses: dict[str, list[str]] = {pid: [] for pid in people}
    for u in draft.get("unions", []):
        a, b = u.get("a"), u.get("b")
        if a not in people or b not in people:
            missing = [n for n, x in ((u.get("a_name"), a), (u.get("b_name"), b)) if x not in people]
            issues.append(_issue("union_unknown_person", "block",
                                 f"A marriage names someone who is not in the tree: {', '.join(str(m) for m in missing)}."))
            continue
        spouses[a].append(b)
        spouses[b].append(a)
        if people[a].get("sex") == people[b].get("sex"):
            issues.append(_issue("union_same_sex", "block",
                                 f"{names[a]} and {names[b]} are recorded as married but have the same sex.", a))

    for pid, p in people.items():
        if p.get("sex") not in SEXES:
            issues.append(_issue("sex_missing", "block", f"Sex is not recorded for {names[pid]}.", pid))
        for role, want in (("mother", "female"), ("father", "male")):
            ref, said = p.get(role), p.get(f"{role}_name")
            if ref is None and said:
                issues.append(_issue("parent_not_in_tree", "block",
                                     f"{names[pid]}'s {role} was named as '{said}', who is not in the tree.", pid,
                                     role=role, heard=said))
            elif ref is not None and ref not in people:
                issues.append(_issue("parent_not_in_tree", "block", f"{names[pid]}'s {role} is not in the tree.", pid, role=role))
            elif ref is not None and people[ref].get("sex") not in (want, "", None):
                issues.append(_issue("parent_sex", "block",
                                     f"{names[ref]} is recorded as {names[pid]}'s {role} but is not {want}.", pid, role=role))
        if p.get("heard_status") or p.get("heard_diagnosis"):
            heard = p.get("heard_diagnosis") or p.get("heard_status")
            if p.get("status_source") != "record":
                issues.append(_issue("heard_health_status", "check",
                                     f"Heard in the story about {names[pid]}: {heard}. Check the medical record; "
                                     "what was said is not used.", pid, heard=heard))
        if p.get("status") not in (None, "unknown") and p.get("status_source") != "record":
            issues.append(_issue("status_without_record", "block",
                                 f"{names[pid]}'s status must come from a record before it is used.", pid))

    # One parent known, the other missing. Children who share the known parent are grouped: adding one
    # separate unnamed parent per child would make full siblings into half-siblings and change the risk.
    groups: dict[tuple[str, str], list[str]] = {}
    for pid, p in people.items():
        has_m, has_f = p.get("mother") in people, p.get("father") in people
        if has_m != has_f:
            known_role, missing_role = ("mother", "father") if has_m else ("father", "mother")
            groups.setdefault((p[known_role], missing_role), []).append(pid)
    for (known, missing_role), kids in groups.items():
        known_role = "father" if missing_role == "mother" else "mother"
        kid_names = ", ".join(names[k] for k in kids)
        want = "male" if missing_role == "father" else "female"
        partners = [s for s in spouses.get(known, []) if people[s].get("sex") == want]
        if len(partners) == 1:
            issues.append(_issue("one_parent", "block",
                                 f"{kid_names}: {names[known]} is the {known_role} but no {missing_role} is recorded. "
                                 f"{names[known]} is married to {names[partners[0]]}; is that the {missing_role}?",
                                 kids[0], persons=kids, role=missing_role, suggest={"set_parent": partners[0]}))
        else:
            many = len(kids) > 1
            issues.append(_issue("one_parent", "block",
                                 f"{kid_names}: {names[known]} is the {known_role} but no {missing_role} is recorded, "
                                 "and the engine needs both parents or neither. "
                                 + (f"If they are full siblings, add one unnamed {missing_role} for all of them."
                                    if many else f"Add the {missing_role} (an unnamed person is fine)."),
                                 kids[0], persons=kids, role=missing_role,
                                 suggest={"add_unknown_parent": missing_role, "partner_of": known}))

    # cycles (someone their own ancestor)
    seen: dict[str, int] = {}

    def visit(x: str) -> bool:
        if seen.get(x) == 1:
            return True
        if seen.get(x) == 2 or x not in people:
            return False
        seen[x] = 1
        bad = any(visit(people[x][r]) for r in ("mother", "father") if people[x].get(r))
        seen[x] = 2
        return bad

    for pid in people:
        if visit(pid):
            issues.append(_issue("cycle", "block", "The tree has someone as their own ancestor."))
            break
    return issues


def apply(draft: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """Apply one counsellor action to a draft and return the new draft. Actions:
      confirm_person {person}, confirm_union {index}, confirm_all_people, confirm_all_unions
      set_parent {persons, role, parent}                      (e.g. accept "the mother's husband is the father")
      add_unknown_parent {persons, role, partner_of?}         (one shared unnamed parent for full siblings)
      set_status_from_record {person, status, affected_with?, record_ref}
      set_flag {person, flag: pregnant|deceased, value}
      rename {person, name}
    Any edit to a person or link clears that item's confirmation, so it must be confirmed again."""
    d = json.loads(json.dumps(draft))
    people = {p["id"]: p for p in d["people"]}
    kind = action.get("type")

    def person(key: str = "person") -> dict[str, Any]:
        pid = action.get(key)
        if pid not in people:
            raise IntakeError(f"Unknown person {pid!r}")
        return people[pid]

    if kind == "confirm_person":
        person()["confirmed"] = True
    elif kind == "confirm_all_people":
        for p in d["people"]:
            p["confirmed"] = True
    elif kind == "confirm_union":
        i = int(action.get("index", -1))
        if not 0 <= i < len(d["unions"]):
            raise IntakeError("Unknown marriage")
        d["unions"][i]["confirmed"] = True
    elif kind == "confirm_all_unions":
        for u in d["unions"]:
            u["confirmed"] = True
    elif kind == "set_parent":
        role, parent = action.get("role"), action.get("parent")
        if role not in ("mother", "father") or parent not in people:
            raise IntakeError("set_parent needs role mother|father and a parent in the tree")
        for pid in action.get("persons") or []:
            if pid not in people:
                raise IntakeError(f"Unknown person {pid!r}")
            people[pid][role] = parent
            people[pid][f"{role}_name"] = people[parent]["name"]
            people[pid]["confirmed"] = False
    elif kind == "add_unknown_parent":
        role = action.get("role")
        kids = [k for k in action.get("persons") or [] if k in people]
        if role not in ("mother", "father") or not kids:
            raise IntakeError("add_unknown_parent needs role mother|father and children in the tree")
        n = 1 + max(int(x["id"][1:]) for x in d["people"] if re.fullmatch(r"p\d+", x["id"]))
        new_id = f"p{n}"
        label = f"Unnamed {role} of " + ", ".join(people[k]["name"] for k in kids)
        d["people"].append({"id": new_id, "name": label, "sex": "female" if role == "mother" else "male",
                            "mother": None, "father": None, "mother_name": None, "father_name": None,
                            "heard_status": None, "heard_diagnosis": None, "status": "unknown",
                            "affected_with": None, "status_source": None, "confirmed": False, "added_by": "counsellor"})
        for k in kids:
            people[k][role] = new_id
            people[k][f"{role}_name"] = label
            people[k]["confirmed"] = False
        partner = action.get("partner_of")
        if partner in people and not any({u.get("a"), u.get("b")} == {partner, new_id} for u in d["unions"]):
            d["unions"].append({"a": new_id, "b": partner, "a_name": label, "b_name": people[partner]["name"],
                                "confirmed": False})
    elif kind == "set_status_from_record":
        p = person()
        status, ref = action.get("status"), (action.get("record_ref") or "").strip()
        if status not in ("affected", "unaffected", "unknown"):
            raise IntakeError("status must be affected, unaffected or unknown")
        if status != "unknown" and not ref:
            raise IntakeError("A status needs the record it comes from")
        p.update(status=status, affected_with=action.get("affected_with") if status == "affected" else None,
                 status_source="record" if status != "unknown" else None, record_ref=ref or None, confirmed=False)
    elif kind == "set_flag":
        p, flag = person(), action.get("flag")
        if flag not in ("pregnant", "deceased"):
            raise IntakeError("flag must be pregnant or deceased")
        if flag == "pregnant" and p.get("sex") != "female":
            raise IntakeError("Only a woman can be recorded as pregnant")
        p[flag] = bool(action.get("value", True))
        p["confirmed"] = False
    elif kind == "rename":
        p, name = person(), (action.get("name") or "").strip()
        if not name or len(name) > 60:
            raise IntakeError("A name needs 1 to 60 characters")
        old = p["name"]
        p["name"] = name
        for q in d["people"]:
            for r in ("mother", "father"):
                if q.get(r) == p["id"]:
                    q[f"{r}_name"] = name
        for u in d["unions"]:
            for side in ("a", "b"):
                if u.get(side) == p["id"]:
                    u[f"{side}_name"] = name
        p["confirmed"] = p["confirmed"] and old == name
    else:
        raise IntakeError(f"Unknown action {kind!r}")
    return d


def ready_pedigree(draft: dict[str, Any]) -> dict[str, Any]:
    """The engine-facing pedigree, only when every person and marriage is confirmed and nothing blocks."""
    unconfirmed = [p.get("name") or p["id"] for p in draft["people"] if not p.get("confirmed")]
    unconfirmed += [f"marriage {u.get('a_name') or u.get('a')}–{u.get('b_name') or u.get('b')}"
                    for u in draft.get("unions", []) if not u.get("confirmed")]
    if unconfirmed:
        raise IntakeError("Not yet confirmed by the counsellor: " + ", ".join(unconfirmed))
    blocking = [i["message"] for i in review(draft) if i["severity"] == "block"]
    if blocking:
        raise IntakeError("Fix these first: " + " ".join(blocking))
    people = []
    for p in draft["people"]:
        q = {"id": p["id"], "sex": p["sex"], "name": p.get("name") or p["id"],
             "mother": p.get("mother"), "father": p.get("father"), "status": p.get("status") or "unknown"}
        if q["status"] == "affected" and p.get("affected_with"):
            q["affected_with"] = p["affected_with"]
        for flag in ("pregnant", "deceased"):
            if p.get(flag):
                q[flag] = True
        if p.get("test_detected") is not None:
            q["test"] = {"detected": list(p["test_detected"])}
        people.append(q)
    return {"people": people, "unions": [{"a": u["a"], "b": u["b"]} for u in draft.get("unions", [])]}


def load_demo() -> dict[str, Any]:
    """The RECORDED demo: synthetic Emirati voice clip, Jais-ASR transcript and the Jais 3 draft."""
    tree = json.loads((DEMO_DIR / f"{DEMO_STEM}.jais3_tree.json").read_text())
    transcript = (DEMO_DIR / f"{DEMO_STEM}.jais_asr.txt").read_text().strip()
    dialect = re.match(r"^\s*\[([A-Za-z]{2,3})\]", transcript)
    draft = to_draft(tree["arguments"] or {})
    return {
        "recorded": True,
        "audio_label": "Synthetic Emirati voice (Azure ar-AE-FatimaNeural). Fictional family.",
        "script": (DEMO_DIR / "story_mariam_ae.txt").read_text().strip(),
        "transcript": re.sub(r"^\s*\[[A-Za-z]{2,3}\]\s*", "", transcript),
        "asr": {"model": "Jais-ASR (inceptionai, MLX 4-bit, run on a laptop)",
                "dialect": dialect.group(1) if dialect else None},
        "drafter": {"model": tree.get("model_label") or tree.get("model"), "latency_s": tree.get("latency_s"),
                    "created_at": tree.get("created_at"), "tool_called": tree.get("tool_called"),
                    "engine_check": tree.get("error") or "passed"},
        "draft": draft,
        "issues": review(draft),
    }


def demo_audio_path() -> Path:
    return DEMO_DIR / f"{DEMO_STEM}.wav"
