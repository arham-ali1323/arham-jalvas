from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import get_current_user, get_db
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.chat import (
    ConversationDetail,
    ConversationOut,
    CreateConversation,
    MessageOut,
)

router = APIRouter(tags=["conversations"])


async def _owned_conversation(
    db: AsyncSession, user: User, conversation_id: str, *, with_messages: bool = False
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user.id
    )
    if with_messages:
        stmt = stmt.options(selectinload(Conversation.messages))
    conv = (await db.execute(stmt)).scalar_one_or_none()
    if conv is None:
        # 404 (not 403) so another user's IDs are indistinguishable from absent.
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: CreateConversation,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    conv = Conversation(user_id=user.id, title=body.title.strip() or "New conversation")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    return await _owned_conversation(db, user, conversation_id, with_messages=True)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    await _owned_conversation(db, user, conversation_id)
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    conv = await _owned_conversation(db, user, conversation_id)
    await db.delete(conv)
    await db.commit()
    return None
