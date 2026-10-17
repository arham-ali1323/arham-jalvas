"""MARK LIV shared backend — FastAPI application factory.

Run locally:
    uvicorn app.main:app --reload --port 8080
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import auth, chat, conversations, devices, health, live

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        # Interactive docs are disabled in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth")
    app.include_router(conversations.router, prefix="/conversations")
    app.include_router(chat.router, prefix="/chat")
    app.include_router(live.router, prefix="/live")
    app.include_router(devices.router, prefix="/devices")

    @app.get("/")
    async def root() -> dict:
        return {
            "service": settings.app_name,
            "environment": settings.environment,
            "docs": None if settings.is_production else "/docs",
        }

    return app


app = create_app()
