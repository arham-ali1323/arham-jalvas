"""Shared test fixtures.

Environment variables are set BEFORE the app is imported so the cached settings
and engine point at a throwaway SQLite database, never the developer's data.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="markliv_test_"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.as_posix()}/test.db"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["ENVIRONMENT"] = "development"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["AI_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = "test-key"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database.session import get_engine  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.routes.chat import get_provider  # noqa: E402
from app.services.ai import AIProvider  # noqa: E402


class FakeProvider(AIProvider):
    name = "fake"

    async def stream(self, messages, *, system=None):
        for piece in ("Hello", ", ", "world"):
            yield piece


@pytest_asyncio.fixture(autouse=True)
async def _database():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _override_provider():
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    yield
    app.dependency_overrides.pop(get_provider, None)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def register(client: AsyncClient, email: str = "user@example.com",
                   password: str = "supersecret1") -> dict:
    resp = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
