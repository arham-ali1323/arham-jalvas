"""AI provider abstraction.

The conversation lives behind `AIProvider` so the transport (REST/SSE today,
Gemini Live and local LLMs later) is swappable without touching the routes.

Gemini is the only production provider wired up today. A missing API key is a
hard, explicit error (503 at the API edge) — never silently substituted with
fake output.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import AsyncIterator

from app.config import get_settings


class ProviderNotConfigured(RuntimeError):
    """No usable AI provider is configured for this deployment."""


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant" | "system"
    content: str


class AIProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def stream(
        self, messages: list[ChatMessage], *, system: str | None = None
    ) -> AsyncIterator[str]:
        """Yield response text chunks as they are produced."""
        raise NotImplementedError

    async def complete(
        self, messages: list[ChatMessage], *, system: str | None = None
    ) -> str:
        parts: list[str] = []
        async for chunk in self.stream(messages, system=system):
            parts.append(chunk)
        return "".join(parts)


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        # Imported lazily so the service starts even where the SDK is absent.
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.model = model

    @staticmethod
    def _to_contents(messages: list[ChatMessage]) -> list:
        from google.genai import types

        out = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            out.append(types.Content(role=role, parts=[types.Part(text=m.content)]))
        return out

    async def stream(
        self, messages: list[ChatMessage], *, system: str | None = None
    ) -> AsyncIterator[str]:
        from google.genai import types

        config = (
            types.GenerateContentConfig(system_instruction=system)
            if system
            else None
        )
        stream = await self._client.aio.models.generate_content_stream(
            model=self.model,
            contents=self._to_contents(messages),
            config=config,
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if text:
                yield text


def build_provider() -> AIProvider:
    """Construct the configured provider or raise `ProviderNotConfigured`."""
    settings = get_settings()
    choice = (settings.ai_provider or "none").lower()

    if choice == "gemini":
        if not settings.gemini_api_key:
            raise ProviderNotConfigured(
                "GEMINI_API_KEY is not set; cannot serve chat completions."
            )
        return GeminiProvider(settings.gemini_api_key, settings.gemini_text_model)

    raise ProviderNotConfigured(f"Unknown AI_PROVIDER '{settings.ai_provider}'.")
