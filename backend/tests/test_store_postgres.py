"""Store contract, run against SQLite always and against PostgreSQL when SILSILA_TEST_DATABASE_URL is set.
Includes a multi-replica audit-chain concurrency test (PostgreSQL only)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from silsila.api.store import Store

PG_URL = os.environ.get("SILSILA_TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(not PG_URL, reason="SILSILA_TEST_DATABASE_URL not set")


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=needs_pg)])
def store(request, tmp_path):
    s = Store(database_url=PG_URL) if request.param == "postgres" else Store(tmp_path / "t.db")
    s.reset()
    assert s.backend == request.param
    yield s
    s.reset()
    s.close()


def test_ping_and_path(store):
    assert store.ping() is True
    assert "test@" not in store.path and ":***@" in store.path if store.backend == "postgres" else True


def test_documents(store):
    store.put("case", {"id": "c1", "case_id": "c1", "title": "عنوان"})
    store.put("note", {"id": "n1", "case_id": "c1", "text": "a"})
    store.put("note", {"id": "n2", "case_id": "c2", "text": "b"})
    assert store.get("case", "c1")["title"] == "عنوان"
    assert store.get("case", "nope") is None
    assert [d["id"] for d in store.list("note", "c1")] == ["n1"]
    assert {d["id"] for d in store.list("note")} == {"n1", "n2"}
    assert [d["id"] for d in store.find("note", text="b")] == ["n2"]
    store.put("note", {"id": "n1", "case_id": "c1", "text": "changed"})  # upsert
    assert len(store.list("note")) == 2 and store.get("note", "n1")["text"] == "changed"


def test_audit_chain_and_tamper(store):
    assert store.verify_chain() == {"intact": True, "events": 0, "first_broken_seq": None, "head": "0" * 64}
    for i in range(5):
        ev = store.audit("a", "counsellor", "x", case_id="c1" if i % 2 else None, detail={"i": i, "ar": "ي"})
        assert ev["seq"] == i + 1
    assert store.verify_chain()["intact"] and store.verify_chain()["events"] == 5
    assert [e["seq"] for e in store.audit_events(limit=2)] == [5, 4]
    assert len(store.audit_events(case_id="c1")) == 2
    assert store.audit_events(limit=1)[0]["detail"] == {"i": 4, "ar": "ي"}
    store.tamper_for_demo(3)
    assert store.verify_chain() == {"intact": False, "events": 3, "first_broken_seq": 3}


def test_reset(store):
    store.put("user", {"id": "u"})
    store.audit("a", "r", "x")
    store.reset()
    assert store.list("user") == [] and store.verify_chain()["events"] == 0
    assert store.audit("a", "r", "x")["seq"] == 1


@needs_pg
def test_replicas_append_concurrently():
    replicas = [Store(database_url=PG_URL) for _ in range(3)]
    replicas[0].reset()
    per_thread, threads = 100, 4

    def work(args: tuple[int, int]) -> None:
        r, t = args
        for i in range(per_thread):
            replicas[r].audit(f"r{r}t{t}", "system", "load", detail={"i": i})

    jobs = [(r, t) for r in range(len(replicas)) for t in range(threads)]
    with ThreadPoolExecutor(len(jobs)) as ex:
        list(ex.map(work, jobs))
    total = len(jobs) * per_thread
    res = replicas[0].verify_chain()
    assert res["intact"] and res["events"] == total
    seqs = sorted(e["seq"] for e in replicas[1].audit_events(limit=total + 10))
    assert seqs == list(range(1, total + 1))
    replicas[0].reset()
    for r in replicas:
        r.close()


@needs_pg
def test_concurrent_startup_is_safe():
    # Many replicas creating the schema at once must not fail.
    with ThreadPoolExecutor(6) as ex:
        stores = list(ex.map(lambda _: Store(database_url=PG_URL), range(6)))
    for s in stores:
        s.close()
