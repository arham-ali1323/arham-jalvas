"""Live voice endpoints.

    POST /live/ticket   — authenticated; mints a single-use WebSocket ticket.
    WS   /live/session  — the audio bridge; authenticates with a ticket.

The WebSocket never sees a bearer token or a Gemini key. See
`app/services/live_tickets.py` for why the ticket exchange exists.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.deps import get_current_user
from app.models.user import User
from app.schemas.live import LiveTicketRequest, LiveTicketResponse
from app.services import live as live_service
from app.services import live_tickets
from app.services.ai import ProviderNotConfigured
from app.services.ratelimit import SlidingWindowLimiter

log = logging.getLogger("mark_liv.live")
router = APIRouter(tags=["live"])

# One limiter instance per process. See app/services/ratelimit.py for the
# multi-worker caveat.
_settings = get_settings()
_connect_limiter = SlidingWindowLimiter(
    _settings.live_connect_attempts_per_minute, window_seconds=60.0
)


def get_live_provider() -> live_service.LiveProvider:
    """Dependency so tests can substitute a fake provider."""
    return live_service.build_live_provider()


@router.post("/ticket", response_model=LiveTicketResponse)
async def create_ticket(
    body: LiveTicketRequest | None = None,
    user: User = Depends(get_current_user),
) -> LiveTicketResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503, detail="Live voice is not configured on this server."
        )
    if not _connect_limiter.allow(user.id):
        raise HTTPException(
            status_code=429, detail="Too many live-voice requests. Please slow down."
        )

    voice = live_service.resolve_voice(body.voice if body else None)
    ticket, ttl = live_tickets.tickets.issue(user.id)
    return LiveTicketResponse(
        ticket=ticket,
        expires_in=int(ttl),
        model=settings.gemini_live_model,
        voice=voice,
        voices=list(live_service.ALLOWED_VOICES),
        input_rate=live_service.INPUT_SAMPLE_RATE,
        output_rate=live_service.OUTPUT_SAMPLE_RATE,
    )


@router.websocket("/session")
async def live_session(
    websocket: WebSocket,
    provider: live_service.LiveProvider = Depends(get_live_provider),
) -> None:
    # The ticket is the only credential on this transport. An invalid or reused
    # ticket is refused before the socket is accepted.
    user_id = live_tickets.tickets.consume(websocket.query_params.get("ticket", ""))
    if not user_id:
        await websocket.close(code=4401)  # application-defined: unauthorized
        return

    if not live_tickets.sessions.acquire(user_id):
        await websocket.close(code=4429)  # too many concurrent sessions
        return

    await websocket.accept()
    voice = live_service.resolve_voice(websocket.query_params.get("voice"))
    settings = get_settings()

    try:
        # Open the upstream model session first so a misconfiguration is reported
        # as a clean control frame instead of a socket that dies mid-conversation.
        async with provider.session(voice=voice) as session:
            await live_service.run_bridge(
                websocket,
                session,
                voice=voice,
                input_rate=live_service.INPUT_SAMPLE_RATE,
                output_rate=live_service.OUTPUT_SAMPLE_RATE,
            )
    except ProviderNotConfigured as exc:
        log.warning("live session unavailable: %s", exc)
        await _safe_send_error(websocket, str(exc))
    except WebSocketDisconnect:
        pass  # the client closed; nothing to report
    except Exception:  # noqa: BLE001 - a dead socket must not crash the worker
        log.exception("live session failed")
        await _safe_send_error(websocket, "The voice session ended unexpectedly.")
    finally:
        live_tickets.sessions.release(user_id)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001 - already closed
            pass


async def _safe_send_error(websocket: WebSocket, message: str) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:  # noqa: BLE001
        pass
