import pytest

from silsila_bench import items as I
from silsila_bench import render as R


@pytest.fixture(scope="module")
def fams():
    return I.generate_families()


@pytest.mark.parametrize("path,reg,expected", [
    (("father", "brother", "son"), "en", "my father's brother's son"),
    (("father", "brother", "son"), "msa", "ابن عمي"),
    (("father", "brother", "son"), "gulf", "ولد عمي"),
    (("father", "brother", "son"), "arabizi", "ibn 3ammi"),
    (("mother", "brother", "daughter"), "msa", "ابنة خالي"),
    (("mother", "brother", "daughter"), "gulf", "بنت خالي"),
    (("mother", "brother", "daughter"), "arabizi", "bint 5ali"),
    (("father", "sister"), "gulf", "عمتي"),
    (("mother", "sister"), "msa", "خالتي"),
    (("father", "father"), "msa", "جدي لأبي"),
    (("mother", "mother"), "gulf", "يدتي أم أمي"),
    (("father", "father", "brother", "son"), "msa", "ابن عم والدي"),
    (("father", "father", "brother", "son"), "gulf", "ولد عم أبوي"),
    (("father", "father", "father"), "msa", "جد والدي"),
    (("husband", "father"), "gulf", "أبو ريلي"),
    (("father", "brother", "son", "wife"), "arabizi", "7urmat ibn 3ammi"),
])
def test_relation_phrases(path, reg, expected):
    assert R.relation_phrase(path, reg) == expected


def test_relation_phrase_with_named_owner():
    assert R.relation_phrase(("father", "brother", "son"), "msa", owner="مريم") == "ابن عم مريم"
    assert R.relation_phrase(("father", "brother", "son"), "en", owner="Mariam") == "Mariam's father's brother's son"
    assert R.relation_phrase(("mother", "brother", "son"), "arabizi", owner="Mariam") == "ibn 5al Mariam"


def test_blood_path_goes_through_common_ancestors(fams):
    for f in fams:
        for c in f.consanguineous:
            path = R.kin_path(f, c["female"], c["male"], blood_only=True)
            assert path is not None
            # up first, then down: never a parent step after a child step
            seen_down = False
            for lab in path:
                if lab in ("son", "daughter", "brother", "sister"):
                    seen_down = True
                assert not (seen_down and lab in ("father", "mother"))


def test_story_mentions_everyone_in_every_register(fams):
    for f in fams[::7]:
        for reg in I.REGISTERS:
            s = R.story(f, reg)
            for p in f.people.values():
                name = p.name_ar if reg in ("msa", "gulf") else p.id
                assert name in s, (f.family_id, reg, name)


def test_story_states_marriages_tests_and_diagnosis(fams):
    f = next(x for x in fams if any(p.test_detected == [] for p in x.people.values())
             and any(p.test_detected for p in x.people.values()))
    en = R.story(f, "en")
    assert "has been diagnosed with" in en and "Nobody else in the family" in en
    assert "was negative" in en and "which found" in en
    assert "married" in en
    gulf = R.story(f, "gulf")
    assert "طلع سلبي" in gulf and "معرّس" in gulf or "ماخذ" in gulf


def test_cousin_marriage_expressed_relationally(fams):
    f = next(x for x in fams if x.family_type == "one_loop")
    c = f.consanguineous[0]
    s = R.story(f, "en")
    assert "'s" in s and ("brother's" in s or "sister's" in s)


def test_rendering_is_deterministic(fams):
    f = fams[33]
    for reg in I.REGISTERS:
        assert R.story(f, reg) == R.story(f, reg)
        assert R.question_text(f, "a", reg) == R.question_text(f, "a", reg)


def test_facts_contain_parameters():
    en = R.facts("SMN1", "en")
    assert "91.2%" in en and "F = 0.0222" in en and "1.43%" in en
    hbb = R.facts("HBB", "msa")
    assert "4.56%" in hbb and "2.90%" in hbb


def test_questions(fams):
    f = fams[5]
    qa = R.question_text(f, "a", "en")
    assert qa.startswith("Question: What is the chance that") and f.question("a").person in qa
    qb = R.question_text(f, "b", "gulf")
    assert "احتمال" in qb


def test_arabic_templates_flag_missing_native_review():
    import inspect
    assert "WITHOUT native-speaker review" in inspect.getsource(R)
