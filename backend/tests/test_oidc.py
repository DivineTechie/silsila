"""OIDC login against a fully local mock identity provider (no network)."""

from __future__ import annotations

import base64
import hashlib
import time
import urllib.parse

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("cryptography")  # needed by pyjwt for RS256; see docs/identity-oidc.md
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from silsila.api import auth, oidc  # noqa: E402
from silsila.api.store import Store  # noqa: E402

ISSUER = "https://idp.test"
CLIENT_ID = "silsila-web"
REDIRECT = "http://localhost:8000/api/auth/oidc/family/callback"
POST_LOGIN = "http://localhost:5173/"


def new_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk_for(key, kid):
    d = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**d, "kid": kid, "use": "sig", "alg": "RS256"}


class MockIdP:
    def __init__(self):
        self.key, self.kid = new_key(), "k1"
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []
        self.id_token: str | None = None

    def jwks(self):
        return {"keys": [jwk_for(self.key, self.kid)]}

    def count(self, suffix):
        return sum(1 for _, u, _, _ in self.calls if u.endswith(suffix))

    def fetch(self, method, url, *, data=None, headers=None):
        self.calls.append((method, url, data, headers))
        if url == ISSUER + "/.well-known/openid-configuration":
            return {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize",
                    "token_endpoint": ISSUER + "/token", "jwks_uri": ISSUER + "/jwks"}
        if url == ISSUER + "/jwks":
            return self.jwks()
        if url == ISSUER + "/token":
            return {"id_token": self.id_token, "access_token": "unused", "token_type": "Bearer"}
        raise AssertionError(url)

    def sign(self, nonce, *, key=None, kid=None, **over):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123", "iat": now, "exp": now + 300,
                  "nonce": nonce, "email": "a@example.org", **over}
        return jwt.encode(claims, key or self.key, algorithm="RS256", headers={"kid": kid or self.kid})


@pytest.fixture()
def env(tmp_path, monkeypatch):
    idp = MockIdP()
    monkeypatch.setattr(oidc, "fetch", idp.fetch)
    monkeypatch.setattr(oidc, "JWKS_MIN_REFRESH_SECONDS", 0)
    oidc.clear_caches()
    for k, v in {
        "SILSILA_OIDC_FAMILY_ISSUER": ISSUER, "SILSILA_OIDC_FAMILY_CLIENT_ID": CLIENT_ID,
        "SILSILA_OIDC_FAMILY_CLIENT_SECRET": "super-secret-value", "SILSILA_OIDC_FAMILY_ROLE": "family",
        "SILSILA_OIDC_FAMILY_REDIRECT_URI": REDIRECT,
        "SILSILA_OIDC_STAFF_ISSUER": ISSUER, "SILSILA_OIDC_STAFF_CLIENT_ID": CLIENT_ID,
        "SILSILA_OIDC_STAFF_ROLE": "counsellor",
        "SILSILA_OIDC_STAFF_REDIRECT_URI": "http://localhost:8000/api/auth/oidc/staff/callback",
        "SILSILA_OIDC_POST_LOGIN_URL": POST_LOGIN,
        "SILSILA_OIDC_STAFF_ALLOWLIST": "dr@clinic.example",
    }.items():
        monkeypatch.setenv(k, v)
    store = Store(tmp_path / "oidc.db")
    app = FastAPI()
    app.include_router(oidc.router)
    app.dependency_overrides[oidc.get_store] = lambda: store
    client = TestClient(app, follow_redirects=False)
    yield client, idp, store
    oidc.clear_caches()


def begin(client, provider="family"):
    r = client.get(f"/api/auth/oidc/{provider}/start")
    assert r.status_code == 302
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(r.headers["location"]).query))
    return r, q


def finish(client, idp, q, provider="family", *, id_token=None, state=None, **claims):
    idp.id_token = id_token or idp.sign(q["nonce"], **claims)
    return client.get(f"/api/auth/oidc/{provider}/callback", params={"code": "abc", "state": state or q["state"]})


def test_start_redirect_has_pkce_state_nonce(env):
    client, idp, _ = env
    r, q = begin(client)
    loc = urllib.parse.urlsplit(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == ISSUER + "/authorize"
    assert q["response_type"] == "code" and q["client_id"] == CLIENT_ID and q["redirect_uri"] == REDIRECT
    assert q["scope"] == "openid profile email"
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
    assert q["state"] and q["nonce"] and q["state"] != q["nonce"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" not in cookie  # localhost redirect


def test_cookie_secure_for_non_local_redirect(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setenv("SILSILA_OIDC_FAMILY_REDIRECT_URI", "https://app.example.ae/api/auth/oidc/family/callback")
    assert "secure" in client.get("/api/auth/oidc/family/start").headers["set-cookie"].lower()


def test_happy_path_family(env):
    client, idp, store = env
    _, q = begin(client)
    r = finish(client, idp, q)
    assert r.status_code == 302
    base, frag = r.headers["location"].split("#")
    assert base == POST_LOGIN and frag.startswith("token=")
    claims = auth.decode(frag[len("token="):])
    assert claims["role"] == "family"
    user = store.get("user", claims["sub"])
    assert user["oidc_sub"] == f"{ISSUER}|user-123" and user["lang"] == "en"
    # PKCE verifier and client secret reached the token endpoint; challenge matches the verifier
    _, _, form, headers = next(c for c in idp.calls if c[1].endswith("/token"))
    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == q["code_challenge"]
    assert headers["Authorization"].startswith("Basic ")
    ev = store.audit_events()[-1]
    assert ev["action"] == "auth.oidc_login" and ev["outcome"] == "success"
    assert "token" not in str(ev["detail"]) and "user-123" not in str(ev["detail"])
    # second login reuses the same user
    _, q2 = begin(client)
    r2 = finish(client, idp, q2)
    assert auth.decode(r2.headers["location"].split("token=")[1])["sub"] == claims["sub"]
    assert len(store.find("user", oidc_sub=f"{ISSUER}|user-123")) == 1


def test_counsellor_not_in_allowlist_is_403(env):
    client, idp, store = env
    _, q = begin(client, "staff")
    r = finish(client, idp, q, "staff", email="other@clinic.example")
    assert r.status_code == 403
    assert store.find("user", oidc_sub=f"{ISSUER}|user-123") == []
    ev = store.audit_events()[-1]
    assert ev["outcome"] == "denied" and "not_allowlisted" in str(ev["detail"]) and "other@clinic" not in str(ev["detail"])


def test_counsellor_in_allowlist(env):
    client, idp, _ = env
    _, q = begin(client, "staff")
    r = finish(client, idp, q, "staff", email="Dr@Clinic.example")
    assert r.status_code == 302
    assert auth.decode(r.headers["location"].split("token=")[1])["role"] == "counsellor"


def test_counsellor_removed_from_allowlist_is_blocked(env, monkeypatch):
    client, idp, _ = env
    _, q = begin(client, "staff")
    assert finish(client, idp, q, "staff", email="dr@clinic.example").status_code == 302
    monkeypatch.setenv("SILSILA_OIDC_STAFF_ALLOWLIST", "someone@else.example")
    _, q = begin(client, "staff")
    assert finish(client, idp, q, "staff", email="dr@clinic.example").status_code == 403


def test_family_sub_cannot_become_counsellor(env):
    client, idp, store = env
    store.put("user", {"id": "u1", "role": "family", "oidc_sub": f"{ISSUER}|user-123"})
    _, q = begin(client, "staff")
    assert finish(client, idp, q, "staff", email="dr@clinic.example").status_code == 403


@pytest.mark.parametrize("bad", ["nonce", "aud", "iss", "expired"])
def test_bad_claims_rejected(env, bad):
    client, idp, store = env
    _, q = begin(client)
    over = {"nonce": {}, "aud": {"aud": "someone-else"}, "iss": {"iss": "https://evil.test"},
            "expired": {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}}[bad]
    tok = idp.sign("wrong-nonce", **over) if bad == "nonce" else idp.sign(q["nonce"], **over)
    r = finish(client, idp, q, id_token=tok)
    assert r.status_code == 400 and "location" not in r.headers
    assert store.find("user") == []
    assert store.audit_events()[-1]["outcome"] == "denied"


def test_bad_signature_rejected(env):
    client, idp, store = env
    _, q = begin(client)
    r = finish(client, idp, q, id_token=idp.sign(q["nonce"], key=new_key()))
    assert r.status_code == 400 and store.find("user") == []


def test_hs256_id_token_rejected(env):
    client, idp, _ = env
    _, q = begin(client)
    now = int(time.time())
    tok = jwt.encode({"iss": ISSUER, "aud": CLIENT_ID, "sub": "x", "iat": now, "exp": now + 60, "nonce": q["nonce"]},
                     "k" * 40, algorithm="HS256", headers={"kid": "k1"})
    assert finish(client, idp, q, id_token=tok).status_code == 400


def test_state_mismatch_and_tampered_cookie(env):
    client, idp, _ = env
    _, q = begin(client)
    assert finish(client, idp, q, state="not-the-state").status_code == 400
    _, q = begin(client)
    cookie = client.cookies.get("silsila_oidc_family")
    client.cookies.clear()
    client.cookies.set("silsila_oidc_family", cookie[:-3] + ("AAA" if not cookie.endswith("AAA") else "BBB"),
                       path="/api/auth/oidc")
    assert finish(client, idp, q).status_code == 400
    client.cookies.clear()
    assert finish(client, idp, q).status_code == 400  # no cookie at all


def test_state_cookie_from_other_provider_rejected(env):
    client, idp, _ = env
    _, q = begin(client, "staff")
    client.cookies.set("silsila_oidc_family", client.cookies.get("silsila_oidc_staff"), path="/api/auth/oidc")
    assert finish(client, idp, q, "family").status_code == 400


def test_idp_error_param_is_generic(env):
    client, _, store = env
    begin(client)
    r = client.get("/api/auth/oidc/family/callback", params={"error": "access_denied", "error_description": "secret detail"})
    assert r.status_code == 400 and "secret detail" not in r.text
    assert "secret detail" not in str(store.audit_events()[-1]["detail"])


def test_unknown_kid_triggers_one_jwks_refresh(env):
    client, idp, _ = env
    _, q = begin(client)
    assert finish(client, idp, q).status_code == 302
    assert idp.count("/jwks") == 1
    idp.key, idp.kid = new_key(), "k2"  # IdP rotates its key
    _, q = begin(client)
    assert finish(client, idp, q).status_code == 302
    assert idp.count("/jwks") == 2
    # a kid the IdP never publishes: exactly one more refresh, then rejected
    _, q = begin(client)
    r = finish(client, idp, q, id_token=idp.sign(q["nonce"], kid="ghost"))
    assert r.status_code == 400 and idp.count("/jwks") == 3


def test_unknown_kid_refresh_is_rate_limited(env, monkeypatch):
    client, idp, _ = env
    _, q = begin(client)
    finish(client, idp, q)
    monkeypatch.setattr(oidc, "JWKS_MIN_REFRESH_SECONDS", 3600)
    _, q = begin(client)
    r = finish(client, idp, q, id_token=idp.sign(q["nonce"], kid="ghost"))
    assert r.status_code == 400 and idp.count("/jwks") == 1


def test_providers_lists_no_secrets(env):
    client, _, _ = env
    r = client.get("/api/auth/oidc/providers")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert ids == {"family", "staff"}
    assert "super-secret-value" not in r.text and CLIENT_ID not in r.text and "secret" not in r.text.lower()


def test_inert_when_unconfigured(tmp_path, monkeypatch):
    import os
    for k in [k for k in os.environ if k.startswith("SILSILA_OIDC_")]:
        monkeypatch.delenv(k)
    app = FastAPI()
    app.include_router(oidc.router)
    app.dependency_overrides[oidc.get_store] = lambda: Store(tmp_path / "x.db")
    c = TestClient(app, follow_redirects=False)
    assert c.get("/api/auth/oidc/providers").json() == []
    assert c.get("/api/auth/oidc/family/start").status_code == 404
    assert c.get("/api/auth/oidc/family/callback").status_code == 404


def test_incomplete_or_insecure_provider_not_listed(env, monkeypatch):
    client, _, _ = env
    monkeypatch.setenv("SILSILA_OIDC_FAMILY_ISSUER", "http://idp.test")  # plain http, not localhost
    monkeypatch.delenv("SILSILA_OIDC_STAFF_CLIENT_ID")
    assert client.get("/api/auth/oidc/providers").json() == []
