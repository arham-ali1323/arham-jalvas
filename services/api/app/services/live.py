"""Real-time voice: a swappable live-session abstraction and the bridge that
pumps audio between a WebSocket client and the model.

WHY A RELAY, NOT A DIRECT BROWSER CONNECTION
    The brief is explicit: the permanent Gemini key must never reach the
    browser. So the browser talks only to this service. It sends raw PCM16 mono
    at 16 kHz and receives raw PCM16 mono at 24 kHz plus small JSON control
    frames. The key, the model name and the system instruction all stay here.

WHAT THE BROWSER SEES
    Binary WebSocket frames  -> model audio, PCM16 @ 24 kHz.
    Text   WebSocket frames  -> JSON control, one of:
        {"type": "ready",  "input_rate": 16000, "output_rate": 24000, "voice": ...}
        {"type": "input_transcript",  "text": ...}
        {"type": "output_transcript", "text": ...}
        {"type": "turn_complete"}
        {"type": "interrupted"}
        {"type": "error", "message": ...}

    Browser -> server:
        binary frames                       -> microphone PCM16 @ 16 kHz
        {"type": "text", "text": ...}       -> a typed turn
        {"type": "activity_start"}          -> manual VAD / push-to-talk begin
        {"type": "activity_end"}            -> manual VAD / push-to-talk end
        {"type": "close"}                   -> end the session

TESTABILITY
    `run_bridge` depends only on two small protocols (`LiveSocket`,
    `LiveSession`), so the whole pump can be tested with in-memory fakes and no
    network, no microphone and no FastAPI.
"""
from __future__ import annotations

import abc
import asyncio
import contextlib
import logging
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from app.config import get_settings
from app.services.ai import ProviderNotConfigured

log = logging.getLogger("mark_liv.live")

# The same prebuilt voices the desktop offers, so a user hears a consistent
# assistant regardless of which client they are on.
ALLOWED_VOICES: tuple[str, ...] = ("Charon", "Puck", "Kore", "Fenrir", "Aoede")

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000

_DEFAULT_SYSTEM = (
    "You are MARK LIV, a helpful, calm, spoken AI assistant. Replies are read "
    "aloud, so keep them concise and natural: no markdown, no bullet symbols, "
    "no code blocks unless explicitly asked. Answer in the language the user is "
    "speaking."
)


def resolve_voice(requested: str | None) -> str:
    """Server-approved voice, falling back to the configured default. A client
    cannot smuggle an arbitrary string into the model config."""
    settings = get_settings()
    if requested and requested in ALLOWED_VOICES:
        return requested
    if settings.live_voice_name in ALLOWED_VOICES:
        return settings.live_voice_name
    return ALLOWED_VOICES[0]


# ── Session abstraction ──────────────────────────────────────────────────────

class LiveSession(abc.ABC):
    """One open real-time conversation with a model."""

    @abc.abstractmethod
    async def send_audio(self, data: bytes) -> None: ...

    @abc.abstractmethod
    async def send_text(self, text: str) -> None: ...

    @abc.abstractmethod
    def receive(self) -> AsyncIterator[dict[str, Any]]: ...

    @abc.abstractmethod
    async def start_activity(self) -> None: ...

    @abc.abstractmethod
    async def end_activity(self) -> None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...


class LiveProvider(abc.ABC):
    """Opens live sessions. Matches the shape of `AIProvider` (one-shot text),
    so both transports are swappable the same way."""

    name = "base"

    @abc.abstractmethod
    def session(
        self, *, system: str | None = None, voice: str | None = None
    ) -> "contextlib.AbstractAsyncContextManager[LiveSession]": ...


def translate_response(response: Any) -> list[dict[str, Any]]:
    """Turn one SDK `LiveServerMessage` into transport-neutral events.

    Kept as a free function taking a duck-typed object so it can be unit-tested
    without the SDK, the network, or a real session."""
    events: list[dict[str, Any]] = []

    data = getattr(response, "data", None)
    if data:
        events.append({"type": "audio", "data": data})

    server_content = getattr(response, "server_content", None)
    if server_content is not None:
        out = getattr(server_content, "output_transcription", None)
        if out is not None and getattr(out, "text", None):
            events.append({"type": "output_transcript", "text": out.text})
        inp = getattr(server_content, "input_transcription", None)
        if inp is not None and getattr(inp, "text", None):
            events.append({"type": "input_transcript", "text": inp.text})
        if getattr(server_content, "interrupted", False):
            events.append({"type": "interrupted"})
        if getattr(server_content, "turn_complete", False):
            events.append({"type": "turn_complete"})

    return events


class GeminiLiveSession(LiveSession):
    """Thin adapter over `google.genai`'s Live session. Nothing here is
    Gemini-specific in shape — a second provider implements the same class."""

    def __init__(self, client: Any, model: str, config: Any) -> None:
        self._client = client
        self._model = model
        self._config = config
        self._cm: Any = None
        self._session: Any = None

    async def connect(self) -> None:
        self._cm = self._client.aio.live.connect(model=self._model, config=self._config)
        self._session = await self._cm.__aenter__()

    async def send_audio(self, data: bytes) -> None:
        from google.genai import types

        await self._session.send_realtime_input(
            audio=types.Blob(data=data, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
        )

    async def send_text(self, text: str) -> None:
        await self._session.send_client_content(
            turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True
        )

    async def start_activity(self) -> None:
        from google.genai import types

        with contextlib.suppress(Exception):
            await self._session.send_realtime_input(activity_start=types.ActivityStart())

    async def end_activity(self) -> None:
        from google.genai import types

        with contextlib.suppress(Exception):
            await self._session.send_realtime_input(activity_end=types.ActivityEnd())

    async def receive(self) -> AsyncIterator[dict[str, Any]]:
        async for response in self._session.receive():
            for event in translate_response(response):
                yield event

    async def close(self) -> None:
        if self._cm is not None:
            with contextlib.suppress(Exception):
                await self._cm.__aexit__(None, None, None)
            self._cm = None
            self._session = None


class GeminiLiveProvider(LiveProvider):
    name = "gemini"

    @contextlib.asynccontextmanager
    async def session(
        self, *, system: str | None = None, voice: str | None = None
    ) -> AsyncIterator[LiveSession]:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise ProviderNotConfigured(
                "GEMINI_API_KEY is not set; live voice is unavailable."
            )

        # Imported lazily so this module (and its tests) do not require the SDK.
        from google import genai
        from google.genai import types

        instruction = (system or settings.live_system_instruction or _DEFAULT_SYSTEM)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=instruction,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=resolve_voice(voice)
                    )
                )
            ),
        )

        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options={"api_version": "v1beta"},
        )
        session = GeminiLiveSession(client, settings.gemini_live_model, config)
        try:
            await session.connect()
        except Exception:
            await session.close()
            raise
        try:
            yield session
        finally:
            await session.close()


def build_live_provider() -> LiveProvider:
    """Construction never fails; the key is checked when a session is opened so
    an unconfigured server can still be started and probed."""
    return GeminiLiveProvider()


# ── The bridge ───────────────────────────────────────────────────────────────

@runtime_checkable
class LiveSocket(Protocol):
    """The subset of `starlette`'s `WebSocket` the bridge uses. A fake with the
    same three methods fully exercises the pump in tests."""

    async def receive(self) -> dict[str, Any]: ...

    async def send_bytes(self, data: bytes) -> None: ...

    async def send_json(self, data: dict[str, Any]) -> None: ...


async def run_bridge(
    socket: LiveSocket,
    session: LiveSession,
    *,
    voice: str = "",
    input_rate: int = INPUT_SAMPLE_RATE,
    output_rate: int = OUTPUT_SAMPLE_RATE,
) -> None:
    """Pump both directions until either side ends. Never raises: transport
    failures are reported to the client and swallowed so the caller can close
    the socket cleanly."""
    stopped = asyncio.Event()

    await socket.send_json(
        {
            "type": "ready",
            "input_rate": input_rate,
            "output_rate": output_rate,
            "voice": voice,
        }
    )

    async def client_to_model() -> None:
        try:
            while True:
                message = await socket.receive()
                msg_type = message.get("type")
                if msg_type == "websocket.disconnect":
                    return
                data = message.get("bytes")
                text = message.get("text")
                if data:
                    await session.send_audio(data)
                elif text:
                    if not await _handle_control(session, text):
                        return
        finally:
            stopped.set()

    async def model_to_client() -> None:
        try:
            async for event in session.receive():
                if event["type"] == "audio":
                    await socket.send_bytes(event["data"])
                else:
                    await socket.send_json(event)
        finally:
            stopped.set()

    tasks = [
        asyncio.create_task(client_to_model(), name="live-client-in"),
        asyncio.create_task(model_to_client(), name="live-model-out"),
    ]
    try:
        await stopped.wait()
    except asyncio.CancelledError:
        raise
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


async def _handle_control(session: LiveSession, text: str) -> bool:
    """Handle one JSON control frame. Returns False when the client asked to end
    the session."""
    import json

    try:
        control = json.loads(text)
    except (ValueError, TypeError):
        return True
    if not isinstance(control, dict):
        return True

    kind = control.get("type")
    if kind == "text":
        payload = str(control.get("text") or "")
        if payload:
            await session.send_text(payload)
    elif kind == "activity_start":
        await session.start_activity()
    elif kind == "activity_end":
        await session.end_activity()
    elif kind == "close":
        return False
    return True
