"""Demo authentication: password hashes (scrypt) and short-lived signed tokens.

Roles: 'family' (the index person or their parent), 'counsellor' (genetic
counselling team). Relatives use unguessable invitation links and never log in.
In production identity would come from UAE PASS; see docs/deployment.md.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import secrets
from typing import Any

import jwt

SECRET = os.environ.get("SILSILA_SECRET") or secrets.token_hex(32)
TOKEN_HOURS = 8


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
    return jwt.encode({"sub": user["id"], "role": user["role"], "exp": exp}, SECRET, algorithm="HS256")


def decode(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET, algorithms=["HS256"])
