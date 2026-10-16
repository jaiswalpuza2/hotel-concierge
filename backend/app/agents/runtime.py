"""Application runtime: builds every collaborator once at start-up."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.chat_service import ChatService
from app.agents.checkpoint import open_checkpointer
from app.agents.graph import compile_graph
from app.agents.graph_spec import build_spec
from app.agents.ports import AgentDeps, AgentSettings
from app.api.ws.manager import ConnectionManager
from app.business.profiles import get_profile
from app.config import get_settings
from app.handoff.providers import build_alert_provider
from app.handoff.service import HandoffService
from app.llm.factory import get_llm
from app.notifications.providers import build_email_provider, build_sms_provider
from app.notifications.service import NotificationService
from app.rag.service import KnowledgeService
from app.tools.hotel_tools import HotelToolExecutor
from app.utils.timeutil import nepal_today
from app.voice.providers import build_stt, build_tts

logger = structlog.get_logger(__name__)


@dataclass
class ConciergeRuntime:
    """Everything the API layer needs, created in the app lifespan."""

    chat: ChatService
    handoff: HandoffService
    ws: ConnectionManager
    checkpointer_kind: str
    close: Any  # async callable releasing the checkpointer pool


async def build_runtime(session_factory: async_sessionmaker[AsyncSession], database_url: str) -> ConciergeRuntime:
    """Wire LLM, tools, RAG, notifications, handoff and voice into one chat service."""
    settings = get_settings()
    ws = ConnectionManager()
    knowledge = KnowledgeService(session_factory)
    handoff = HandoffService(session_factory, build_alert_provider(), ws)
    notifier = NotificationService(session_factory, build_sms_provider(), build_email_provider())
    profile = get_profile(settings.business_type)
    tools = HotelToolExecutor(session_factory, knowledge.search)

    deps = AgentDeps(
        llm=get_llm(),
        tools=tools,
        knowledge=knowledge,
        handoff=handoff,
        notifier=notifier,
        profile=profile,
        today=nepal_today,
        settings=AgentSettings(
            max_tool_iterations=settings.max_tool_iterations, history_window=settings.history_window
        ),
    )
    saver, close, kind = await open_checkpointer(database_url)
    graph = compile_graph(build_spec(deps), saver)
    chat = ChatService(graph, session_factory, stt=build_stt(), tts=build_tts(), max_audio_bytes=settings.max_audio_bytes)
    logger.info("runtime.ready", checkpointer=kind, llm=settings.llm_provider, business=profile.id)
    return ConciergeRuntime(chat=chat, handoff=handoff, ws=ws, checkpointer_kind=kind, close=close)
