"""Clients, runner and report with a fake OpenAI-compatible server. No network, no paid calls."""

import asyncio
import json

import pytest

from silsila_bench import items as I
from silsila_bench import report, runner
from silsila_bench.clients import load_env, parse_text_tool_calls
from silsila_bench.tools import compute_family_risk

from conftest import completion


def run(coro):
    return asyncio.run(coro)


def test_plain_answer_and_request_shape(fake_server):
    srv = fake_server(lambda body, i: (200, completion("<think>hmm 1/2</think>\nAnswer: 25%")))
    c = srv.client("gpt-oss-120b")
    res = run(c.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert res.content == "Answer: 25%" and "1/2" in res.reasoning and res.usage["completion_tokens"] == 5
    body = srv.requests[0]
    assert body["temperature"] == 0.0 and body["model"] == "accounts/fireworks/models/gpt-oss-120b"
    assert "tools" not in body


def test_retries_on_429_and_500(fake_server):
    seq = [429, 500, 200]
    srv = fake_server(lambda body, i: (seq[i], completion("Answer: 1 in 4") if seq[i] == 200 else {"error": "x"}))
    res = run(srv.client().chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert res.content == "Answer: 1 in 4" and len(srv.requests) == 3


def test_no_retry_on_400(fake_server):
    import openai
    srv = fake_server(lambda body, i: (400, {"error": {"message": "bad"}}))
    with pytest.raises(openai.BadRequestError):
        run(srv.client().chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert len(srv.requests) == 1


def test_gives_up_after_max_attempts(fake_server):
    import openai
    srv = fake_server(lambda body, i: (503, {"error": "down"}))
    c = srv.client()
    c.max_attempts = 3
    with pytest.raises(openai.InternalServerError):
        run(c.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert len(srv.requests) == 3


def test_parse_text_tool_calls_formats():
    xml = ("<ifm|tool_calls>\n<ifm|tool_call>compute_family_risk\n<ifm|arg_key>gene</ifm|arg_key>\n"
           "<ifm|arg_value>HBB</ifm|arg_value>\n<ifm|arg_key>people</ifm|arg_key>\n"
           "<ifm|arg_value>[{\"id\": \"A\", \"sex\": \"male\"}]</ifm|arg_value>\n</ifm|tool_call>\n</ifm|tool_calls>")
    c = parse_text_tool_calls(xml, {"compute_family_risk"})
    assert c[0].name == "compute_family_risk" and c[0].arguments["people"][0]["id"] == "A" and c[0].arguments["gene"] == "HBB"
    js = '<ifm|tool_calls>\n<ifm|tool_call>{"name": "submit_family_tree", "arguments": {"gene": "SMN1"}}</ifm|tool_call>\n</ifm|tool_calls>'
    assert parse_text_tool_calls(js)[0].arguments == {"gene": "SMN1"}
    hermes = 'ok\n<tool_call>\n{"name": "compute_family_risk", "arguments": {"gene": "CYP21A2"}}\n</tool_call>'
    assert parse_text_tool_calls(hermes, {"compute_family_risk"})[0].arguments["gene"] == "CYP21A2"
    llama = '<|python_tag|>{"name": "compute_family_risk", "parameters": {"gene": "HBB"}}'
    assert parse_text_tool_calls(llama, {"compute_family_risk"})[0].arguments == {"gene": "HBB"}
    assert parse_text_tool_calls('{"name": "other", "arguments": {}}', {"compute_family_risk"}) == []
    assert parse_text_tool_calls("Answer: 25%", {"compute_family_risk"}) == []


def _tool_loop_handler(fam, qid, *, as_text=False):
    """Fake model: first turn calls compute_family_risk with the gold tree, second turn reports the result."""
    q = fam.question(qid)
    question = {"type": "carrier", "person": q.person} if q.type == "carrier" else {"type": "child_affected", "couple": list(q.couple)}
    args = {**fam.gold_tree(), "question": question}

    def h(body, i):
        msgs = body["messages"]
        if msgs[-1]["role"] in ("tool",) or "<tool_response>" in str(msgs[-1].get("content")):
            content = msgs[-1]["content"]
            res = json.loads(content.replace("<tool_response>", "").replace("</tool_response>", ""))
            return 200, completion(f"The engine says {res['percent']}.\nAnswer: {res['probability']}")
        if as_text:
            text = "<tool_call>\n" + json.dumps({"name": "compute_family_risk", "arguments": args}) + "\n</tool_call>"
            return 200, completion(text)
        return 200, completion(None, tool_calls=[("compute_family_risk", args)])
    return h


def test_t2_native_tool_loop(fake_server, tmp_path):
    fam = I.family_map()["one_loop-03"]
    item = next(i for i in I.build_items("T2") if i.family_id == "one_loop-03" and i.qid == "b")
    srv = fake_server(_tool_loop_handler(fam, "b"))
    c = srv.client("gpt-oss-120b")
    rec = run(runner.run_item(c, item, fam))
    assert rec["error"] is None and len(rec["turns"]) == 2
    assert rec["tool_results"][0]["probability"] == pytest.approx(fam.question("b").gold, rel=1e-9)
    assert srv.requests[0]["tools"][0]["function"]["name"] == "compute_family_risk"
    second = srv.requests[1]["messages"]
    assert second[-2]["role"] == "assistant" and isinstance(second[-2]["tool_calls"][0]["function"]["arguments"], str)
    assert second[-1]["role"] == "tool"


def test_t2_jais_style_sends_arguments_as_objects(fake_server):
    fam = I.family_map()["no_loop-04"]
    item = next(i for i in I.build_items("T2") if i.family_id == "no_loop-04" and i.qid == "a")
    srv = fake_server(_tool_loop_handler(fam, "a"))
    rec = run(runner.run_item(srv.client("jais-3-7b"), item, fam))
    assert rec["error"] is None
    assert isinstance(srv.requests[1]["messages"][-2]["tool_calls"][0]["function"]["arguments"], dict)


def test_t2_prompted_tool_mode(fake_server):
    fam = I.family_map()["multiple-04"]
    item = next(i for i in I.build_items("T2") if i.family_id == "multiple-04" and i.qid == "a")
    srv = fake_server(_tool_loop_handler(fam, "a", as_text=True))
    rec = run(runner.run_item(srv.client("llama3-med42-8b"), item, fam))
    assert rec["error"] is None and rec["turns"][0]["tool_calls_from_text"]
    first = srv.requests[0]
    assert "tools" not in first and "# Tools" in first["messages"][0]["content"]
    assert srv.requests[1]["messages"][-1]["role"] == "user" and "<tool_response>" in srv.requests[1]["messages"][-1]["content"]
    assert rec["tool_results"][0]["probability"] == pytest.approx(fam.question("a").gold, rel=1e-9)


def test_t3_single_and_incremental(fake_server):
    fam = I.family_map()["one_loop-07"]
    item = next(i for i in I.build_items("T3") if i.family_id == "one_loop-07")
    srv = fake_server(lambda b, i: (200, completion(None, tool_calls=[("submit_family_tree", fam.gold_tree())])))
    rec = run(runner.run_item(srv.client(), item, fam))
    assert rec["tool_args"][0]["gene"] == fam.locus and srv.requests[0]["tools"][0]["function"]["name"] == "submit_family_tree"

    calls = [("add_person", {"id": p.id, "sex": p.sex}) for p in fam.people.values()]
    calls += [("set_parents", {"child": p.id, "mother": p.mother, "father": p.father}) for p in fam.people.values() if p.mother]
    calls += [("set_status", {"id": p.id, "status": p.status, "affected_with": p.affected_with}) for p in fam.people.values()]
    calls += [("set_test_result", {"id": p.id, "detected": p.test_detected}) for p in fam.people.values() if p.test_detected is not None]
    calls += [("add_marriage", {"a": a, "b": b}) for a, b in fam.unions]
    script = [calls[:20], calls[20:], [("finish_family_tree", {"gene": fam.locus})]]
    srv2 = fake_server(lambda b, i: (200, completion(None, tool_calls=script[i])))
    rec = run(runner.run_item(srv2.client(), item, fam, t3_mode="incremental"))
    assert rec["error"] is None and len(rec["turns"]) == 3
    from silsila_bench.score import score_t3
    row = score_t3({rec["item_id"]: rec}, I.family_map())[0]
    assert row["identical"] and row["engine_correct"] == 2


def test_run_track_is_resumable_and_records_errors(fake_server, tmp_path):
    items = runner.select_items("T1", limit=6)
    fams = I.family_map()
    fail_ids = {items[2].item_id}

    state = {"fail": True}

    def h2(body, i):
        from silsila_bench.prompts import user_prompt
        for it in items:
            if user_prompt(fams[it.family_id], it) == body["messages"][-1]["content"] and it.item_id in fail_ids and state["fail"]:
                return 400, {"error": {"message": "bad"}}
        return 200, completion("Answer: 25%")

    srv = fake_server(h2)
    c = srv.client()
    p = run(runner.run_track(c, "T1", items, runs_dir=tmp_path, progress=False))
    recs = runner.load_records(p)
    assert len(recs) == 6 and recs[items[2].item_id]["error"] and len(runner.done_ids(p)) == 5
    n_before = len(srv.requests)
    state["fail"] = False
    run(runner.run_track(c, "T1", items, runs_dir=tmp_path, progress=False))
    assert len(srv.requests) == n_before + 1          # only the failed item is retried
    assert len(runner.done_ids(p)) == 6
    # a truncated last line (interrupted run) is ignored
    with p.open("a") as fh:
        fh.write('{"item_id": "T1:x"')
    assert len(runner.load_records(p)) == 6


def test_report_end_to_end(fake_server, tmp_path):
    fams = I.family_map()

    def h(body, i):
        return 200, completion("Answer: 1 in 4")

    srv = fake_server(h)
    items = runner.select_items("T1", families=["no_loop-01", "one_loop-02"])
    run(runner.run_track(srv.client(), "T1", items, runs_dir=tmp_path / "runs", progress=False))
    out = tmp_path / "evidence"
    assert report.main(["--runs-dir", str(tmp_path / "runs"), "--out-dir", str(out), "--skip-pubmed"]) == 0
    data = json.loads((out / "silsila_bench.json").read_text())
    assert data["items"] == {"T1": 1200, "T2": 600, "T3": 300, "T5": 50}
    m = data["models"]["gpt-oss-120b"]
    assert m["tracks"]["T1"]["status"] == "partial" and m["tracks"]["T1"]["done"] == 16
    assert "metrics" in m["tracks"]["T4"]
    assert data["models"]["jais-3-32b"]["status"] == "not run"
    md = (out / "silsila_bench.md").read_text()
    assert "not run" in md and "not a ranking" in md
    for word in ("best", "winner", "rank 1", "outperform"):
        assert word not in md.lower()
    csv_text = (out / "logs" / "bench" / "gpt-oss-120b_T1.csv").read_text()
    assert "raw_answer" in csv_text.splitlines()[0] and "Answer: 1 in 4" in csv_text


def test_load_env(tmp_path, monkeypatch):
    monkeypatch.delenv("SILSILA_TEST_KEY", raising=False)
    (tmp_path / ".env").write_text("# c\nSILSILA_TEST_KEY='abc'\n")
    load_env(tmp_path / ".env")
    import os
    assert os.environ["SILSILA_TEST_KEY"] == "abc"


def test_truncated_reasoning_without_tags_is_no_answer(fake_server):
    """Jais 3's template opens <ifm|think> in the prompt; output cut off at max_tokens has no tags at all."""
    srv = fake_server(lambda b, i: (200, completion("We need the probability... carriers are 0.82% of people ...",
                                                    finish="length")))
    res = run(srv.client("jais-3-7b").chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert res.content == "" and res.truncated_in_reasoning and "0.82%" in res.reasoning
    from silsila_bench.parse import parse_probability
    assert parse_probability(res.content).no_number
    # a non-reasoning model's truncated answer is kept
    res = run(srv.client("llama3-med42-8b").chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert res.content.startswith("We need")
    # a finished reasoning-model answer (closing tag present) keeps the text after the tag
    srv2 = fake_server(lambda b, i: (200, completion("thinking...</ifm|think>\nAnswer: 1 in 4", finish="stop")))
    res = run(srv2.client("jais-3-7b").chat([{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]))
    assert res.content == "Answer: 1 in 4" and not res.truncated_in_reasoning


def test_t2_final_turn_without_tools_after_budget(fake_server):
    fam = I.family_map()["no_loop-05"]
    item = next(i for i in I.build_items("T2") if i.family_id == "no_loop-05")

    def h(body, i):
        if "tools" not in body:
            return 200, completion("Answer: 1 in 4")
        return 200, completion(None, tool_calls=[("compute_family_risk", {"gene": "HBB", "people": []})])

    srv = fake_server(h)
    rec = run(runner.run_item(srv.client(), item, fam))
    assert len(rec["turns"]) == runner.MAX_TURNS_T2 + 1 and rec["final_content"] == "Answer: 1 in 4"
    assert all("error" in x for x in rec["tool_results"]) and len(rec["tool_results"]) == runner.MAX_TURNS_T2
