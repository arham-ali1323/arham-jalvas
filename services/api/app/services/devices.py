"""Pairing and command relay for desktop companions.

Two pieces live here:

1. `PairingStore` — the short-lived handshake that turns "a desktop app is
   showing a code" into "a device is authorised on an account". A code is
   displayed on the desktop, typed into the signed-in web app, and the desktop
   then receives a long-lived device token. The token is stored **hashed** in the
   database; the plaintext is shown exactly once, to the desktop.

2. `DeviceHub` — the in-process registry of live companion WebSockets, keyed by
   device id. Web commands are pushed through here; results come back on the
   same socket.

Both stores are in-process. On a multi-worker deployment a pairing started on
one worker is not visible to another, and a command can only reach a socket
held by the worker that receives the HTTP request. That is stated plainly
rather than hidden — a single worker (or sticky routing) is correct, and Redis
behind these same methods is the fix. The durable state (devices, permissions,
action history) is all in the database and is unaffected.
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import string
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# A pairing code is read off one screen and typed into another, so it uses an
# unambiguous alphabet (no 0/O, 1/I/L) and is case-insensitive on entry.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6
_CODE_TTL_SECONDS = 300.0  # 5 minutes
_POLL_TOKEN_BYTES = 24


def generate_device_token() -> str:
    """A fresh, high-entropy device credential (the companion keeps this)."""
    return secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    """One-way hash stored in the database. The plaintext token is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


@dataclass
class PairingSession:
    id: str
    code: str
    poll_token: str
    name: str
    platform: str
    fingerprint: str
    expires_at: float
    # pending -> approved | denied | expired
    status: str = "pending"
    device_id: str | None = None
    device_token: str | None = None

    def public_status(self) -> dict[str, Any]:
        """What the polling desktop sees. The device token is included only once
        the pairing is approved, and only to the holder of the poll token."""
        out: dict[str, Any] = {"status": self.status}
        if self.status == "approved":
            out["device_id"] = self.device_id
            out["device_token"] = self.device_token
        return out


class PairingStore:
    def __init__(self, ttl_seconds: float = _CODE_TTL_SECONDS) -> None:
        self._ttl = float(ttl_seconds)
        self._lock = threading.Lock()
        self._sessions: dict[str, PairingSession] = {}

    def _prune_locked(self, now: float) -> None:
        for pid, s in list(self._sessions.items()):
            if s.expires_at < now and s.status == "pending":
                s.status = "expired"
            if s.expires_at + 300 < now:  # keep resolved sessions briefly
                self._sessions.pop(pid, None)

    def start(self, name: str, platform: str, fingerprint: str) -> PairingSession:
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            # Codes are short; make sure the live one is unique.
            live_codes = {s.code for s in self._sessions.values()}
            code = _new_code()
            while code in live_codes:
                code = _new_code()
            session = PairingSession(
                id=secrets.token_urlsafe(12),
                code=code,
                poll_token=secrets.token_urlsafe(_POLL_TOKEN_BYTES),
                name=(name or "MARK LIV Desktop")[:120],
                platform=(platform or "")[:40],
                fingerprint=(fingerprint or "")[:128],
                expires_at=now + self._ttl,
            )
            self._sessions[session.id] = session
            return session

    def get(self, pairing_id: str, poll_token: str) -> PairingSession | None:
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            s = self._sessions.get(pairing_id)
            if s is None or not secrets.compare_digest(s.poll_token, poll_token):
                return None
            if s.status == "pending" and s.expires_at < now:
                s.status = "expired"
            return s

    def find_by_code(self, code: str) -> PairingSession | None:
        wanted = (code or "").strip().upper()
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            for s in self._sessions.values():
                if s.status == "pending" and s.expires_at >= now and s.code == wanted:
                    return s
            return None

    def approve(self, session: PairingSession, device_id: str, device_token: str) -> None:
        with self._lock:
            session.status = "approved"
            session.device_id = device_id
            session.device_token = device_token

    def deny(self, session: PairingSession) -> None:
        with self._lock:
            session.status = "denied"


class DeviceHub:
    """Live companion sockets, keyed by device id.

    Only the worker that accepted a socket holds it; that is the documented
    single-worker boundary. Methods are async because they touch WebSockets.
    """

    def __init__(self) -> None:
        self._sockets: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def register(self, device_id: str, socket: Any) -> None:
        async with self._lock:
            self._sockets[device_id] = socket

    async def unregister(self, device_id: str, socket: Any) -> None:
        async with self._lock:
            # Only drop the entry if it is still this socket — a reconnect may
            # have already replaced it.
            if self._sockets.get(device_id) is socket:
                self._sockets.pop(device_id, None)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._sockets

    def online_ids(self) -> set[str]:
        return set(self._sockets)

    async def disconnect(self, device_id: str) -> None:
        """Forget and close a device's socket (used when it is revoked)."""
        async with self._lock:
            socket = self._sockets.pop(device_id, None)
        if socket is not None:
            try:
                await socket.close(code=4403)
            except Exception:  # noqa: BLE001 - already gone
                pass

    async def send(self, device_id: str, payload: dict[str, Any]) -> bool:
        """Push a frame to a device. Returns False if it is not connected or the
        send fails (the caller treats that as "device offline")."""
        async with self._lock:
            socket = self._sockets.get(device_id)
        if socket is None:
            return False
        try:
            await socket.send_json(payload)
            return True
        except Exception:  # noqa: BLE001 - a broken socket means offline
            async with self._lock:
                if self._sockets.get(device_id) is socket:
                    self._sockets.pop(device_id, None)
            return False


pairings = PairingStore()
hub = DeviceHub()
