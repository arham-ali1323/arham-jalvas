from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_sessionmaker
from app.deps import get_current_user, get_db
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import ChatRequest, ProviderInfo
from app.services.ai import AIProvider, ChatMessage, ProviderNotConfigured, build_provider

log = logging.getLogger("mark_liv.chat")
router = APIRouter(tags=["chat"])


def get_provider() -> AIProvider:
    """Dependency so tests can override the provider with a fake."""
    try:
        return build_provider()
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _resolve_conversation(
    db: AsyncSession, user: User, body: ChatRequest
) -> Conversation:
    if body.conversation_id:
        conv = await db.get(Conversation, body.conversation_id)
        if conv is None or conv.user_id != user.id:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return conv
    title = " ".join(body.message.split())[:60] or "New conversation"
    conv = Conversation(user_id=user.id, title=title)
    db.add(conv)
    await db.flush()
    return conv


@router.get("/providers", response_model=list[ProviderInfo])
async def providers(user: User = Depends(get_current_user)) -> list[ProviderInfo]:
    settings = get_settings()
    configured = (
        settings.ai_provider.lower() == "gemini" and bool(settings.gemini_api_key)
    )
    return [
        ProviderInfo(
            name=settings.ai_provider,
            configured=configured,
            model=settings.gemini_text_model if configured else "",
        )
    ]


@router.post("/completions")
async def completions(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    provider: AIProvider = Depends(get_provider),
) -> StreamingResponse:
    """Persist the user turn, stream the assistant reply as Server-Sent Events,
    then persist the assistant turn. Each event is `data: {json}`."""
    conv = await _resolve_conversation(db, user, body)
    now = datetime.now(timezone.utc)
    db.add(
        Message(
            conversation_id=conv.id,
            user_id=user.id,
            role="user",
            content=body.message,
            created_at=now,
            updated_at=now,
        )
    )
    conv.updated_at = now
    await db.commit()

    # Snapshot everything the streaming generator needs before the request-scoped
    # session is closed. The generator opens its own session to persist the reply.
    conv_id = conv.id
    user_id = user.id
    rows = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    history = [
        ChatMessage(role=m.role, content=m.content)
        for m in rows
        if m.role in ("user", "assistant")
    ]
    system = body.system

    async def event_stream():
        collected: list[str] = []
        try:
            async for chunk in provider.stream(history, system=system):
                collected.append(chunk)
                yield _sse({"type": "delta", "text": chunk})
        except Exception as exc:  # noqa: BLE001 - report, don't kill the stream
            log.exception("provider stream failed")
            yield _sse({"type": "error", "message": str(exc)})
        finally:
            text = "".join(collected).strip()
            if text:
                try:
                    async with get_sessionmaker()() as session:
                        stamp = datetime.now(timezone.utc)
                        session.add(
                            Message(
                                conversation_id=conv_id,
                                user_id=user_id,
                                role="assistant",
                                content=text,
                                created_at=stamp,
                                updated_at=stamp,
                            )
                        )
                        stored = await session.get(Conversation, conv_id)
                        if stored is not None:
                            stored.updated_at = stamp
                        await session.commit()
                except Exception:  # noqa: BLE001
                    log.exception("failed to persist assistant message")
            yield _sse({"type": "done", "conversation_id": conv_id})
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
