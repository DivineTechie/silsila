"""The guide answers questions about the tool with fixed text and live lookups. No language model."""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from silsila import guide as guide_mod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SILSILA_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("SILSILA_DEMO_FAMILY_PASSWORD", "test-family-pw")
    monkeypatch.setenv("SILSILA_DEMO_COUNSELLOR_PASSWORD", "test-counsellor-pw")
    monkeypatch.setenv("SILSILA_DEMO", "1")
    from silsila.api import app as app_mod, seed, store as store_mod
    importlib.reload(app_mod)
    s = store_mod.Store()
    seed.seed(s)
    app_mod._store = s
    return TestClient(app_mod.app)


def ask(client, text=None, lang="en", id=None):
    r = client.post("/api/guide/ask", json={"text": text, "id": id, "lang": lang})
    assert r.status_code == 200, r.text
    return r.json()


def test_every_listed_question_finds_its_own_answer_in_both_languages(client):
    topics = client.get("/api/guide").json()["topics"]
    assert len(topics) >= 20
    for t in topics:
        for lang, q in (("en", t["q_en"]), ("ar", t["q_ar"])):
            out = ask(client, q, lang)
            assert out["kind"] == "answer" and out["id"] == t["id"], (q, out.get("id"))
            assert out["answer"] and out["sources"] and "not generated" in out["method"]


PARAPHRASES = [
    ("how much load can it handle", "hosting"), ("how many users at once", "hosting"), ("ما هي القوانين في الإمارات", "law"),
    ("what is silsila", "what"), ("is this an AI chatbot?", "is_this_ai"), ("are you a robot", "is_this_ai"),
    ("how accurate is the engine", "accuracy"), ("what is the chance for a first cousin with thalassaemia", "relationship"),
    ("does AI write the messages", "no_ai_text"), ("where is it hosted and how fast", "hosting"),
    ("why not use ChatGPT", "why_not_llm"), ("why not just ask a chatbot", "why_not_llm"),
    ("who decides who is told", "who_decides"), ("can records be tampered with", "audit"),
    ("what is measured as success", "measures"), ("is it a medical device", "limits"), ("what about data security", "privacy"),
    ("how much does it cost", "pilot"), ("which diseases are covered", "conditions"),
    ("how do you fit the national genomics masterplan", "programmes"), ("how does FHIR import work with Malaffi", "fhir"),
    ("does it support Arabic and read aloud", "language"), ("does it tell couples whether to marry", "options"),
    ("why does consanguinity matter", "why_cousins"), ("how does voice intake work", "voice"),
    ("what would 250 index newborns a year mean", "scenario"), ("how is the chance calculated", "engine"),
    ("what happens with a suicidal message", "hard_questions"),
    # questions people type that the first set of answers did not cover (added 17 Nov 2026)
    ("who built this", "who_built"), ("who is behind this project", "who_built"), ("is the code open source", "code"),
    ("where can I see the code", "code"), ("how do I try the demo", "try_demo"), ("do I need a password", "try_demo"),
    ("what roles can I log in as", "try_demo"), ("what is the family twin", "twin"), ("what is watch a cascade", "cascade_demo"),
    ("what is a carrier", "glossary"), ("what does recessive mean", "glossary"), ("what does the relative see", "relative_view"),
    ("what is in the invitation", "relative_view"), ("can a relative say no", "decline"), ("can someone opt out", "decline"),
    ("what is the comprehension check", "teachback"), ("what is teach back", "teachback"),
    ("what does the counsellor do", "counsellor"), ("how much counsellor time does it save", "counsellor"),
    ("what tech stack is it built with", "stack"), ("what programming language", "stack"), ("how many tests does it have", "tests"),
    ("how is it different from premarital screening", "vs_premarital"), ("what about religion and culture", "culture"),
    ("is it halal", "culture"), ("does it diagnose disease", "diagnose"), ("does it comply with UAE data protection law", "law"),
    ("what models does it use", "models_used"), ("what are the hazards", "hazards"), ("what is the roadmap", "roadmap"),
    ("what comes next", "roadmap"), ("what if the family tree is wrong", "tree_wrong"), ("does it work on a phone", "device"),
    ("does it work offline", "device"), ("how does a case close", "closure"), ("what happens after the relative is tested", "closure"),
    ("what does silsila mean", "name"), ("why is it called silsila", "name"), ("what is the judging criteria fit", "criteria"),
    ("how are relatives contacted, sms or email", "contact"), ("do you send whatsapp messages", "contact"),
    ("is this real patient data", "demo_data"), ("which model was best", "why_not_llm"), ("what is silsila bench", "why_not_llm"),
    ("whats the differnce between this and a chatbot", "is_this_ai"),
    ("هل يكتب الذكاء الاصطناعي الرسائل؟", "no_ai_text"), ("ما حدود النظام", "limits"), ("كيف يحسب الاحتمال", "engine"),
]


@pytest.mark.parametrize("question,expected", PARAPHRASES)
def test_questions_in_other_words_reach_the_right_answer(client, question, expected):
    lang = "ar" if any("؀" <= c <= "ۿ" for c in question) else "en"
    out = ask(client, question, lang)
    assert out["kind"] == "answer" and out["id"] == expected, (question, out.get("id"), out.get("method"))


@pytest.mark.parametrize("question", ["what's the weather in Dubai", "pizza", "hello", "tell me a joke", "how do I cook rice",
                                      "who won the world cup", "what is the capital of France", "asdf qwer zxcv"])
def test_the_guide_says_so_when_it_has_no_answer(client, question):
    out = ask(client, question)
    assert out["kind"] == "no_match" and "will not guess" in out["answer"] and len(out["suggestions"]) >= 3
    assert "facts" not in out  # nothing is looked up or invented for a question it cannot answer


@pytest.mark.parametrize("question,lang", [
    ("should I end my pregnancy?", "en"), ("I want to die", "en"), ("my son has thalassaemia, what should we do", "en"),
    ("what does my result mean", "en"), ("am I a carrier?", "en"), ("can we have a healthy baby", "en"),
    ("هل أتزوج ابنة عمي؟", "ar"), ("ما معنى نتيجتي", "ar"),
])
def test_personal_and_urgent_questions_are_not_answered(client, question, lang):
    out = ask(client, question, lang)
    assert out["kind"] == "handoff" and "998" in out["answer"] and "999" in out["answer"]
    assert "facts" not in out and "id" not in out


def test_every_lookup_runs_and_names_its_sources(client):
    g = guide_mod.guide()
    seen = set()
    for e in g.entries:
        out = ask(client, id=e["id"])
        if e.get("tool"):
            seen.add(e["tool"])
            assert out["tool"]["name"] == e["tool"] and out["facts"], e["id"]
            for f in out["facts"]:
                assert f["label"] and f["value"] and f["source"], (e["id"], f)
                assert f["label"] != "Lookup failed", (e["id"], f)
        else:
            assert out["facts"] == [] and out["tool"] is None
    assert seen == set(guide_mod.TOOLS)  # no lookup is defined and unused


def test_lookups_return_what_the_real_tools_return(client):
    rel = {f["label"]: f["value"] for f in ask(client, "chance for a sibling or cousin with CAH")["facts"]}
    assert rel["Parent of the affected child"].startswith("100%")
    assert 66.0 < float(rel["Brother or sister with no signs of the condition"].split("%")[0]) < 68.0  # two in three, plus the background rate
    assert 24.0 < float(rel["First cousin"].split("%")[0]) < 27.0
    assert "CYP21A2" in rel["Condition used"]
    assert "HBB" in {f["label"]: f["value"] for f in ask(client, "chance for a cousin with thalassaemia")["facts"]}["Condition used"]

    gate = {f["label"]: f["value"] for f in ask(client, id="no_ai_text")["facts"]}
    assert gate["Gate result, just now"].startswith("Blocked")

    chain = {f["label"]: f["value"] for f in ask(client, id="audit")["facts"]}
    assert chain["Audit chain on this server, verified just now"] == "intact"

    sc = {f["label"]: f["value"] for f in ask(client, "what would 250 index families a year mean")["facts"]}
    assert sc["Index families a year (from your question, or 100)"] == "250" and sc["Tests, at 5 offered per family"] == "1,250"
    b4 = json.loads((guide_mod.EVIDENCE / "b4_uae.json").read_text())["results"]["theta_calibrated"]["loci"]["CYP21A2"]["atrisk_couples"]
    row = next(r for r in b4 if r["budget_tests_per_family"] == 5)
    assert f"about {row['ranked_per_1000_tests'] * 1.25:.0f} " in sc["CAH: at-risk couples found (PROJECTION)"]

    acc = {f["label"]: f["value"] for f in ask(client, id="accuracy")["facts"]}
    assert acc["Textbook cases passed"] == "67 of 67" and acc["Malformed or impossible inputs answered silently"] == "0 of 237"


def test_no_language_model_is_called_and_the_question_is_not_stored(client, monkeypatch):
    import httpx
    def boom(*a, **k):
        raise AssertionError("the guide must not call any outside service")
    monkeypatch.setattr(httpx, "post", boom)
    monkeypatch.setattr(httpx.Client, "post", boom)
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "x")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "x")
    secret = "zebra-quokka how accurate is the engine"
    assert ask(client, secret)["id"] == "accuracy"
    cou = {"Authorization": f"Bearer {client.post('/api/demo/login', json={'persona': 'counsellor'}).json()['token']}"}
    events = [e for e in client.get("/api/audit", headers=cou).json()["events"] if e["action"] == "guide.ask"]
    assert events and events[0]["detail"]["matched"] == "accuracy"
    assert "zebra" not in json.dumps(events)
    src = (guide_mod.GUIDE_FILE.parents[2] / "backend" / "src" / "silsila" / "guide.py").read_text()
    assert "model_labels" not in src and "openai" not in src.lower() and "httpx" not in src


def test_arabic_answers_are_arabic_and_empty_questions_are_refused(client):
    out = ask(client, id="what", lang="ar")
    assert any("؀" <= c <= "ۿ" for c in out["answer"]) and any("؀" <= c <= "ۿ" for c in out["not_ai"])
    assert client.post("/api/guide/ask", json={"text": "  ", "lang": "en"}).status_code == 422
    assert client.post("/api/guide/ask", json={"text": "x" * 500, "lang": "en"}).status_code == 422
    assert ask(client, id="nope")["kind"] == "no_match"


@pytest.mark.parametrize("question,expected,read_as", [
    ("how acurate is the calculaton", {"engine", "accuracy"}, {"acurate": "accurate", "calculaton": "calculation"}),
    ("hw does the engin wrk", {"engine"}, {"engin": "engine"}),
    ("tell me about privcy", {"privacy"}, {"privcy": "privacy"}),
])
def test_misspelt_words_are_read_as_the_closest_known_word_and_the_answer_says_so(client, question, expected, read_as):
    out = ask(client, question)
    assert out["kind"] == "answer" and out["id"] in expected, (question, out.get("id"))
    read = next(s for s in out["steps"] if s["kind"] == "read")["detail"]
    for wrong, right in read_as.items():
        assert f"Read '{wrong}' as '{right}'" in read


def test_every_answer_shows_the_steps_that_produced_it(client):
    out = ask(client, "what is the family twin")
    kinds = [s["kind"] for s in out["steps"]]
    assert kinds == ["read", "safety", "match", "lookup", "answer"]
    assert "50 fixed answers" in out["steps"][2]["detail"] or "fixed answers" in out["steps"][2]["detail"]
    assert "Nothing was generated" in out["steps"][-1]["detail"]
    assert all(isinstance(s["ms"], (int, float)) for s in out["steps"])
    none = ask(client, "who won the world cup")
    assert [s["kind"] for s in none["steps"]] == ["read", "safety", "match", "answer"] and "does not guess" in none["steps"][-1]["detail"]
    stop = ask(client, "should I end my pregnancy?")
    assert [s["kind"] for s in stop["steps"]] == ["read", "safety"] and "does not answer" in stop["steps"][-1]["detail"]
    listed = ask(client, id="twin")
    assert listed["steps"][0]["detail"].startswith("A question from the list")


def test_the_server_image_carries_every_file_a_lookup_reads():
    # the hosted guide reported "Lookup failed" for the hazard log because the image did not include the file
    from pathlib import Path
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert "docs/evidence/*.json" in dockerfile and "docs/governance/hazard-log.md" in dockerfile

