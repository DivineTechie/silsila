"""SQLite storage and the tamper-evident audit log.

Records are JSON documents in a few tables. The audit log is a hash chain:
each event stores the SHA-256 of the previous event, and its own hash covers
its content plus that link. Editing or deleting any past event breaks every
hash after it, which `verify_chain` reports. Events are mirrored to FHIR
AuditEvent on export (silsila.api.fhir).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
  kind TEXT NOT NULL, id TEXT NOT NULL, case_id TEXT, body TEXT NOT NULL,
  created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY (kind, id));
CREATE INDEX IF NOT EXISTS docs_case ON docs(kind, case_id);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL,
  action TEXT NOT NULL, case_id TEXT, entity TEXT, outcome TEXT NOT NULL, detail TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
"""
GENESIS = "0" * 64


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _event_hash(prev: str, ev: dict[str, Any]) -> str:
    payload = json.dumps({k: ev[k] for k in ("seq", "ts", "actor", "role", "action", "case_id", "entity",
                                              "outcome", "detail")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


class Store:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or os.environ.get("SILSILA_DB", Path(__file__).resolve().parents[3] / "silsila.db"))
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---------------------------------------------------------- documents --
    def put(self, kind: str, doc: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            ts = now()
            doc.setdefault("created", ts)
            doc["updated"] = ts
            self.conn.execute(
                "INSERT INTO docs(kind,id,case_id,body,created,updated) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body, case_id=excluded.case_id, updated=excluded.updated",
                (kind, doc["id"], doc.get("case_id"), json.dumps(doc, ensure_ascii=False), doc["created"], ts),
            )
        return doc

    def get(self, kind: str, id_: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT body FROM docs WHERE kind=? AND id=?", (kind, id_)).fetchone()
        return json.loads(row["body"]) if row else None

    def list(self, kind: str, case_id: str | None = None) -> list[dict[str, Any]]:
        if case_id is None:
            rows = self.conn.execute("SELECT body FROM docs WHERE kind=? ORDER BY created", (kind,)).fetchall()
        else:
            rows = self.conn.execute("SELECT body FROM docs WHERE kind=? AND case_id=? ORDER BY created",
                                     (kind, case_id)).fetchall()
        return [json.loads(r["body"]) for r in rows]

    def find(self, kind: str, **where: Any) -> list[dict[str, Any]]:
        return [d for d in self.list(kind) if all(d.get(k) == v for k, v in where.items())]

    # -------------------------------------------------------------- audit --
    def audit(self, actor: str, role: str, action: str, *, case_id: str | None = None, entity: str | None = None,
              outcome: str = "success", detail: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            last = self.conn.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (last["seq"] + 1) if last else 1
            prev = last["hash"] if last else GENESIS
            ev = {"seq": seq, "ts": now(), "actor": actor, "role": role, "action": action, "case_id": case_id,
                  "entity": entity, "outcome": outcome,
                  "detail": json.dumps(detail or {}, sort_keys=True, ensure_ascii=False)}
            ev["prev_hash"] = prev
            ev["hash"] = _event_hash(prev, ev)
            self.conn.execute(
                "INSERT INTO audit(seq,ts,actor,role,action,case_id,entity,outcome,detail,prev_hash,hash) "
                "VALUES(:seq,:ts,:actor,:role,:action,:case_id,:entity,:outcome,:detail,:prev_hash,:hash)", ev)
            return ev

    def audit_events(self, case_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        q = "SELECT * FROM audit" + (" WHERE case_id=?" if case_id else "") + " ORDER BY seq DESC LIMIT ?"
        rows = self.conn.execute(q, ((case_id, limit) if case_id else (limit,))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail"])
            out.append(d)
        return out

    def verify_chain(self) -> dict[str, Any]:
        prev = GENESIS
        count = 0
        for r in self.conn.execute("SELECT * FROM audit ORDER BY seq"):
            ev = dict(r)
            count += 1
            if ev["prev_hash"] != prev or _event_hash(prev, ev) != ev["hash"]:
                return {"intact": False, "events": count, "first_broken_seq": ev["seq"]}
            prev = ev["hash"]
        return {"intact": True, "events": count, "first_broken_seq": None, "head": prev}

    def tamper_for_demo(self, seq: int) -> None:
        """Demonstration only (enabled with SILSILA_DEMO=1): edit one past event
        directly in the database, the way an insider with database access might."""
        with self._lock:
            self.conn.execute("UPDATE audit SET detail=? WHERE seq=?", (json.dumps({"edited": True}), seq))
