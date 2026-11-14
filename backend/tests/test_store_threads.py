"""The API shares one SQLite connection across worker threads; concurrent reads and writes must not
interfere (a race here once made a valid session look like an unknown user)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from silsila.api.store import Store


def test_concurrent_reads_and_audit_writes(tmp_path):
    s = Store(tmp_path / "t.db")
    for i in range(20):
        s.put("user", {"id": f"u{i}", "role": "counsellor"})

    def work(i: int) -> bool:
        ok = s.get("user", f"u{i % 20}") is not None
        s.audit(f"u{i % 20}", "counsellor", "test.read")
        return ok and len(s.list("user")) == 20

    with ThreadPoolExecutor(16) as ex:
        assert all(ex.map(work, range(2000)))
    assert s.verify_chain()["intact"]
