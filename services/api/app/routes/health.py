from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/health/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness: confirms the database is reachable."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - surface any DB error as 503
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")
    return {"status": "ready"}
