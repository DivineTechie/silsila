"""Request ID, redacted JSON access log, security headers, body-size limit and rate limiting (pure ASGI)."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import re
import time
import uuid
from collections import defaultdict, deque

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .settings import Settings

access_log = logging.getLogger("silsila.access")
# One JSON line per request on stdout, whatever the server's own logging set-up. uvicorn's access log is
# switched off in the container (--no-access-log) because it would print full paths, tokens included.
if not access_log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    access_log.addHandler(_h)
    access_log.setLevel(logging.INFO)
    access_log.propagate = False

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
# Relative invitation links carry a secret code in the path: /api/r/<code>/...
_TOKEN_PATH = re.compile(r"^(/api/r/)[^/]+")
_PRIVATE_PREFIXES = ("/api/auth", "/api/r/", "/api/demo")


def redact_path(path: str) -> str:
    return _TOKEN_PATH.sub(r"\1:token", path)[:200]


def _log_path(scope: Scope) -> str:
    """The route template when routing matched (never contains a value), else the redacted raw path."""
    route = scope.get("route")
    template = getattr(route, "path", None)
    if template:
        template = re.sub(r"\{(\w+)[^}]*\}", r":\1", template)
        return _TOKEN_PATH.sub(r"\1:token", template)
    return redact_path(scope.get("path", ""))


def _client_hash(scope: Scope) -> str:
    client = scope.get("client")
    return hashlib.sha256((client[0] if client else "unknown").encode()).hexdigest()[:10]


class _TooLarge(Exception):
    pass


class RateLimiter:
    """Sliding window, in memory. This is PER REPLICA: a pilot should put Azure Front Door / WAF rate
    limiting in front; this only stops casual password guessing and link enumeration."""

    def __init__(self) -> None:
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: float = 60.0) -> float:
        """0 if allowed (and counted), else seconds until the next slot."""
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            return window - (now - q[0])
        q.append(now)
        if len(self.hits) > 10_000:  # bound memory
            for k in [k for k, v in self.hits.items() if not v or now - v[-1] >= window]:
                del self.hits[k]
        return 0.0


class SilsilaMiddleware:
    def __init__(self, app: ASGIApp, cfg: Settings) -> None:
        self.app, self.cfg = app, cfg
        self.limiter = RateLimiter()

    def _limit_for(self, method: str, path: str) -> tuple[str, int] | None:
        if method == "POST" and path == "/api/auth/login":
            return "login", self.cfg.login_per_min
        if path.startswith("/api/r/"):
            return "invite", self.cfg.invite_per_min
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        headers = Headers(scope=scope)
        rid = headers.get("x-request-id", "")
        if not _REQUEST_ID.match(rid):
            rid = uuid.uuid4().hex
        method, path = scope["method"], scope["path"]
        needs_nostore = path.startswith("/api/") and (
            "authorization" in headers or path.startswith(_PRIVATE_PREFIXES))
        status = 0
        too_large = False
        too_large_body = json.dumps({"detail": "Request body too large"}).encode()

        async def send_wrapped(message: Message) -> None:
            nonlocal status
            if too_large:  # a streamed body went over the limit: whatever the app made of it, answer 413
                if message["type"] == "http.response.start":
                    message = {**message, "status": 413, "headers": [
                        (b"content-type", b"application/json"), (b"content-length", str(len(too_large_body)).encode())]}
                else:
                    message = {**message, "body": too_large_body}
            if message["type"] == "http.response.start":
                status = message["status"]
                out = [(k, v) for k, v in message["headers"] if k.lower() != b"x-request-id"]
                extra = {"x-request-id": rid, "x-content-type-options": "nosniff",
                         "x-frame-options": "DENY", "referrer-policy": "no-referrer"}
                if self.cfg.production:
                    extra["strict-transport-security"] = "max-age=31536000; includeSubDomains"
                present = {k.lower() for k, _ in out}
                if needs_nostore and b"cache-control" not in present:
                    extra["cache-control"] = "no-store"
                for k, v in extra.items():
                    if k.encode() not in present:
                        out.append((k.encode(), v.encode()))
                message = {**message, "headers": out}
            await send(message)

        async def reject(code: int, detail: str, extra: list[tuple[bytes, bytes]] | None = None) -> None:
            body = json.dumps({"detail": detail}).encode()
            await send_wrapped({"type": "http.response.start", "status": code, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                *(extra or [])]})
            await send_wrapped({"type": "http.response.body", "body": body})

        try:
            lim = self._limit_for(method, path)
            declared = headers.get("content-length", "")
            if declared.isdigit() and int(declared) > self.cfg.max_body_bytes:
                await reject(413, "Request body too large")
            elif lim and (wait := self.limiter.check(f"{lim[0]}:{_client_hash(scope)}", lim[1])):
                await reject(429, "Too many requests; try again shortly",
                             [(b"retry-after", str(int(wait) + 1).encode())])
            else:
                seen = 0

                async def limited_receive() -> Message:
                    nonlocal seen, too_large
                    msg = await receive()
                    if msg["type"] == "http.request":
                        seen += len(msg.get("body", b""))
                        if seen > self.cfg.max_body_bytes:
                            too_large = True
                            raise _TooLarge
                    return msg

                try:
                    await self.app(scope, limited_receive, send_wrapped)
                except _TooLarge:
                    if status == 0:
                        await reject(413, "Request body too large")
        finally:
            # Never logged: query strings, bodies, Authorization, full IP. Path is redacted.
            access_log.info(json.dumps({
                "method": method, "path": _log_path(scope), "status": status,
                "ms": round((time.perf_counter() - started) * 1000, 1), "request_id": rid,
                "client": _client_hash(scope)}))
