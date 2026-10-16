"""Aggregate router for all /api/v1 endpoints (mounted under ``/api/v1`` in ``app/main.py``)."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.voice import router as voice_router

api_router = APIRouter()

# Auth - /api/v1/auth/login, /refresh, /logout
api_router.include_router(auth_router, prefix="/auth")
# Documents - /api/v1/documents (+ /documents/ingest-sample-kb from the admin router)
api_router.include_router(documents_router, prefix="/documents")
# Guest chat - /api/v1/chat/message, /history/{id}, /capabilities
api_router.include_router(chat_router)
# Voice over HTTP - /api/v1/voice/transcribe, /voice/speak
api_router.include_router(voice_router)
# Staff: bookings, conversations, handoffs, stats
api_router.include_router(admin_router)

__all__ = ["api_router"]
