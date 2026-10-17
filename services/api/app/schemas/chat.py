from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    conversation_id: str | None = None
    model: str | None = None
    system: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class CreateConversation(BaseModel):
    title: str = Field(default="New conversation", max_length=200)


class ProviderInfo(BaseModel):
    name: str
    configured: bool
    model: str = ""
