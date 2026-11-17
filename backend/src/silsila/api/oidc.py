"""Generic OpenID Connect login (authorization code flow with PKCE).

Point it at UAE PASS (families) or Microsoft Entra ID (counsellors) with
environment variables only; see docs/identity-oidc.md. At the end of a
successful login it issues the same Silsila token as the demo password login.

Inert unless at least one provider is configured: with nothing set, the
provider list is empty and every other endpoint answers 404.

Login state lives in a short-lived signed cookie, not in server memory, so it
works across replicas. No tokens or personal data are written to logs or to
the audit trail; failures are recorded as an error code only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import auth
from .store import Store, new_id

router = APIRouter(prefix="/api/auth/oidc", tags=["oidc"])

STATE_TTL_SECONDS = 600
ALLOWED_ALGS = ["RS256", "ES256"]
CLOCK_LEEWAY = 60
JWKS_MIN_REFRESH_SECONDS = 10  # a bad kid cannot make us hammer the IdP
HTTP_TIMEOUT = 10
_ENV_ISSUER = re.compile(r"^SILSILA_OIDC_([A-Z0-9]+)_ISSUER$")


class OidcError(Exception):
    """Internal failure carrying a short error code (safe for the audit trail)."""

    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


# ------------------------------------------------------------------ http --
def _urllib_fetch(method: str, url: str, *, data: dict[str, str] | None = None,
                  headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Fetch a URL and parse JSON. Replaced in tests; stdlib only, so httpx can stay a dev dependency."""
    if urllib.parse.urlsplit(url).scheme not in ("https", "http"):
        raise OidcError("bad_url")
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 (scheme checked above)
            return json.loads(resp.read(2_000_000))
    except urllib.error.HTTPError as exc:
        raise OidcError(f"http_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        raise OidcError("http_error") from None


# Looked up at call time so tests can replace it: oidc.fetch = fake
fetch: Callable[..., dict[str, Any]] = _urllib_fetch


# ---------------------------------------------------------------- config --
@dataclass(frozen=True)
class Provider:
    id: str
    issuer: str
    client_id: str
    client_secret: str | None
    scopes: str
    role: str
    redirect_uri: str
    token_auth: str  # "basic" or "post"


def _env(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None


def providers() -> dict[str, Provider]:
    """Providers that are fully configured, read from the environment on each call."""
    out: dict[str, Provider] = {}
    for key in list(os.environ):
        m = _ENV_ISSUER.match(key)
        if not m:
            continue
        pid = m.group(1)
        pre = f"SILSILA_OIDC_{pid}_"
        issuer, client_id = _env(pre + "ISSUER"), _env(pre + "CLIENT_ID")
        role, redirect = _env(pre + "ROLE"), _env(pre + "REDIRECT_URI")
        if not (issuer and client_id and redirect and role in ("family", "counsellor")):
            continue
        host = urllib.parse.urlsplit(issuer)
        if host.scheme != "https" and host.hostname not in ("localhost", "127.0.0.1"):
            continue  # never talk to an identity provider over plain http
        out[pid.lower()] = Provider(
            id=pid.lower(), issuer=issuer.rstrip("/"), client_id=client_id,
            client_secret=_env(pre + "CLIENT_SECRET"),
            scopes=_env(pre + "SCOPES") or "openid profile email",
            role=role, redirect_uri=redirect,
            token_auth="post" if (_env(pre + "TOKEN_AUTH") or "basic").lower() == "post" else "basic")
    return out


def _provider(pid: str) -> Provider:
    p = providers().get(pid.lower())
    if p is None:
        raise HTTPException(404, "Not found")
    return p


# ------------------------------------------------------- discovery / jwks --
_discovery: dict[str, dict[str, Any]] = {}
_jwks: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_caches() -> None:
    _discovery.clear()
    _jwks.clear()


def discover(p: Provider) -> dict[str, Any]:
    doc = _discovery.get(p.issuer)
    if doc is None:
        doc = fetch("GET", p.issuer + "/.well-known/openid-configuration")
        if str(doc.get("issuer", "")).rstrip("/") != p.issuer:
            raise OidcError("discovery_issuer_mismatch")
        for k in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not doc.get(k):
                raise OidcError("discovery_incomplete")
        _discovery[p.issuer] = doc
    return doc


def _load_jwks(p: Provider, force: bool = False) -> dict[str, Any]:
    cached = _jwks.get(p.issuer)
    if cached and not force:
        return cached[1]
    keys = fetch("GET", discover(p)["jwks_uri"])
    if not isinstance(keys.get("keys"), list):
        raise OidcError("jwks_invalid")
    _jwks[p.issuer] = (time.monotonic(), keys)
    return keys


def _signing_key(p: Provider, kid: str | None) -> Any:
    def find(jwks: dict[str, Any]) -> dict[str, Any] | None:
        keys = [k for k in jwks["keys"] if k.get("use", "sig") == "sig"]
        for k in keys:
            if k.get("kid") == kid:
                return k
        return keys[0] if kid is None and len(keys) == 1 else None

    jwk = find(_load_jwks(p))
    if jwk is None:  # unknown kid: the IdP may have rotated keys; refresh once
        if time.monotonic() - _jwks[p.issuer][0] >= JWKS_MIN_REFRESH_SECONDS:
            jwk = find(_load_jwks(p, force=True))
    if jwk is None:
        raise OidcError("unknown_kid")
    try:
        return jwt.PyJWK(jwk).key
    except Exception:  # noqa: BLE001 - any malformed key is just a failure
        raise OidcError("bad_jwk") from None


def verify_id_token(p: Provider, id_token: str, nonce: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise OidcError("id_token_malformed") from None
    if header.get("alg") not in ALLOWED_ALGS:
        raise OidcError("id_token_alg")
    key = _signing_key(p, header.get("kid"))
    try:
        claims = jwt.decode(
            id_token, key, algorithms=ALLOWED_ALGS, audience=p.client_id, issuer=p.issuer,
            leeway=CLOCK_LEEWAY, options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.ExpiredSignatureError:
        raise OidcError("id_token_expired") from None
    except jwt.InvalidAudienceError:
        raise OidcError("id_token_aud") from None
    except jwt.InvalidIssuerError:
        raise OidcError("id_token_iss") from None
    except jwt.PyJWTError:
        raise OidcError("id_token_invalid") from None
    aud = claims["aud"]
    if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != p.client_id:
        raise OidcError("id_token_azp")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise OidcError("id_token_nonce")
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise OidcError("id_token_sub")
    return claims


# ------------------------------------------------------- state cookie ----
def _key(purpose: str) -> bytes:
    return hmac.new(auth._secret().encode(), b"silsila-oidc|" + purpose.encode(), hashlib.sha256).digest()


def _verifier(rand: str) -> str:
    """PKCE verifier derived from the server secret, so the cookie never carries it."""
    return base64.urlsafe_b64encode(hmac.new(_key("pkce"), rand.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _cookie_name(pid: str) -> str:
    return f"silsila_oidc_{pid}"


def _seal_state(pid: str, state: str, nonce: str, rand: str) -> str:
    now = int(time.time())
    return jwt.encode({"typ": "oidc_state", "p": pid, "s": state, "n": nonce, "r": rand,
                       "iat": now, "exp": now + STATE_TTL_SECONDS}, _key("state"), algorithm="HS256")


def _open_state(pid: str, cookie: str | None) -> dict[str, Any]:
    if not cookie:
        raise OidcError("state_missing")
    try:
        data = jwt.decode(cookie, _key("state"), algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError:
        raise OidcError("state_invalid") from None
    if data.get("typ") != "oidc_state" or data.get("p") != pid:
        raise OidcError("state_invalid")
    return data


def _is_local(uri: str) -> bool:
    return urllib.parse.urlsplit(uri).hostname in ("localhost", "127.0.0.1", "::1")


# ----------------------------------------------------------------- store --
def get_store() -> Store:
    """FastAPI dependency. Defaults to app.py's store(); override via app.dependency_overrides."""
    from . import app as app_mod  # late import: app.py includes this router
    return app_mod.store()


# ------------------------------------------------------------- endpoints --
@router.get("/providers")
def list_providers() -> list[dict[str, str]]:
    return [{"id": p.id, "role": p.role, "start": f"/api/auth/oidc/{p.id}/start"} for p in providers().values()]


@router.get("/{provider}/start")
def start(provider: str) -> RedirectResponse:
    p = _provider(provider)
    try:
        authz = discover(p)["authorization_endpoint"]
    except OidcError:
        raise HTTPException(502, "Sign-in is not available right now") from None
    state, nonce, rand = (secrets.token_urlsafe(32) for _ in range(3))
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": p.client_id, "redirect_uri": p.redirect_uri,
        "scope": p.scopes, "state": state, "nonce": nonce,
        "code_challenge": _challenge(_verifier(rand)), "code_challenge_method": "S256"})
    sep = "&" if "?" in authz else "?"
    resp = RedirectResponse(f"{authz}{sep}{q}", status_code=302)
    resp.set_cookie(_cookie_name(p.id), _seal_state(p.id, state, nonce, rand), max_age=STATE_TTL_SECONDS,
                    path="/api/auth/oidc", httponly=True, secure=not _is_local(p.redirect_uri), samesite="lax")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _exchange_code(p: Provider, code: str, verifier: str) -> dict[str, Any]:
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": p.redirect_uri,
            "code_verifier": verifier}
    headers: dict[str, str] = {"Accept": "application/json"}
    if p.client_secret and p.token_auth == "basic":
        cred = f"{urllib.parse.quote(p.client_id, safe='')}:{urllib.parse.quote(p.client_secret, safe='')}"
        headers["Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
    else:
        form["client_id"] = p.client_id
        if p.client_secret:
            form["client_secret"] = p.client_secret
    return fetch("POST", discover(p)["token_endpoint"], data=form, headers=headers)


def _staff_allowlist() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("SILSILA_OIDC_STAFF_ALLOWLIST", "").split(",") if e.strip()}


def _claim_email(claims: dict[str, Any]) -> str | None:
    if claims.get("email_verified") is False:
        return None
    for k in ("email", "preferred_username", "upn"):
        v = claims.get(k)
        if isinstance(v, str) and "@" in v:
            return v.strip().lower()
    return None


def resolve_user(store: Store, p: Provider, claims: dict[str, Any]) -> dict[str, Any]:
    """Map verified claims to a Silsila user, creating a minimal family user on first login."""
    oidc_sub = f"{p.issuer}|{claims['sub']}"
    user = next(iter(store.find("user", oidc_sub=oidc_sub)), None)
    if user is not None and user.get("role") != p.role:
        raise OidcError("role_mismatch", 403)
    if p.role == "counsellor":
        email = _claim_email(claims)
        if email is None or email not in _staff_allowlist():  # checked on every login, so removal revokes access
            raise OidcError("not_allowlisted", 403)
        if user is None:
            user = store.put("user", {"id": new_id("user"), "role": "counsellor", "display_name": "Counsellor",
                                      "lang": "en", "oidc_sub": oidc_sub})
    elif user is None:
        user = store.put("user", {"id": new_id("user"), "role": "family", "display_name": "Family member",
                                  "lang": "en", "oidc_sub": oidc_sub})
    return user


def _clear_header(pid: str) -> str:
    return f"{_cookie_name(pid)}=; Max-Age=0; Path=/api/auth/oidc; HttpOnly; SameSite=lax"


@router.get("/{provider}/callback")
def callback(provider: str, request: Request, store: Store = Depends(get_store)) -> RedirectResponse:
    p = _provider(provider)
    try:
        saved = _open_state(p.id, request.cookies.get(_cookie_name(p.id)))
        qs = request.query_params
        if qs.get("error"):
            raise OidcError("idp_error")  # the IdP's own error text is not echoed anywhere
        if not hmac.compare_digest(qs.get("state", ""), saved["s"]):
            raise OidcError("state_mismatch")
        code = qs.get("code")
        if not code:
            raise OidcError("code_missing")
        tokens = _exchange_code(p, code, _verifier(saved["r"]))
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("id_token_missing")
        claims = verify_id_token(p, id_token, saved["n"])
        user = resolve_user(store, p, claims)
    except OidcError as exc:
        store.audit(f"oidc:{p.id}", "unknown", "auth.oidc_login", outcome="denied",
                    detail={"provider": p.id, "error": exc.code})
        forbidden = exc.status == 403
        raise HTTPException(403 if forbidden else 400,
                            "You are not authorised to sign in here" if forbidden else "Sign-in could not be completed",
                            headers={"Set-Cookie": _clear_header(p.id)}) from None
    store.audit(user["id"], user["role"], "auth.oidc_login", detail={"provider": p.id})
    post = _env("SILSILA_OIDC_POST_LOGIN_URL") or "/"
    resp = RedirectResponse(f"{post}#token={auth.issue(user)}", status_code=302)
    resp.delete_cookie(_cookie_name(p.id), path="/api/auth/oidc")
    resp.headers["Cache-Control"] = "no-store"
    return resp
