"""Family stories in four registers: English, Modern Standard Arabic, Gulf Arabic and Arabizi.

The story is told by one parent of the affected child (the narrator). Every person is introduced the way
people talk: by their relation to the narrator ("my father's brother's son Khalid", "ابن عمي خالد",
"ولد عمي خالد", "ibn 3ammi Khalid"), followed by who married whom, whose children are whose, who has
died, who is affected, and who had a carrier test with what result. The text fully determines the gold
family tree. Rendering is a pure function of the family, so it is deterministic.

LIMITATION (stated in the pre-registration): the MSA, Gulf Arabic and Arabizi templates below were
written by the team WITHOUT native-speaker review. Kinship terms follow common usage (paternal vs
maternal relatives are distinguished: عم/عمة vs خال/خالة), but wording may read as non-native.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from silsila import params

from .items import Family, PersonRec

EDGE_RANK = {"father": 0, "mother": 1, "brother": 2, "sister": 3, "son": 4, "daughter": 5, "husband": 6, "wife": 7}
SPOUSE_EXTRA = 0.1   # prefer blood paths over paths through a marriage of equal length


# ------------------------------------------------------------- kinship ---
def _neighbours(fam: Family, x: str, blood_only: bool = False) -> list[tuple[str, str]]:
    p = fam.people[x]
    out: list[tuple[str, str]] = []
    if p.father:
        out.append(("father", p.father))
    if p.mother:
        out.append(("mother", p.mother))
    for q in fam.people.values():
        if q.id != x and p.mother and q.mother == p.mother and q.father == p.father:
            out.append(("brother" if q.sex == "male" else "sister", q.id))
        if x in (q.mother, q.father):
            out.append(("son" if q.sex == "male" else "daughter", q.id))
    if not blood_only:
        for f, m in fam.couples:
            if f == x:
                out.append(("husband", m))
            elif m == x:
                out.append(("wife", f))
    return out


def kin_path(fam: Family, src: str, dst: str, blood_only: bool = False) -> tuple[str, ...] | None:
    """Shortest relation path from `src` to `dst` as edge labels, e.g. ('father', 'brother', 'son').
    Ties are broken by a fixed edge order, so the result is deterministic.

    blood_only: the genealogical relationship through common ancestors (go up through parents, at most
    one sibling step, then down through children), as used for "Khalid is Mariam's father's brother's
    son"; paths through a shared child or a marriage are not allowed."""
    if src == dst:
        return ()
    up, down = ("father", "mother"), ("son", "daughter")
    heap: list[tuple[float, tuple[int, ...], str, int, tuple[str, ...]]] = [(0.0, (), src, 0, ())]
    seen: set[tuple[str, int]] = set()
    while heap:
        cost, ranks, x, phase, path = heapq.heappop(heap)
        if x == dst:
            return path
        if (x, phase) in seen:
            continue
        seen.add((x, phase))
        for lab, y in _neighbours(fam, x, blood_only):
            nphase = phase
            if blood_only:
                if lab in up:
                    if phase != 0:
                        continue
                elif lab in down or lab in ("brother", "sister"):
                    if phase == 1 and lab not in down:
                        continue
                    nphase = 1
            c = cost + 1 + (SPOUSE_EXTRA if lab in ("husband", "wife") else 0.0)
            heapq.heappush(heap, (c, ranks + (EDGE_RANK[lab],), y, nphase, path + (lab,)))
    return None


# Arabic kinship units: path -> (construct form, "my" form). The construct form is None when the unit
# is only used with "my" (it then carries a side qualifier such as لأبي).
F, M, B, Z, S, D, H, W = "father", "mother", "brother", "sister", "son", "daughter", "husband", "wife"

UNITS: dict[str, dict[tuple[str, ...], tuple[str | None, str]]] = {
    "msa": {
        (F,): ("والد", "والدي"), (M,): ("والدة", "والدتي"), (B,): ("شقيق", "شقيقي"), (Z,): ("شقيقة", "شقيقتي"),
        (S,): ("ابن", "ابني"), (D,): ("ابنة", "ابنتي"), (H,): ("زوج", "زوجي"), (W,): ("زوجة", "زوجتي"),
        (F, B): ("عم", "عمي"), (F, Z): ("عمة", "عمتي"), (M, B): ("خال", "خالي"), (M, Z): ("خالة", "خالتي"),
        (F, B, S): ("ابن عم", "ابن عمي"), (F, B, D): ("ابنة عم", "ابنة عمي"),
        (F, Z, S): ("ابن عمة", "ابن عمتي"), (F, Z, D): ("ابنة عمة", "ابنة عمتي"),
        (M, B, S): ("ابن خال", "ابن خالي"), (M, B, D): ("ابنة خال", "ابنة خالي"),
        (M, Z, S): ("ابن خالة", "ابن خالتي"), (M, Z, D): ("ابنة خالة", "ابنة خالتي"),
        (B, S): ("ابن أخ", "ابن أخي"), (B, D): ("ابنة أخ", "ابنة أخي"),
        (Z, S): ("ابن أخت", "ابن أختي"), (Z, D): ("ابنة أخت", "ابنة أختي"),
        (F, F): ("جد", "جدي لأبي"), (F, M): ("جدة", "جدتي لأبي"),
        (M, F): ("جد", "جدي لأمي"), (M, M): ("جدة", "جدتي لأمي"),
    },
    "gulf": {
        (F,): ("أبو", "أبوي"), (M,): ("أم", "أمي"), (B,): ("أخو", "أخوي"), (Z,): ("أخت", "أختي"),
        (S,): ("ولد", "ولدي"), (D,): ("بنت", "بنتي"), (H,): ("ريل", "ريلي"), (W,): ("حرمة", "حرمتي"),
        (F, B): ("عم", "عمي"), (F, Z): ("عمة", "عمتي"), (M, B): ("خال", "خالي"), (M, Z): ("خالة", "خالتي"),
        (F, B, S): ("ولد عم", "ولد عمي"), (F, B, D): ("بنت عم", "بنت عمي"),
        (F, Z, S): ("ولد عمة", "ولد عمتي"), (F, Z, D): ("بنت عمة", "بنت عمتي"),
        (M, B, S): ("ولد خال", "ولد خالي"), (M, B, D): ("بنت خال", "بنت خالي"),
        (M, Z, S): ("ولد خالة", "ولد خالتي"), (M, Z, D): ("بنت خالة", "بنت خالتي"),
        (B, S): ("ولد أخو", "ولد أخوي"), (B, D): ("بنت أخو", "بنت أخوي"),
        (Z, S): ("ولد أخت", "ولد أختي"), (Z, D): ("بنت أخت", "بنت أختي"),
        (F, F): ("يد", "يدي أبو أبوي"), (F, M): ("يدة", "يدتي أم أبوي"),
        (M, F): ("يد", "يدي أبو أمي"), (M, M): ("يدة", "يدتي أم أمي"),
    },
    "arabizi": {
        (F,): ("abu", "abuy"), (M,): ("umm", "ummi"), (B,): ("5ou", "5ouy"), (Z,): ("u5t", "u5ti"),
        (S,): ("wild", "wildi"), (D,): ("bint", "binti"), (H,): ("ryal", "ryli"), (W,): ("7urmat", "7urmti"),
        (F, B): ("3amm", "3ammi"), (F, Z): ("3ammat", "3ammti"), (M, B): ("5al", "5ali"), (M, Z): ("5alat", "5alti"),
        (F, B, S): ("ibn 3amm", "ibn 3ammi"), (F, B, D): ("bint 3amm", "bint 3ammi"),
        (F, Z, S): ("ibn 3ammat", "ibn 3ammti"), (F, Z, D): ("bint 3ammat", "bint 3ammti"),
        (M, B, S): ("ibn 5al", "ibn 5ali"), (M, B, D): ("bint 5al", "bint 5ali"),
        (M, Z, S): ("ibn 5alat", "ibn 5alti"), (M, Z, D): ("bint 5alat", "bint 5alti"),
        (B, S): ("wild 5ou", "wild 5ouy"), (B, D): ("bint 5ou", "bint 5ouy"),
        (Z, S): ("wild u5t", "wild u5ti"), (Z, D): ("bint u5t", "bint u5ti"),
        (F, F): ("yadd", "yaddi abu abuy"), (F, M): ("yaddat", "yaddti umm abuy"),
        (M, F): ("yadd", "yaddi abu ummi"), (M, M): ("yaddat", "yaddti umm ummi"),
    },
}


def _segment(path: tuple[str, ...], units: dict) -> list[tuple[str, ...]]:
    """Split a path into the fewest kinship units (ties: longest unit farthest from the owner)."""
    n = len(path)
    best: dict[int, tuple[int, tuple[int, ...], list[tuple[str, ...]]]] = {0: (0, (), [])}
    for i in range(n):
        if i not in best:
            continue
        k, key, segs = best[i]
        for j in range(i + 1, n + 1):
            u = path[i:j]
            if u not in units:
                continue
            cand = (k + 1, key + (-(j - i),), segs + [u])
            if j not in best or (cand[0], tuple(reversed(cand[1]))) < (best[j][0], tuple(reversed(best[j][1]))):
                best[j] = cand
    return best[n][2]


def relation_phrase(path: tuple[str, ...], register: str, owner: str | None = None) -> str:
    """Relation phrase for `path` from the owner's point of view. owner None means the narrator ("my")."""
    if register == "en":
        head = "my" if owner is None else f"{owner}'s"
        return head + " " + "'s ".join(path)
    units = UNITS[register]
    segs = _segment(path, units)
    words = []
    for i, u in enumerate(reversed(segs)):        # farthest unit first (Arabic construct chain)
        construct, mine = units[u]
        last = i == len(segs) - 1
        if last and owner is None:
            words.append(mine)
        else:
            words.append(construct if construct is not None else units[(u[0],)][0])
    if owner is not None:
        words.append(owner)
    return " ".join(words)


# ------------------------------------------------------------ wording ---
COND_GROUP = {   # "affected by any condition at this locus" (question b and "nobody else has ...")
    "HBB": {
        "en": "a haemoglobin disorder (beta-thalassaemia major, sickle cell disease or sickle beta-thalassaemia)",
        "msa": "اضطراب في الهيموغلوبين (الثلاسيميا بيتا الكبرى أو فقر الدم المنجلي أو فقر الدم المنجلي مع الثلاسيميا بيتا)",
        "gulf": "مرض في الدم من أمراض الهيموغلوبين (الثلاسيميا الكبرى أو الأنيميا المنجلية أو الاثنين مع بعض)",
        "arabizi": "maradh fil dam (thalassemia major aw sickle cell aw sickle beta-thalassemia)",
    },
    "CYP21A2": {
        "en": "congenital adrenal hyperplasia (classic 21-hydroxylase deficiency)",
        "msa": "تضخم الغدة الكظرية الخلقي (نقص إنزيم 21-هيدروكسيليز، الشكل التقليدي)",
        "gulf": "تضخم الغدة الكظرية الخلقي (CAH)",
        "arabizi": "tadhakhum el ghudda el kudhriya (CAH)",
    },
    "SMN1": {
        "en": "spinal muscular atrophy (SMA)",
        "msa": "ضمور العضلات الشوكي",
        "gulf": "ضمور العضلات الشوكي (SMA)",
        "arabizi": "dhumoor el 3adalat el shawki (SMA)",
    },
}
COND_LABEL = {   # the index person's diagnosis (engine phenotype label -> text)
    "sickle cell disease": {"en": "sickle cell disease", "msa": "مرض فقر الدم المنجلي",
                            "gulf": "الأنيميا المنجلية", "arabizi": "sickle cell (fagr el dam el manjali)"},
    "sickle beta-thalassaemia": {"en": "sickle beta-thalassaemia", "msa": "مرض فقر الدم المنجلي مع الثلاسيميا بيتا",
                                 "gulf": "الأنيميا المنجلية مع الثلاسيميا بيتا",
                                 "arabizi": "sickle beta-thalassemia"},
    "beta-thalassaemia major or intermedia": {"en": "beta-thalassaemia major", "msa": "مرض الثلاسيميا بيتا الكبرى",
                                              "gulf": "الثلاسيميا الكبرى", "arabizi": "thalassemia major"},
    "classic congenital adrenal hyperplasia": {"en": "classic congenital adrenal hyperplasia (21-hydroxylase deficiency)",
                                               "msa": "تضخم الغدة الكظرية الخلقي (الشكل التقليدي)",
                                               "gulf": "تضخم الغدة الكظرية الخلقي", "arabizi": "tadhakhum el ghudda el kudhriya (CAH)"},
    "spinal muscular atrophy": {"en": "spinal muscular atrophy (SMA)", "msa": "ضمور العضلات الشوكي",
                                "gulf": "ضمور العضلات الشوكي (SMA)", "arabizi": "dhumoor el 3adalat el shawki (SMA)"},
}
CARRIER_GROUP = {
    "HBB": {"en": "a haemoglobin (HBB) variant, either beta-thalassaemia or sickle",
            "msa": "صفة وراثية في جين الهيموغلوبين HBB (الثلاسيميا بيتا أو الخلايا المنجلية)",
            "gulf": "صفة الثلاسيميا أو الأنيميا المنجلية (جين HBB)",
            "arabizi": "sifat el thalassemia aw el sickle cell (jeen HBB)"},
    "CYP21A2": {"en": "a CYP21A2 variant (congenital adrenal hyperplasia)",
                "msa": "صفة تضخم الغدة الكظرية الخلقي (جين CYP21A2)",
                "gulf": "صفة تضخم الغدة الكظرية (جين CYP21A2)",
                "arabizi": "sifat el CAH (jeen CYP21A2)"},
    "SMN1": {"en": "an SMN1 deletion (spinal muscular atrophy)",
             "msa": "صفة ضمور العضلات الشوكي (حذف في جين SMN1)",
             "gulf": "صفة ضمور العضلات الشوكي (جين SMN1)",
             "arabizi": "sifat el SMA (jeen SMN1)"},
}
VARIANT = {
    "B": {"en": "a beta-thalassaemia variant (carrier)", "msa": "متغير الثلاسيميا بيتا (حامل للصفة)",
          "gulf": "صفة الثلاسيميا بيتا", "arabizi": "sifat el thalassemia beta"},
    "S": {"en": "a sickle variant (sickle cell trait)", "msa": "متغير الخلايا المنجلية (سمة الخلايا المنجلية)",
          "gulf": "صفة الأنيميا المنجلية", "arabizi": "sifat el sickle cell"},
    "c": {"en": "a CYP21A2 variant (carrier of congenital adrenal hyperplasia)",
          "msa": "متغير في جين CYP21A2 (حامل لصفة تضخم الغدة الكظرية الخلقي)",
          "gulf": "صفة تضخم الغدة الكظرية (جين CYP21A2)", "arabizi": "sifat el CAH (jeen CYP21A2)"},
    "del": {"en": "a deletion of one copy of SMN1 (SMA carrier)", "msa": "حذف نسخة من جين SMN1 (حامل لصفة ضمور العضلات الشوكي)",
            "gulf": "نقص نسخة من جين SMN1 (صفة ضمور العضلات)", "arabizi": "naqs nus5a min jeen SMN1 (sifat el SMA)"},
}
VARIANT_NAME = {"B": ("beta-thalassaemia variant", "متغير الثلاسيميا بيتا", "sifat el thalassemia beta"),
                "S": ("sickle variant", "متغير الخلايا المنجلية", "sifat el sickle cell"),
                "c": ("CYP21A2 variant", "متغير جين CYP21A2", "jeen CYP21A2"),
                "del": ("SMN1 deletion", "حذف في جين SMN1", "naqs fi jeen SMN1")}


def _join(xs: list[str], register: str) -> str:
    if len(xs) == 1:
        return xs[0]
    if register == "en":
        return ", ".join(xs[:-1]) + " and " + xs[-1]
    if register == "arabizi":
        return ", ".join(xs[:-1]) + " w " + xs[-1]
    return "، ".join(xs[:-1]) + " و" + xs[-1]


@dataclass
class _Ctx:
    fam: Family
    reg: str
    mentioned: set[str]

    def name(self, pid: str) -> str:
        p = self.fam.people[pid]
        return p.name_ar if self.reg in ("msa", "gulf") else p.id

    def me(self) -> str:
        return {"en": "me", "msa": "أنا", "gulf": "أنا", "arabizi": "ana"}[self.reg]

    def rel(self, pid: str) -> str:
        path = kin_path(self.fam, self.fam.narrator, pid)
        assert path is not None, pid
        return relation_phrase(path, self.reg)

    def desc(self, pid: str, *, force: bool = False) -> str:
        """First mention: relation + name; later mentions: name only."""
        if pid == self.fam.narrator:
            return self.me()
        if pid in self.mentioned and not force:
            return self.name(pid)
        self.mentioned.add(pid)
        return f"{self.rel(pid)} {self.name(pid)}"


def _sorted_couples(fam: Family) -> list[tuple[str, str]]:
    return sorted(fam.couples, key=lambda c: (min(fam.people[c[0]].generation, fam.people[c[1]].generation),
                                              list(fam.people).index(c[0])))


def _children_of(fam: Family, f: str, m: str) -> list[str]:
    return [p.id for p in fam.people.values() if p.mother == f and p.father == m]


def story(fam: Family, reg: str) -> str:
    """The family story in register `reg` (en, msa, gulf, arabizi)."""
    c = _Ctx(fam, reg, {fam.narrator})
    P = fam.people
    nar = P[fam.narrator]
    fem = nar.sex == "female"
    group = COND_GROUP[fam.locus][reg]
    out: list[str] = []
    out.append({
        "en": f"My name is {c.name(nar.id)}. I want to understand the chance of {group} in my family.",
        "msa": f"اسمي {c.name(nar.id)}، وأريد أن أفهم احتمال الإصابة ب{group} في عائلتي.",
        "gulf": f"أنا {c.name(nar.id)}، وأبي أفهم شو احتمال {group} في عايلتنا.",
        "arabizi": f"Ana {c.name(nar.id)}, w abi afham sh7al i7timal {group} fi 3ayeltna.",
    }[reg])
    for f, m in _sorted_couples(fam):
        dead = P[f].deceased or P[m].deceased
        if nar.id in (f, m):
            sp = m if nar.id == f else f
            s = {
                "en": f"I am married to {c.desc(sp)}.",
                "msa": f"أنا {'متزوجة' if fem else 'متزوج'} من {c.desc(sp)}.",
                "gulf": f"أنا {'ماخذة' if fem else 'ماخذ'} {c.desc(sp)}.",
                "arabizi": f"Ana {'ma5tha' if fem else 'ma5ith'} {c.desc(sp)}.",
            }[reg]
        else:
            # someone related to the family only through this marriage is introduced by name alone
            pf, pm = kin_path(fam, nar.id, f), kin_path(fam, nar.id, m)
            if pf == (pm or ()) + ("wife",) and f not in c.mentioned:
                c.mentioned.add(f)
            if pm == (pf or ()) + ("husband",) and m not in c.mentioned:
                c.mentioned.add(m)
            h, w = c.desc(m), c.desc(f)
            s = {
                "en": f"{h[0].upper() + h[1:]} and {w} {'were' if dead else 'are'} married.",
                "msa": f"{'كان ' if dead else ''}{h} {'متزوجاً' if dead else 'متزوج'} من {w}.",
                "gulf": f"{h} {'كان ' if dead else ''}معرّس على {w}.",
                "arabizi": f"{h[0].upper() + h[1:]} {'kan ' if dead else ''}m3arris 3ala {w}.",
            }[reg]
        out.append(s)
        cons = next((x for x in fam.consanguineous if (x["female"], x["male"]) == (f, m)), None)
        if cons is not None:
            path = kin_path(fam, f, m, blood_only=True)
            if path:
                if nar.id == f:
                    rel = relation_phrase(path, reg)
                    s = {"en": f"{c.name(m)} is also {rel}.", "msa": f"و{c.name(m)} هو أيضاً {rel}.",
                         "gulf": f"و{c.name(m)} بعد هو {rel}.", "arabizi": f"W {c.name(m)} ba3ad huwa {rel}."}[reg]
                elif nar.id == m:
                    path_m = kin_path(fam, m, f, blood_only=True)
                    rel = relation_phrase(path_m, reg)  # type: ignore[arg-type]
                    s = {"en": f"{c.name(f)} is also {rel}.", "msa": f"و{c.name(f)} هي أيضاً {rel}.",
                         "gulf": f"و{c.name(f)} بعد هي {rel}.", "arabizi": f"W {c.name(f)} ba3ad hiya {rel}."}[reg]
                else:
                    rel = relation_phrase(path, reg, owner=c.name(f))
                    s = {"en": f"{c.name(m)} is {rel}.", "msa": f"{c.name(m)} هو {rel}.",
                         "gulf": f"{c.name(m)} هو {rel}.", "arabizi": f"{c.name(m)} huwa {rel}."}[reg]
                out.append(s)
        kids = _children_of(fam, f, m)
        if kids:
            lst = _join([c.desc(k) for k in kids], reg)
            ours = nar.id in (f, m)
            out.append({
                "en": f"{'Our' if ours else 'Their'} children: {lst}.",
                "msa": f"{'أولادنا' if ours else 'أولادهما'}: {lst}.",
                "gulf": f"{'عيالنا' if ours else 'عيالهم'}: {lst}.",
                "arabizi": f"{'3yalna' if ours else '3yalhum'}: {lst}.",
            }[reg])
    dead = [p.id for p in P.values() if p.deceased]
    if dead:
        names = _join([c.name(x) for x in dead], reg)
        if len(dead) == 1:
            male = P[dead[0]].sex == "male"
            s = {"en": f"{names} has passed away.",
                 "msa": f"{'توفي' if male else 'توفيت'} {names} {'رحمه' if male else 'رحمها'} الله.",
                 "gulf": f"{names} الله {'يرحمه' if male else 'يرحمها'} {'متوفي' if male else 'متوفية'}.",
                 "arabizi": f"{names} allah {'yir7ama' if male else 'yir7amha'}, {'mitwaffi' if male else 'mitwaffya'}."}[reg]
        else:
            s = {"en": f"{names} have passed away.", "msa": f"توفي كل من {names} رحمهم الله.",
                 "gulf": f"{names} الله يرحمهم متوفين.", "arabizi": f"{names} allah yir7amhum, mitwaffeen."}[reg]
        out.append(s)
    idx = P[fam.index]
    male = idx.sex == "male"
    label = COND_LABEL[idx.affected_with][reg]  # type: ignore[index]
    out.append({
        "en": f"{c.name(idx.id)} has been diagnosed with {label}.",
        "msa": f"تم تشخيص {c.name(idx.id)} ب{label}.",
        "gulf": f"{c.name(idx.id)} {'تشخّص' if male else 'تشخّصت'} ب{label}.",
        "arabizi": f"{c.name(idx.id)} {'tsha55as' if male else 'tsha55asat'} b {label}.",
    }[reg])
    out.append({
        "en": f"Nobody else in the family has {group}.",
        "msa": f"ولا يوجد أي شخص آخر في العائلة مصاب ب{group}.",
        "gulf": f"وما حد {'غيره' if male else 'غيرها'} في العايلة عنده {group}.",
        "arabizi": f"W ma 7ad {'ghaira' if male else 'ghairha'} fil 3ayla 3inda {group}.",
    }[reg])
    tested = [p for p in P.values() if p.test_detected is not None]
    for p in tested:
        out.append(_test_sentence(c, p))
    return " ".join(out)


def _test_sentence(c: _Ctx, p: PersonRec) -> str:
    reg, n, male = c.reg, c.name(p.id), p.sex == "male"
    if p.id == c.fam.narrator:
        n = {"en": "I", "msa": "أنا", "gulf": "أنا", "arabizi": "Ana"}[reg]
    if p.test_detected:
        v = _join([VARIANT[a][reg] for a in p.test_detected], reg)
        if p.id == c.fam.narrator:
            return {"en": f"I had a carrier test, which found {v}.",
                    "msa": f"أجريت فحص الكشف عن الحاملين، وأظهر {v}.",
                    "gulf": f"أنا سوّيت فحص الحامل وطلع عندي {v}.",
                    "arabizi": f"Ana sawwait fa7s el 7amil w til3 3indi {v}."}[reg]
        return {"en": f"{n} had a carrier test, which found {v}.",
                "msa": f"{'أجرى' if male else 'أجرت'} {n} فحص الكشف عن الحاملين، وأظهر {v}.",
                "gulf": f"{n} {'سوّى' if male else 'سوّت'} فحص الحامل وطلع {'عنده' if male else 'عندها'} {v}.",
                "arabizi": f"{n} {'sawwa' if male else 'sawwat'} fa7s el 7amil w til3 {'3inda' if male else '3indaha'} {v}."}[reg]
    if p.id == c.fam.narrator:
        return {"en": "I had a carrier test, which was negative (no variant found).",
                "msa": "أجريت فحص الكشف عن الحاملين وكانت النتيجة سلبية (لم يُعثر على أي متغير).",
                "gulf": "أنا سوّيت فحص الحامل وطلع سلبي (ما لقوا شي).",
                "arabizi": "Ana sawwait fa7s el 7amil w til3 salbi (ma lgaw shay)."}[reg]
    return {"en": f"{n} had a carrier test, which was negative (no variant found).",
            "msa": f"{'أجرى' if male else 'أجرت'} {n} فحص الكشف عن الحاملين وكانت النتيجة سلبية (لم يُعثر على أي متغير).",
            "gulf": f"{n} {'سوّى' if male else 'سوّت'} فحص الحامل وطلع سلبي (ما لقوا شي).",
            "arabizi": f"{n} {'sawwa' if male else 'sawwat'} fa7s el 7amil w til3 salbi (ma lgaw shay)."}[reg]


# ---------------------------------------------------------------- facts ---
def locus_facts(locus_id: str) -> dict[str, float]:
    """Carrier proportion per pathogenic allele (2 p_i p_N (1-F), i.e. the published values the engine
    uses), detection rate per allele and background inbreeding."""
    rec = params.load()[locus_id]
    loc, f = rec.locus, rec.background_f
    pn = next(a.frequency for a in loc.alleles if not a.pathogenic)
    out: dict[str, float] = {"F": f}
    for a in loc.alleles:
        if a.pathogenic:
            out[f"carrier_{a.id}"] = 2 * a.frequency * pn * (1 - f)
            out[f"detect_{a.id}"] = a.detection_rate
    return out


def facts(locus_id: str, reg: str) -> str:
    fx = locus_facts(locus_id)
    rec = params.load()[locus_id]
    alleles = [a for a in rec.locus.alleles if a.pathogenic]
    lang = "en" if reg == "en" else ("arabizi" if reg == "arabizi" else "ar")
    lines: list[str] = []
    for a in alleles:
        en, ar, az = VARIANT_NAME[a.id]
        pct = f"{100 * fx[f'carrier_{a.id}']:.2f}%"
        det = fx[f"detect_{a.id}"]
        if lang == "en":
            lines.append(f"- About {pct} of people in this population carry one {en} ({rec.locus.gene} gene).")
            lines.append(f"- The carrier test detects {100 * det:.1f}% of carriers of the {en}"
                         + (" (assume it misses none)." if det >= 1 else "; a negative test leaves a small remaining chance."))
        elif lang == "ar":
            lines.append(f"- حوالي {pct} من الناس في هذا المجتمع يحملون نسخة واحدة من {ar} (جين {rec.locus.gene}).")
            lines.append(f"- فحص الحاملين يكشف {100 * det:.1f}% من حاملي {ar}"
                         + ("، (افترض أنه لا يفوّت أي حامل)." if det >= 1 else "، لذلك تبقى بعد النتيجة السلبية فرصة صغيرة."))
        else:
            lines.append(f"- Ta8riban {pct} min el nas fi hal mujtama3 3indahum nus5a wa7da min {az} (jeen {rec.locus.gene}).")
            lines.append(f"- Fa7s el 7amil yikshif {100 * det:.1f}% min el 7amileen"
                         + (" (i3tabir inna ma yfawwit 7ad)." if det >= 1 else ", fa ba3d el natija el salbiya yibga i7timal sghayyir."))
    F_ = fx["F"]
    if lang == "en":
        head = "Facts to use:"
        lines += [f"- Background inbreeding coefficient of this population: F = {F_} (applies to people whose parents are not described).",
                  "- People who married into the family are not related to it except as described.",
                  "- Assume complete penetrance (two variant copies always cause the condition, one copy never does) and no new mutations."]
    elif lang == "ar":
        head = "معلومات للاستخدام:"
        lines += [f"- معامل زواج الأقارب الخلفي في هذا المجتمع: F = {F_} (ينطبق على الأشخاص الذين لم يُذكر والداهم).",
                  "- الأشخاص الذين تزوجوا من خارج العائلة ليسوا أقارب لها إلا كما هو مذكور.",
                  "- افترض نفاذية كاملة (نسختان من المتغير تسببان المرض دائماً، ونسخة واحدة لا تسببه) وعدم وجود طفرات جديدة."]
    else:
        head = "Ma3loomat lil isti5dam:"
        lines += [f"- Mu3amil zawaj el aqarib el 5alfi fi hal mujtama3: F = {F_} (lil nas elli ma ndhikar abuhum w ummhum).",
                  "- Elli 5athaw min barra el 3ayla mub garaib lahum illa mithil ma madhkoor.",
                  "- I3tabir inn nus5atain min el sifa dayman tsabbib el maradh, w nus5a wa7da ma tsabbib, w ma fi tafrat jideeda."]
    return head + "\n" + "\n".join(lines)


# ------------------------------------------------------------ questions ---
def question_text(fam: Family, qid: str, reg: str) -> str:
    q = fam.question(qid)
    c = _Ctx(fam, reg, set())
    nar = fam.narrator
    if q.type == "carrier":
        p = fam.people[q.person]  # type: ignore[index]
        d = c.desc(p.id, force=True)
        g = CARRIER_GROUP[fam.locus][reg]
        fem = p.sex == "female"
        return {
            "en": f"Question: What is the chance that {d} is a carrier of {g}?",
            "msa": f"السؤال: ما احتمال أن {'تكون' if fem else 'يكون'} {d} {'حاملةً' if fem else 'حاملاً'} ل{g}؟",
            "gulf": f"السؤال: شو احتمال إن {d} {'تكون حاملة' if fem else 'يكون حامل'} ل{g}؟",
            "arabizi": f"Su2al: sh7al i7timal inn {d} {'tkoon 7amla' if fem else 'ykoon 7amil'} l {g}?",
        }[reg]
    f, m = q.couple  # type: ignore[misc]
    g = COND_GROUP[fam.locus][reg]
    another = q.couple_has_children
    if nar in (f, m):
        sp = c.desc(m if nar == f else f, force=True)
        return {
            "en": f"Question: If {sp} and I have {'another' if another else 'a'} child, what is the chance that the child will be affected by {g}?",
            "msa": f"السؤال: إذا أنجبت أنا و{sp} طفلاً{' آخر' if another else ''}، فما احتمال أن يكون الطفل مصاباً ب{g}؟",
            "gulf": f"السؤال: لو أنا و{sp} يانا ياهل{' ثاني' if another else ''}، شو احتمال إنه يكون عنده {g}؟",
            "arabizi": f"Su2al: law ana w {sp} yana yahil{' thani' if another else ''}, sh7al i7timal inna ykoon 3inda {g}?",
        }[reg]
    h, w = c.desc(m, force=True), c.desc(f, force=True)
    return {
        "en": f"Question: If {h} and {w} have {'another' if another else 'a'} child, what is the chance that the child will be affected by {g}?",
        "msa": f"السؤال: إذا أنجب {h} و{w} طفلاً{' آخر' if another else ''}، فما احتمال أن يكون الطفل مصاباً ب{g}؟",
        "gulf": f"السؤال: لو {h} و{w} ياهم ياهل{' ثاني' if another else ''}، شو احتمال إنه يكون عنده {g}؟",
        "arabizi": f"Su2al: law {h} w {w} yahum yahil{' thani' if another else ''}, sh7al i7timal inna ykoon 3inda {g}?",
    }[reg]
