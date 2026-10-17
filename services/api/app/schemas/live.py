from __future__ import annotations

from pydantic import BaseModel, Field


class LiveTicketRequest(BaseModel):
    # Optional per-session voice; the server validates it against its allowlist.
    voice: str | None = Field(default=None, max_length=40)


class LiveTicketResponse(BaseModel):
    ticket: str
    expires_in: int
    model: str
    voice: str
    voices: list[str]
    input_rate: int
    output_rate: int
