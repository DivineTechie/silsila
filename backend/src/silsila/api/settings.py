"""Deployment settings, read from the environment. `check_production()` refuses to start an unsafe production."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger("silsila.settings")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    demo: bool
    secret: str
    cors: str
    database_url: str
    demo_family_password: str
    demo_counsellor_password: str
    max_body_bytes: int
    login_per_min: int
    invite_per_min: int

    @property
    def production(self) -> bool:
        return not self.demo

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in (self.cors or "*").split(",") if o.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def load() -> Settings:
    env = os.environ.get
    return Settings(
        demo=env("SILSILA_DEMO", "1") == "1",
        secret=env("SILSILA_SECRET", ""),
        cors=env("SILSILA_CORS", ""),
        database_url=env("SILSILA_DATABASE_URL", ""),
        demo_family_password=env("SILSILA_DEMO_FAMILY_PASSWORD", ""),
        demo_counsellor_password=env("SILSILA_DEMO_COUNSELLOR_PASSWORD", ""),
        # The FHIR import cap is 1 MB for the bundle itself; the request wraps it in a small JSON object.
        max_body_bytes=_int("SILSILA_MAX_BODY_BYTES", 2_000_000),
        login_per_min=_int("SILSILA_LOGIN_PER_MIN", 10),
        # A relative's page makes a few calls per step, and in demo mode many visitors may share one network
        # address (a judging room), so the demo allows more.
        invite_per_min=_int("SILSILA_INVITE_PER_MIN", 30 if env("SILSILA_DEMO", "1") == "0" else 240),
    )


def problems(s: Settings) -> list[str]:
    out = []
    if len(s.secret) < 32:
        out.append("SILSILA_SECRET must be set to a random value of at least 32 characters")
    if not s.cors or "*" in s.cors_origins:
        out.append("SILSILA_CORS must list the web app origin(s) explicitly (not empty, not '*')")
    if not s.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        out.append("SILSILA_DATABASE_URL must be a postgres URL (postgresql://...)")
    for name, val in (("SILSILA_DEMO_FAMILY_PASSWORD", s.demo_family_password),
                      ("SILSILA_DEMO_COUNSELLOR_PASSWORD", s.demo_counsellor_password)):
        if val:
            out.append(f"{name} must not be set in production (demo accounts must not exist)")
    return out


def check_production(s: Settings | None = None) -> None:
    """Production (SILSILA_DEMO=0): raise listing every problem. Demo: only log warnings."""
    s = s or load()
    found = problems(s)
    if s.production:
        if found:
            raise ConfigError("Refusing to start in production mode (SILSILA_DEMO=0):\n  - " + "\n  - ".join(found))
    elif found:
        log.warning("Demo mode (SILSILA_DEMO=1). Not acceptable in production: %s", "; ".join(found))
