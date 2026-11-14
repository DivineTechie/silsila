import pytest

from silsila_bench.parse import first_in_full_text, parse_probability, strip_reasoning


@pytest.mark.parametrize("text,value", [
    # percentages
    ("The chance is 25%.", 0.25),
    ("about 6.25 % overall", 0.0625),
    ("roughly 12.5 percent", 0.125),
    ("٢٥٪", 0.25),
    ("النسبة 25 بالمئة", 0.25),
    ("25 في المائة", 0.25),
    ("حوالي ٦٫٢٥٪", 0.0625),
    ("%25", 0.25),
    ("el i7timal 25 bil miya", 0.25),
    ("Answer: 0%", 0.0),
    # decimals
    ("Answer: 0.0123", 0.0123),
    ("p = .25", 0.25),
    ("الإجابة: ٠٫٠٦٢٥", 0.0625),
    ("The probability is 2.5e-3", 0.0025),
    # 1 in N, N in M
    ("about 1 in 4", 0.25),
    ("1 in 1,000 chance", 0.001),
    ("Answer: approximately 1 in 9,030", 1 / 9030),
    ("2 out of 3", 2 / 3),
    ("Answer: 2/3", 2 / 3),
    ("1:4", 0.25),
    ("الاحتمال هو ١ من ٤", 0.25),
    ("الاحتمال 2 من 3", 2 / 3),
    ("١ من كل ١٦", 1 / 16),
    ("1 min 4", 0.25),
    # number words
    ("one in four", 0.25),
    ("one in a thousand", 0.001),
    ("three in four", 0.75),
    ("1 in four", 0.25),
    ("واحد من كل أربعة", 0.25),
    ("واحد من أربعة", 0.25),
    ("واحد من 4", 0.25),
    ("wa7id min kil arba3a", 0.25),
    ("i7timal wa7id min arba3a", 0.25),
    # fraction words
    ("الجواب: نصف", 0.5),
    ("الاحتمال ربع", 0.25),
    ("ثلث", 1 / 3),
    ("احتمال أن يكون حاملاً هو الثلثين تقريباً", 2 / 3),
    ("ثمن", 0.125),
    ("half", 0.5),
    ("two thirds", 2 / 3),
    ("one quarter", 0.25),
    ("an eighth", 0.125),
    ("el i7timal rub3", 0.25),
    ("thilth", 1 / 3),
    ("nus", 0.5),
    ("50/50", 0.5),
])
def test_values(text, value):
    p = parse_probability(text)
    assert p.value == pytest.approx(value, rel=1e-9, abs=1e-12), (text, p)


def test_answer_line_wins_over_working():
    p = parse_probability("Kinship of first cousins is 1/16 and F = 0.0625.\nSo...\nAnswer: about 0.5%")
    assert p.value == pytest.approx(0.005) and p.source == "answer_line"
    assert first_in_full_text("Kinship is 1/16.\nAnswer: 0.5%") == pytest.approx(1 / 16)


def test_markdown_answer_line_and_last_marker():
    assert parse_probability("**Answer**: 6.25%").value == pytest.approx(0.0625)
    assert parse_probability("Answer: 1 in 2? Let me recheck.\nFinal answer: 1/8").value == pytest.approx(0.125)
    assert parse_probability("الجواب: ١ من ٨").value == pytest.approx(0.125)


def test_first_probability_when_no_answer_line():
    p = parse_probability("About 1 in 4 (25%), assuming both are carriers.")
    assert p.value == pytest.approx(0.25) and p.source == "full_text" and p.kind == "ratio"


def test_range_takes_first_value():
    p = parse_probability("20-25%")
    assert p.value == pytest.approx(0.2) and p.is_range


@pytest.mark.parametrize("text", [
    "I cannot give a number without a genetic counsellor.",
    "لا أستطيع تحديد احتمال دقيق.",
    "",
    None,
    "There are 3 children and 2 grandparents.",
    "<think>1 in 2 maybe",   # cut off inside reasoning
])
def test_no_number(text):
    p = parse_probability(text)
    assert p.value is None and p.no_number and p.kind == "none"


def test_reasoning_is_removed():
    assert parse_probability("<think>1 in 2 maybe</think> Answer: 1/8").value == pytest.approx(0.125)
    assert parse_probability("<ifm|think>نصف؟</ifm|think>\nالجواب: ربع").value == pytest.approx(0.25)
    ans, rsn = strip_reasoning("thinking without opening tag 1/2</think>Answer: 25%")
    assert ans == "Answer: 25%" and "1/2" in rsn


def test_probabilities_above_one_are_ignored():
    assert parse_probability("150% sure").value is None
    assert parse_probability("4 in 3").value is None
