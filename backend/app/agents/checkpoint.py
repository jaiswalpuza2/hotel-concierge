"""LangGraph checkpointer: PostgreSQL in production, in-memory fallback."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def _noop() -> None:
    return None


async def open_checkpointer(database_url: str) -> tuple[Any, Callable[[], Awaitable[None]], str]:
    """Create the conversation checkpointer.

    Returns:
        ``(saver, close, kind)`` where ``kind`` is ``"postgres"`` or ``"memory"``.

    PostgreSQL persistence lets a conversation (history, active quotes, handoff
    state) survive API restarts. If the optional packages are missing or the
    connection fails (e.g. psycopg's async mode does not work on Windows'
    default Proactor event loop), we log a warning and fall back to memory so
    the product still runs; run in Docker/Linux for persistent checkpoints.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        conninfo = database_url.replace("postgresql+asyncpg://", "postgresql://")
        pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=5,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await pool.open(wait=True, timeout=10)
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        logger.info("checkpointer.ready", kind="postgres")
        return saver, pool.close, "postgres"
    except Exception as exc:
        logger.warning(
            "checkpointer.postgres_unavailable_using_memory",
            error=f"{exc.__class__.__name__}: {str(exc)[:160]}",
        )

    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver(), _noop, "memory"
