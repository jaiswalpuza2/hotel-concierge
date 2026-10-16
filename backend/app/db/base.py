"""SQLAlchemy async engine, session factory, and declarative Base."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    All models inherit from this class so Alembic's autogenerate
    can discover them when they are imported into alembic/env.py.
    """


def _build_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine from settings."""
    settings = get_settings()
    return create_async_engine(
        settings.db_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # detect stale connections
        echo=settings.app_env == "development",
    )


# Module-level engine and session factory — created once, reused everywhere.
engine = _build_engine()

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # objects remain usable after commit without re-query
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session per request.

    The session is automatically closed when the request context exits.
    Roll back on any unhandled exception to leave the DB in a clean state.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
