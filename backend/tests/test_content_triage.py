from __future__ import annotations

import pytest

from silsila.content import GateError, Message, registry
from silsila.triage import classify, reply_for


def test_registry_loads_and_hashes_verify():
    reg = registry()
    assert len(reg.paragraphs) > 100
    assert {"mp:21-hydroxylase-deficiency", "mp:beta-thalassemia", "mp:sickle-cell-disease",
            "mp:spinal-muscular-atrophy"} <= set(reg.documents)


def test_every_template_renders_in_both_languages():
    reg = registry()
    for tid, t in reg.templates.items():
        import re
        names = set(re.findall(r"\{(\w+)\}", t["en"]))
        assert names == set(re.findall(r"\{(\w+)\}", t["ar"])), f"{tid}: placeholders differ between en and ar"
        params = {n: "X" for n in names}
        for lang in ("en", "ar"):
            assert reg.template_text(tid, lang, params)


def test_teachback_answers_are_supported_by_cited_paragraphs():
    reg = registry()
    expect = {"tb.chance_each_pregnancy": "25 percent", "tb.carriers_usually_well": "typically do not show",
              "tb.same_each_pregnancy": "applies equally to each pregnancy"}
    for q in reg.teachback:
        if q["id"] in expect:
            assert expect[q["id"]] in reg.paragraphs[q["evidence"]].text


def test_gate_blocks_altered_text():
    reg = registry()
    msg = reg.template(Message("en"), "reply.decision_request")
    reg.gate(msg)
    msg.parts[0]["text"] = msg.parts[0]["text"].replace("cannot tell you what to decide", "recommends you do not marry")
    with pytest.raises(GateError):
        reg.gate(msg)


def test_gate_blocks_altered_quote_and_us_paragraph():
    reg = registry()
    msg = reg.quote(Message("en"), "mp:risk-assessment:0:2")
    msg.parts[0]["text"] += " You should not have children."
    with pytest.raises(GateError):
        reg.gate(msg)
    with pytest.raises(GateError):
        reg.quote(Message("en"), "mp:genetic-discrimination:0:1")


def test_gate_rejects_links_and_markup_in_parameters():
    reg = registry()
    with pytest.raises(GateError):
        reg.template(Message("en"), "invite.with_sender", {"sender": "<script>"})
    with pytest.raises(GateError):
        reg.template(Message("en"), "invite.with_sender", {"sender": "visit https://x.example"})


@pytest.mark.parametrize("text,label", [
    ("I can't cope, I want to end my life", "crisis"),
    ("ابي اموت ما اقدر", "crisis"),
    ("Should we cancel the wedding?", "decision_request"),
    ("شو اسوي؟ نلغي الزواج؟", "decision_request"),
    ("Is it haram to marry my cousin?", "religious"),
    ("هل يجوز الزواج من ابنة عمي", "religious"),
    ("What is my husband's result?", "third_party"),
    ("مين ارسل هذي الرسالة", "third_party"),
    ("I'm so scared and it feels like my fault", "distress"),
    ("how do i get tested", "booking"),
])
def test_rules_catch_core_cases(text, label):
    assert label in classify(text, "ar" if any("؀" <= c <= "ۿ" for c in text) else "en", use_model=False).labels


def test_reply_is_non_directive_and_escalates():
    r = classify("Is it haram? Should we cancel the marriage?", "en", use_model=False)
    msg = reply_for(r, "en")
    assert msg.escalate
    ids = [p["id"] for p in msg.parts]
    assert ids[:2] == ["reply.decision_request", "reply.religious"]


def test_crisis_reply_comes_first_and_has_emergency_numbers():
    msg = reply_for(classify("I want to kill myself, should we cancel?", "en", use_model=False), "en")
    assert msg.parts[0]["id"] == "reply.crisis" and "998" in msg.parts[0]["text"]


def test_information_reply_quotes_sources_verbatim():
    msg = reply_for(classify("What does it mean to be a carrier?", "en", use_model=False), "en")
    assert msg.parts[0]["id"] == "reply.information"
    assert all(p["type"] == "source" for p in msg.parts[1:-1]) and len(msg.parts) > 2
    assert msg.parts[-1]["id"] == "safety.footer"
    # queue priority may still be raised by the recall-tuned model; the reply itself is plain information
    assert not any(p["id"].startswith("reply.") and p["id"] != "reply.information" for p in msg.parts)


def test_unknown_message_is_forwarded_and_shows_emergency_numbers():
    msg = reply_for(classify("hmm", "en", use_model=False), "en")
    assert msg.parts[0]["id"] == "reply.forwarded"
    assert msg.parts[-1]["id"] == "safety.footer" and "998" in msg.parts[-1]["text"]
