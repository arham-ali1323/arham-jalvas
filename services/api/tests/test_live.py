"""Tests for live voice: tickets, rate limiting, event translation and the
client<->model bridge. None of these touch the network, a microphone, or the
Gemini API — the provider is faked at the same seam production uses.
"""
from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.live import get_live_provider, _connect_limiter
from app.services import live_tickets
from app.services.live import LiveProvider, LiveSession, run_bridge, translate_response
from app.services.ratelimit import SlidingWindowLimiter

from tests.conftest import register


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeSocket:
    """Stands in for a Starlette WebSocket. Records everything the bridge sends
    and replays a scripted list of inbound frames."""

    def __init__(self, incoming: list[dict]) -> None:
        self._incoming = list(incoming)
        self.sent_json: list[dict] = []
        self.sent_bytes: list[bytes] = []

    async def receive(self) -> dict:
        if self._incoming:
            return self._incoming.pop(0)
        await asyncio.Event().wait()  # block until cancelled

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(data)

    async def send_json(self, data: dict) -> None:
        self.sent_json.append(data)


class FakeSession(LiveSession):
    def __init__(self, events: list[dict] | None = None, *, hold_open: bool = True) -> None:
        self._events = list(events or [])
        self._hold_open = hold_open
        self.audio: list[bytes] = []
        self.texts: list[str] = []
        self.activity: list[str] = []
        self.closed = False

    async def send_audio(self, data: bytes) -> None:
        self.audio.append(data)

    async def send_text(self, text: str) -> None:
        self.texts.append(text)

    async def start_activity(self) -> None:
        self.activity.append("start")

    async def end_activity(self) -> None:
        self.activity.append("end")

    async def receive(self):
        for event in self._events:
            yield event
        if self._hold_open:
            await asyncio.Event().wait()  # keep the session open until cancelled

    async def close(self) -> None:
        self.closed = True


class FakeProvider(LiveProvider):
    name = "fake"

    def __init__(self, events: list[dict] | None = None) -> None:
        self._events = events or []
        self.sessions: list[FakeSession] = []

    @contextlib.asynccontextmanager
    async def session(self, *, system=None, voice=None):
        s = FakeSession(self._events)
        self.sessions.append(s)
        try:
            yield s
        finally:
            await s.close()


# ── Tickets ──────────────────────────────────────────────────────────────────

def test_ticket_is_single_use_and_expires():
    store = live_tickets.TicketStore(ttl_seconds=60)
    token, ttl = store.issue("user-1")
    assert ttl == 60
    assert store.consume(token) == "user-1"
    assert store.consume(token) is None  # replay refused
    assert store.consume("nope") is None


def test_expired_ticket_is_rejected():
    store = live_tickets.TicketStore(ttl_seconds=-1)
    token, _ = store.issue("user-1")
    assert store.consume(token) is None


def test_session_registry_enforces_concurrency():
    reg = live_tickets.SessionRegistry(max_per_user=2)
    assert reg.acquire("u") and reg.acquire("u")
    assert not reg.acquire("u")
    reg.release("u")
    assert reg.acquire("u")


# ── Rate limiter ─────────────────────────────────────────────────────────────

def test_sliding_window_limiter():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60)
    assert all(limiter.allow("k") for _ in range(3))
    assert limiter.allow("k") is False
    assert limiter.allow("other") is True  # separate key


# ── Response translation ─────────────────────────────────────────────────────

def test_translate_audio_and_transcripts():
    response = SimpleNamespace(
        data=b"\x00\x01",
        server_content=SimpleNamespace(
            output_transcription=SimpleNamespace(text="hello"),
            input_transcription=SimpleNamespace(text="hi there"),
            interrupted=False,
            turn_complete=True,
        ),
    )
    events = translate_response(response)
    kinds = [e["type"] for e in events]
    assert kinds == ["audio", "output_transcript", "input_transcript", "turn_complete"]
    assert events[0]["data"] == b"\x00\x01"


def test_translate_empty_response_is_silent():
    assert translate_response(SimpleNamespace(data=None, server_content=None)) == []


def test_translate_interrupted():
    response = SimpleNamespace(
        data=None,
        server_content=SimpleNamespace(
            output_transcription=None,
            input_transcription=None,
            interrupted=True,
            turn_complete=False,
        ),
    )
    assert translate_response(response) == [{"type": "interrupted"}]


# ── Bridge ───────────────────────────────────────────────────────────────────

async def test_bridge_forwards_mic_audio_and_control():
    session = FakeSession([])
    socket = FakeSocket(
        [
            {"type": "websocket.receive", "bytes": b"\x01\x02\x03\x04"},
            {"type": "websocket.receive", "text": '{"type": "activity_start"}'},
            {"type": "websocket.receive", "text": '{"type": "text", "text": "hello"}'},
            {"type": "websocket.receive", "text": '{"type": "close"}'},
        ]
    )
    await asyncio.wait_for(run_bridge(socket, session, voice="Puck"), timeout=5)

    assert socket.sent_json[0]["type"] == "ready"
    assert socket.sent_json[0]["voice"] == "Puck"
    assert session.audio == [b"\x01\x02\x03\x04"]
    assert session.activity == ["start"]
    assert session.texts == ["hello"]


async def test_bridge_forwards_model_audio_and_events():
    session = FakeSession(
        [
            {"type": "audio", "data": b"\xaa\xbb"},
            {"type": "output_transcript", "text": "Hi"},
            {"type": "turn_complete"},
        ],
        hold_open=False,  # the model stream ends, which ends the bridge
    )
    socket = FakeSocket([])  # client never sends; model side ends the bridge
    await asyncio.wait_for(run_bridge(socket, session), timeout=5)

    assert socket.sent_bytes == [b"\xaa\xbb"]
    kinds = [e["type"] for e in socket.sent_json]
    assert kinds[0] == "ready"
    assert "output_transcript" in kinds and "turn_complete" in kinds


# ── HTTP ticket endpoint ─────────────────────────────────────────────────────

async def test_ticket_endpoint_requires_auth(client):
    resp = await client.post("/live/ticket", json={})
    assert resp.status_code == 401


async def test_ticket_endpoint_issues_usable_ticket(client):
    tokens = await register(client)
    resp = await client.post(
        "/live/ticket",
        json={"voice": "Kore"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["voice"] == "Kore"
    assert body["input_rate"] == 16000
    assert body["output_rate"] == 24000
    assert "Kore" in body["voices"]
    # The returned ticket is real and single-use.
    assert live_tickets.tickets.consume(body["ticket"]) is not None
    assert live_tickets.tickets.consume(body["ticket"]) is None


async def test_ticket_endpoint_rate_limited(client):
    tokens = await register(client, email="ratelimit@example.com")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    _connect_limiter.reset()
    limit = _connect_limiter.limit
    for _ in range(limit):
        assert (await client.post("/live/ticket", json={}, headers=headers)).status_code == 200
    resp = await client.post("/live/ticket", json={}, headers=headers)
    assert resp.status_code == 429
    _connect_limiter.reset()


async def test_unknown_voice_falls_back_to_default(client):
    tokens = await register(client, email="voice@example.com")
    resp = await client.post(
        "/live/ticket",
        json={"voice": "NotAVoice"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["voice"] in ("Charon", "Puck", "Kore", "Fenrir", "Aoede")


# ── WebSocket integration ────────────────────────────────────────────────────

def test_ws_session_end_to_end(monkeypatch):
    """A real WebSocket round-trip through the ASGI app, with the provider faked.
    No ticket/auth DB is involved beyond the ticket store itself."""
    fake = FakeProvider([{"type": "audio", "data": b"\x99\x88"}])
    app.dependency_overrides[get_live_provider] = lambda: fake
    try:
        ticket, _ = live_tickets.tickets.issue("ws-user")
        client = TestClient(app)
        with client.websocket_connect(f"/live/session?ticket={ticket}&voice=Kore") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            ws.send_bytes(b"\x01\x02")
            audio = ws.receive_bytes()
            assert audio == b"\x99\x88"
            ws.send_json({"type": "close"})
        # The provider's session received the microphone bytes.
        assert fake.sessions[0].audio == [b"\x01\x02"]
    finally:
        app.dependency_overrides.pop(get_live_provider, None)


def test_ws_rejects_invalid_ticket():
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/live/session?ticket=not-a-real-ticket") as ws:
            ws.receive_json()
