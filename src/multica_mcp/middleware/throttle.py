"""IP-based login throttle for API key authentication.

Mirrors the Go version's ``internal/middleware/throttle.go``.

After *max_failures* failed auth attempts from the same IP within *window*,
the IP is banned for *ban_duration*.

This is implemented as an ASGI-compatible middleware that can wrap a
Starlette app or any ASGI application.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class LoginThrottle:
    """IP-based login throttle for Bearer API key authentication.

    Args:
        max_failures: Number of failed attempts before banning.
        window: Time window in seconds for counting failures.
        ban_duration: Ban duration in seconds after exceeding max failures.
    """

    def __init__(
        self,
        max_failures: int = 5,
        window: float = 60.0,
        ban_duration: float = 900.0,
    ) -> None:
        self._max_failures = max_failures
        self._window = window
        self._ban_duration = ban_duration
        self._clean_every: float = 300.0  # 5 minutes
        self._last_clean: float = time.time()
        self._entries: dict[str, _Entry] = {}
        self._lock: object | None = None  # threading lock imported lazily

    # ---- public API ----

    def is_blocked(self, ip: str) -> bool:
        """Check if an IP is currently banned."""
        entry = self._entries.get(ip)
        if entry is None:
            return False

        now = time.time()
        if entry.blocked:
            if now - entry.last_seen > self._ban_duration:
                # Ban expired — remove entry
                self._entries.pop(ip, None)
                return False
            return True
        return False

    def record_failure(self, ip: str) -> None:
        """Record a failed authentication attempt from *ip*."""
        self._maybe_clean()

        now = time.time()
        entry = self._entries.get(ip)
        if entry is None:
            entry = _Entry()
            self._entries[ip] = entry

        if now - entry.last_seen > self._window:
            entry.count = 0

        entry.count += 1
        entry.last_seen = now

        if entry.count >= self._max_failures:
            entry.blocked = True
            logger.warning(
                "IP blocked by login throttle",
                extra={
                    "ip": ip,
                    "failures": entry.count,
                    "ban_duration": self._ban_duration,
                },
            )

    def record_success(self, ip: str) -> None:
        """Clear throttle state for *ip* after a successful auth."""
        self._entries.pop(ip, None)

    # ---- ASGI middleware ----

    def wrap_app(self, api_key: str, app):
        """Return an ASGI middleware that validates API key and applies throttling.

        Args:
            api_key: The expected Bearer token value.
            app: The inner ASGI app.
        """

        async def asgi_app(scope, receive, send):
            if scope["type"] != "http":
                await app(scope, receive, send)
                return

            ip = _client_ip_from_scope(scope)

            if self.is_blocked(ip):
                logger.warning("request blocked by login throttle", extra={"ip": ip})
                await _send_json_response(send, 429, {"error": "too many auth failures; try again later"})
                return

            # Extract Authorization header
            auth = ""
            for key, value in scope.get("headers", []):
                if key.lower() == b"authorization":
                    auth = value.decode("utf-8", errors="replace")
                    break

            if not auth:
                self.record_failure(ip)
                await _send_json_response(send, 401, {"error": "unauthorized: missing Authorization header"})
                return

            token = auth
            if auth.startswith("Bearer "):
                token = auth[7:]

            if token != api_key:
                self.record_failure(ip)
                logger.warning("invalid API key attempt", extra={"ip": ip})
                await _send_json_response(send, 401, {"error": "unauthorized: invalid API key"})
                return

            self.record_success(ip)
            await app(scope, receive, send)

        return asgi_app

    # ---- internal ----

    def _maybe_clean(self) -> None:
        now = time.time()
        if now - self._last_clean < self._clean_every:
            return
        self._last_clean = now
        # Remove entries that have aged past both ban and window
        max_age = max(self._ban_duration, self._window)
        expired = [
            ip for ip, entry in self._entries.items()
            if now - entry.last_seen > max_age
        ]
        for ip in expired:
            self._entries.pop(ip, None)


class _Entry:
    __slots__ = ("count", "blocked", "last_seen")

    def __init__(self) -> None:
        self.count: int = 0
        self.blocked: bool = False
        self.last_seen: float = 0.0


# ---- helpers ----


def _client_ip_from_scope(scope: dict[str, Any]) -> str:
    """Extract client IP from ASGI scope, respecting X-Forwarded-For / X-Real-IP."""
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

    # X-Forwarded-For: client, proxy1, proxy2
    for key, value in headers:
        if key.lower() == b"x-forwarded-for":
            val = value.decode("utf-8", errors="replace")
            first = val.split(",")[0].strip()
            if first:
                return first

    # X-Real-IP
    for key, value in headers:
        if key.lower() == b"x-real-ip":
            val = value.decode("utf-8", errors="replace").strip()
            if val:
                return val

    # Direct connection
    client: tuple[str, int] | None = scope.get("client")
    if client:
        return client[0]

    return "unknown"


async def _send_json_response(send, status: int, body: dict) -> None:
    import json

    body_bytes = json.dumps(body).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body_bytes)).encode()),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": body_bytes,
    })
