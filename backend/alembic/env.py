"""Alembic async environment — reads DB_URL from environment variables."""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Read local .env first, then the repo-root .env (which docker-compose uses).
# Existing environment variables always win.
_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_here, "..", ".env"))
load_dotenv(os.path.join(_here, "..", "..", ".env"))

# Alembic Config object gives access to values in alembic.ini
config = context.config

# Interpret the alembic.ini logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all ORM models via the registry so Alembic can detect schema changes.
import app.db.models  # noqa: F401,E402 — registers all models on Base.metadata
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata

# Override sqlalchemy.url with DB_URL from the environment.
# This allows docker-compose to inject the correct URL without
# editing alembic.ini (which is committed to source control).
db_url = os.environ.get("DB_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/hoteldb")
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no DB connection, generates SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within an active connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
