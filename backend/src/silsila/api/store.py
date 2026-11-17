"""SQLite (default) or PostgreSQL storage and the tamper-evident audit log.

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
from urllib.parse import urlsplit, urlunsplit

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

# PostgreSQL: same tables; TEXT body/detail so JSON and hashing round-trip exactly as in SQLite.
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS docs (
  kind TEXT NOT NULL, id TEXT NOT NULL, case_id TEXT, body TEXT NOT NULL,
  created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY (kind, id));
CREATE INDEX IF NOT EXISTS docs_case ON docs(kind, case_id);
CREATE TABLE IF NOT EXISTS audit (
  seq BIGINT PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL,
  action TEXT NOT NULL, case_id TEXT, entity TEXT, outcome TEXT NOT NULL, detail TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
"""
# Fixed advisory-lock keys (arbitrary constants): one serialises schema creation, one the audit chain.
LOCK_SCHEMA = 7_351_001
LOCK_AUDIT = 7_351_002
GENESIS = "0" * 64


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _event_hash(prev: str, ev: dict[str, Any]) -> str:
    payload = json.dumps({k: ev[k] for k in ("seq", "ts", "actor", "role", "action", "case_id", "entity",
                                              "outcome", "detail")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


def _redact(url: str) -> str:
    """The database URL without its password, safe for logs."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host = parts.hostname or ""
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    netloc = f"{parts.username or ''}:***@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class Store:
    """Document and audit storage. Backend is chosen once, at construction: PostgreSQL when
    SILSILA_DATABASE_URL starts with "postgres", otherwise SQLite (SILSILA_DB or the given path).
    An explicit `path` argument always means SQLite."""

    def __init__(self, path: str | Path | None = None, database_url: str | None = None) -> None:
        url = database_url if database_url is not None else (None if path else os.environ.get("SILSILA_DATABASE_URL"))
        self._lock = threading.RLock()
        if url and url.startswith("postgres"):
            self.backend = "postgres"
            self.path = _redact(url)
            self._init_postgres(url)
        else:
            self.backend = "sqlite"
            self.path = str(path or os.environ.get("SILSILA_DB", Path(__file__).resolve().parents[3] / "silsila.db"))
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        # WAL lets readers proceed during a write; busy_timeout waits instead of failing if another
        # process (e.g. the verify script) holds the lock.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)

    def _init_postgres(self, url: str) -> None:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(url, min_size=1, max_size=int(os.environ.get("SILSILA_DB_POOL_MAX", "10")),
                                   kwargs={"row_factory": dict_row}, open=True)
        self.pool.wait(timeout=30)
        # Several replicas may start together: serialise the DDL behind a transaction-scoped lock.
        with self.pool.connection() as c:
            c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_SCHEMA,))
            for stmt in PG_SCHEMA.split(";"):
                if stmt.strip():
                    c.execute(stmt)

    def close(self) -> None:
        if self.backend == "postgres":
            self.pool.close()
        else:
            self.conn.close()

    def ping(self) -> bool:
        """Cheap liveness check of the database (for a readiness probe)."""
        try:
            if self.backend == "postgres":
                with self.pool.connection(timeout=5) as c:
                    c.execute("SELECT 1")
            else:
                with self._lock:
                    self.conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 - any failure means "not ready"
            return False

    def reset(self) -> None:
        """Delete all documents and audit events (demo seeding only)."""
        if self.backend == "postgres":
            with self.pool.connection() as c:
                c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_AUDIT,))
                c.execute("DELETE FROM docs")
                c.execute("DELETE FROM audit")
        else:
            with self._lock:
                self.conn.executescript("DELETE FROM docs; DELETE FROM audit;")

    def _rows(self, sqlite_q: str, params: tuple = ()) -> list[Any]:
        """Run a SELECT on either backend (queries are written with ? and translated to %s for PG)."""
        if self.backend == "postgres":
            with self.pool.connection() as c:
                return c.execute(sqlite_q.replace("?", "%s"), params).fetchall()
        # One connection is shared by the server's worker threads: every statement holds the lock.
        with self._lock:
            return self.conn.execute(sqlite_q, params).fetchall()

    # ---------------------------------------------------------- documents --
    def put(self, kind: str, doc: dict[str, Any]) -> dict[str, Any]:
        ts = now()
        doc.setdefault("created", ts)
        doc["updated"] = ts
        sql = ("INSERT INTO docs(kind,id,case_id,body,created,updated) VALUES(?,?,?,?,?,?) "
               "ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body, case_id=excluded.case_id, updated=excluded.updated")
        params = (kind, doc["id"], doc.get("case_id"), json.dumps(doc, ensure_ascii=False), doc["created"], ts)
        if self.backend == "postgres":
            with self.pool.connection() as c:
                c.execute(sql.replace("?", "%s"), params)
        else:
            with self._lock:
                self.conn.execute(sql, params)
        return doc

    def get(self, kind: str, id_: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT body FROM docs WHERE kind=? AND id=?", (kind, id_))
        return json.loads(rows[0]["body"]) if rows else None

    def list(self, kind: str, case_id: str | None = None) -> list[dict[str, Any]]:
        if case_id is None:
            rows = self._rows("SELECT body FROM docs WHERE kind=? ORDER BY created", (kind,))
        else:
            rows = self._rows("SELECT body FROM docs WHERE kind=? AND case_id=? ORDER BY created", (kind, case_id))
        return [json.loads(r["body"]) for r in rows]

    def find(self, kind: str, **where: Any) -> list[dict[str, Any]]:
        return [d for d in self.list(kind) if all(d.get(k) == v for k, v in where.items())]

    # -------------------------------------------------------------- audit --
    def audit(self, actor: str, role: str, action: str, *, case_id: str | None = None, entity: str | None = None,
              outcome: str = "success", detail: dict[str, Any] | None = None) -> dict[str, Any]:
        detail_json = json.dumps(detail or {}, sort_keys=True, ensure_ascii=False)
        cols = "seq,ts,actor,role,action,case_id,entity,outcome,detail,prev_hash,hash"

        def build(last: Any) -> dict[str, Any]:
            ev = {"seq": (last["seq"] + 1) if last else 1, "ts": now(), "actor": actor, "role": role, "action": action,
                  "case_id": case_id, "entity": entity, "outcome": outcome, "detail": detail_json}
            ev["prev_hash"] = last["hash"] if last else GENESIS
            ev["hash"] = _event_hash(ev["prev_hash"], ev)
            return ev

        if self.backend == "postgres":
            # The advisory lock is held until the transaction ends, so replicas append one at a time
            # and each reads the true chain head.
            with self.pool.connection() as c:
                c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_AUDIT,))
                ev = build(c.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone())
                c.execute(f"INSERT INTO audit({cols}) VALUES(%(seq)s,%(ts)s,%(actor)s,%(role)s,%(action)s,%(case_id)s,"
                          "%(entity)s,%(outcome)s,%(detail)s,%(prev_hash)s,%(hash)s)", ev)
            return ev
        with self._lock:
            # SQLite: BEGIN IMMEDIATE so a second process cannot append between our read and insert.
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                ev = build(self.conn.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone())
                self.conn.execute(
                    f"INSERT INTO audit({cols}) "
                    "VALUES(:seq,:ts,:actor,:role,:action,:case_id,:entity,:outcome,:detail,:prev_hash,:hash)", ev)
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            return ev

    def audit_events(self, case_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        q = "SELECT * FROM audit" + (" WHERE case_id=?" if case_id else "") + " ORDER BY seq DESC LIMIT ?"
        rows = self._rows(q, ((case_id, limit) if case_id else (limit,)))
        out = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d["detail"])
            out.append(d)
        return out

    def verify_chain(self) -> dict[str, Any]:
        prev = GENESIS
        count = 0
        for r in self._rows("SELECT * FROM audit ORDER BY seq"):
            ev = dict(r)
            count += 1
            if ev["prev_hash"] != prev or _event_hash(prev, ev) != ev["hash"]:
                return {"intact": False, "events": count, "first_broken_seq": ev["seq"]}
            prev = ev["hash"]
        return {"intact": True, "events": count, "first_broken_seq": None, "head": prev}

    def tamper_for_demo(self, seq: int) -> None:
        """Demonstration only (enabled with SILSILA_DEMO=1): edit one past event
        directly in the database, the way an insider with database access might."""
        edited = json.dumps({"edited": True})
        if self.backend == "postgres":
            with self.pool.connection() as c:
                c.execute("UPDATE audit SET detail=%s WHERE seq=%s", (edited, seq))
        else:
            with self._lock:
                self.conn.execute("UPDATE audit SET detail=? WHERE seq=?", (edited, seq))
