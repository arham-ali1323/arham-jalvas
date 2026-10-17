"""Credentials for the browser's live-voice WebSocket.

THE PROBLEM
    The WebSocket API in browsers cannot set an `Authorization` header, and a
    permanent Gemini key must never reach the browser (see the brief). Putting
    the long-lived access token in the query string would leak it into proxy,
    gateway and server access logs.

THE EXCHANGE
    1. The authenticated web client POSTs `/live/ticket` over normal HTTPS
       (bearer header still available there).
    2. The server returns a random, single-use ticket valid for
       `live_ticket_ttl_seconds`.
    3. The client opens `WS /live/session?ticket=...`. The ticket is consumed on
       the first connection; a replay is refused.

    A ticket in a log is therefore worthless within seconds and cannot be used
    twice. This is the "prefer short-lived credentials" requirement applied to a
    transport that supports nothing better.

SCOPE / LIMITATION
    The store is in-process. On a multi-worker deployment a ticket issued by one
    worker is not visible to another, so the exchange is only guaranteed correct
    with a single worker (or sticky routing). This is stated plainly rather than
    pretended away; swapping the dict for Redis behind these two methods fixes
    it without touching callers.
"""
from __future__ import annotations

import secrets
import threading
import time

from app.config import get_settings


class TicketStore:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = float(ttl_seconds)
        self._lock = threading.Lock()
        self._tickets: dict[str, tuple[str, float]] = {}  # token -> (user_id, expiry)

    def issue(self, user_id: str) -> tuple[str, float]:
        """Return `(token, expires_in_seconds)`. The token is never stored in
        plaintext outside this process and never logged."""
        token = secrets.token_urlsafe(32)
        expiry = time.monotonic() + self._ttl
        with self._lock:
            self._prune_locked()
            self._tickets[token] = (user_id, expiry)
        return token, self._ttl

    def consume(self, token: str) -> str | None:
        """Validate and burn a ticket. Returns the user id, or None if the token
        is unknown, already used, or expired."""
        if not token:
            return None
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            entry = self._tickets.pop(token, None)
        if entry is None:
            return None
        user_id, expiry = entry
        if expiry < now:
            return None
        return user_id

    def _prune_locked(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        expired = [tok for tok, (_, exp) in self._tickets.items() if exp < now]
        for tok in expired:
            self._tickets.pop(tok, None)


class SessionRegistry:
    """Counts live sessions per user so one account cannot open unbounded
    concurrent Gemini Live sessions (each draws on the shared quota)."""

    def __init__(self, max_per_user: int) -> None:
        self._max = max(1, int(max_per_user))
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}

    def acquire(self, user_id: str) -> bool:
        with self._lock:
            if self._active.get(user_id, 0) >= self._max:
                return False
            self._active[user_id] = self._active.get(user_id, 0) + 1
            return True

    def release(self, user_id: str) -> None:
        with self._lock:
            n = self._active.get(user_id, 0) - 1
            if n <= 0:
                self._active.pop(user_id, None)
            else:
                self._active[user_id] = n


_settings = get_settings()
tickets = TicketStore(_settings.live_ticket_ttl_seconds)
sessions = SessionRegistry(_settings.live_max_concurrent_sessions)
