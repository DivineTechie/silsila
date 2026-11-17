"""Demo authentication: password hashes (scrypt) and short-lived signed tokens.

Roles: 'family' (the index person or their parent), 'counsellor' (genetic
counselling team). Relatives use unguessable invitation links and never log in.
In production identity would come from UAE PASS; see docs/deployment.md.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import os
import secrets
from typing import Any

import jwt

log = logging.getLogger("silsila.auth")
ISSUER = AUDIENCE = "silsila"
LEEWAY_SECONDS = 30
TOKEN_HOURS = 8


def _load_secret() -> str:
    secret = os.environ.get("SILSILA_SECRET", "")
    if secret:
        return secret
    if os.environ.get("SILSILA_DEMO", "1") != "1":
        raise RuntimeError("SILSILA_SECRET is required when SILSILA_DEMO=0")
    log.warning("SILSILA_SECRET is not set: using a random secret. Tokens will not survive a restart "
                "or work across replicas.")
    return secrets.token_hex(32)


_secret_cache: str | None = None


def _secret() -> str:
    """Resolved on first use so app start-up can report every configuration problem at once."""
    global _secret_cache
    if _secret_cache is None:
        _secret_cache = _load_secret()
    return _secret_cache


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt_hex, digest_hex = stored.split("$")
    test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(test.hex(), digest_hex)


def issue(user: dict[str, Any]) -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": user["id"], "role": user["role"], "exp": exp,
                        "iss": ISSUER, "aud": AUDIENCE}, _secret(), algorithm="HS256")


def decode(token: str) -> dict[str, Any]:
    return jwt.decode(token, _secret(), algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE,
                      leeway=LEEWAY_SECONDS, options={"require": ["exp", "sub", "iss", "aud"]})
