"""Production hardening: settings check, token claims, middleware, health probes."""

from __future__ import annotations

import importlib
import json
import logging

import jwt
import pytest
from fastapi.testclient import TestClient

from silsila.api import auth, settings

GOOD = {
    "SILSILA_DEMO": "0",
    "SILSILA_SECRET": "x" * 40,
    "SILSILA_CORS": "https://app.example",
    "SILSILA_DATABASE_URL": "postgresql://u:p@db/silsila",
}
ALL = ["SILSILA_DEMO", "SILSILA_SECRET", "SILSILA_CORS", "SILSILA_DATABASE_URL", "SILSILA_DEMO_FAMILY_PASSWORD",
       "SILSILA_DEMO_COUNSELLOR_PASSWORD", "SILSILA_MAX_BODY_BYTES", "SILSILA_LOGIN_PER_MIN"]


def env(monkeypatch, **kw):
    for k in ALL:
        monkeypatch.delenv(k, raising=False)
    for k, v in kw.items():
        monkeypatch.setenv(k, v)


# ---------------------------------------------------------------- settings --
def test_production_accepts_good_settings(monkeypatch):
    env(monkeypatch, **GOOD)
    settings.check_production()


def test_production_lists_every_problem(monkeypatch):
    env(monkeypatch, SILSILA_DEMO="0", SILSILA_SECRET="short", SILSILA_CORS="*",
        SILSILA_DEMO_FAMILY_PASSWORD="x", SILSILA_DEMO_COUNSELLOR_PASSWORD="y")
    with pytest.raises(settings.ConfigError) as e:
        settings.check_production()
    msg = str(e.value)
    for needle in ("SILSILA_SECRET", "SILSILA_CORS", "SILSILA_DATABASE_URL",
                   "SILSILA_DEMO_FAMILY_PASSWORD", "SILSILA_DEMO_COUNSELLOR_PASSWORD"):
        assert needle in msg
    assert "short" not in msg  # never echo secret values


@pytest.mark.parametrize("key,val", [("SILSILA_SECRET", ""), ("SILSILA_SECRET", "y" * 31), ("SILSILA_CORS", ""),
                                     ("SILSILA_CORS", "https://a.example,*"),
                                     ("SILSILA_DATABASE_URL", "sqlite:///x.db")])
def test_production_rejects_each(monkeypatch, key, val):
    env(monkeypatch, **{**GOOD, key: val})
    with pytest.raises(settings.ConfigError):
        settings.check_production()


def test_demo_only_warns(monkeypatch, caplog):
    env(monkeypatch, SILSILA_DEMO="1")
    with caplog.at_level(logging.WARNING, logger="silsila.settings"):
        settings.check_production()
    assert "Demo mode" in caplog.text


# ------------------------------------------------------------------- tokens --
def test_token_claims_and_verification(monkeypatch):
    tok = auth.issue({"id": "u1", "role": "family"})
    claims = auth.decode(tok)
    assert claims["iss"] == "silsila" and claims["aud"] == "silsila" and claims["sub"] == "u1"
    for bad in ({"iss": "other", "aud": "silsila"}, {"iss": "silsila", "aud": "other"}, {"sub": "u1"}):
        payload = {"sub": "u1", "role": "family", "exp": 4102444800, **bad}
        forged = jwt.encode(payload, auth._secret(), algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            auth.decode(forged)


def test_secret_required_in_production(monkeypatch):
    env(monkeypatch, SILSILA_DEMO="0")
    with pytest.raises(RuntimeError):
        auth._load_secret()
    env(monkeypatch, SILSILA_DEMO="0", SILSILA_SECRET="z" * 40)
    assert auth._load_secret() == "z" * 40


def test_demo_random_secret_warns(monkeypatch, caplog):
    env(monkeypatch, SILSILA_DEMO="1")
    with caplog.at_level(logging.WARNING, logger="silsila.auth"):
        assert len(auth._load_secret()) == 64
    assert "restart" in caplog.text


# ------------------------------------------------------------------ app ----
def make_client(monkeypatch, tmp_path, **kw):
    env(monkeypatch, SILSILA_DB=str(tmp_path / "t.db"), **kw)
    monkeypatch.setenv("SILSILA_DB", str(tmp_path / "t.db"))
    from silsila.api import app as app_mod, store as store_mod
    importlib.reload(app_mod)
    if kw.get("SILSILA_DEMO") == "1":  # production wants Postgres, which these tests do not need
        app_mod._store = store_mod.Store()
    return app_mod, TestClient(app_mod.app)


@pytest.fixture()
def demo(monkeypatch, tmp_path):
    yield make_client(monkeypatch, tmp_path, SILSILA_DEMO="1")[1]
    env(monkeypatch)  # leave no state behind for other modules


@pytest.fixture()
def prod(monkeypatch, tmp_path):
    yield make_client(monkeypatch, tmp_path, **GOOD)[1]
    env(monkeypatch)


def test_production_app_refuses_bad_config(monkeypatch, tmp_path):
    from silsila.api import app as app_mod
    env(monkeypatch, SILSILA_DEMO="0")
    with pytest.raises(settings.ConfigError):
        importlib.reload(app_mod)
    env(monkeypatch)
    importlib.reload(app_mod)  # restore a demo-mode module for later tests


def test_production_hides_docs_and_sets_hsts(prod):
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert prod.get(p).status_code == 404
    r = prod.get("/api/live")
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")


def test_demo_keeps_docs_and_no_hsts(demo):
    assert demo.get("/openapi.json").status_code == 200
    assert "strict-transport-security" not in demo.get("/api/live").headers


def test_security_headers_and_request_id(demo):
    r = demo.get("/api/live", headers={"X-Request-ID": "abc-12345678"})
    assert r.headers["x-request-id"] == "abc-12345678"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    r = demo.get("/api/live", headers={"X-Request-ID": "bad id\twith junk"})
    assert r.headers["x-request-id"] != "bad id\twith junk" and len(r.headers["x-request-id"]) == 32
    r = demo.get("/api/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401 and r.headers["cache-control"] == "no-store"


def test_access_log_redacts_invitation_token(demo, caplog):
    secret = "SECRETCODE123456"
    with caplog.at_level(logging.INFO, logger="silsila.access"):
        demo.get(f"/api/r/{secret}?lang=en&x=querysecret", headers={"Authorization": "Bearer tokenvalue"})
        demo.get(f"/api/r/{secret}/topics/whatever")
        demo.post(f"/api/r/{secret}/respond?action=book")
        demo.get(f"/api/r/{secret}/no/such/route")
    assert secret not in caplog.text and "querysecret" not in caplog.text and "tokenvalue" not in caplog.text
    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "silsila.access"]
    assert len(lines) == 4
    assert lines[0]["path"] == "/api/r/:token"
    assert lines[1]["path"] == "/api/r/:token/topics/:topic_id"
    assert lines[3]["path"].startswith("/api/r/:token")
    assert set(lines[0]) == {"method", "path", "status", "ms", "request_id", "client"}
    assert "testclient" not in caplog.text


def test_body_limit_413(monkeypatch, tmp_path):
    _, c = make_client(monkeypatch, tmp_path, SILSILA_DEMO="1", SILSILA_MAX_BODY_BYTES="1000")
    r = c.post("/api/auth/login", content=b"x" * 5000, headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert c.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code == 401
    # chunked body with no Content-Length
    r = c.post("/api/auth/login", content=iter([b"x" * 600, b"x" * 600]),
               headers={"content-type": "application/json"})
    assert r.status_code == 413
    env(monkeypatch)


def test_default_limit_admits_fhir_bundle_size(demo):
    from silsila.api import fhir_import
    assert settings.load().max_body_bytes > fhir_import.MAX_BYTES


def test_login_rate_limit_429(monkeypatch, tmp_path):
    _, c = make_client(monkeypatch, tmp_path, SILSILA_DEMO="1", SILSILA_LOGIN_PER_MIN="3")
    codes = [c.post("/api/auth/login", json={"username": "a", "password": "b"}).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    r = c.post("/api/auth/login", json={"username": "a", "password": "b"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.headers["x-content-type-options"] == "nosniff"
    env(monkeypatch)


def test_live_and_ready(demo):
    assert demo.get("/api/live").json() == {"ok": True}
    assert demo.get("/api/ready").status_code == 200
    assert demo.get("/api/health").status_code == 200


def test_ready_503_when_database_down(monkeypatch, tmp_path):
    app_mod, c = make_client(monkeypatch, tmp_path, SILSILA_DEMO="1")

    class Down:
        def ping(self):
            raise ConnectionError("db down")
    app_mod._store = Down()
    assert c.get("/api/ready").status_code == 503
    assert c.get("/api/live").status_code == 200
    env(monkeypatch)
