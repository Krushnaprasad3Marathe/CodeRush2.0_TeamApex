"""
Aegis MOS — Database session and engine configuration.

Connects to Supabase PostgreSQL via asyncpg.
Uses the direct connection (port 5432) for the long-running backend.

Setup:
  1. Get your connection string from Supabase Dashboard:
     Settings → Database → Connection string → URI (direct)
  2. Set it as the DATABASE_URL environment variable
  3. Format: postgresql+asyncpg://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Supabase connection ──────────────────────────────────────────────
# Default is local Postgres for dev; override with Supabase URL in .env
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aegis:aegis_dev@localhost:5432/aegis_mos",
)

# Detect if we're connecting to Supabase's transaction pooler (port 6543)
_is_pooled = ":6543/" in DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5 if not _is_pooled else 1,
    max_overflow=10 if not _is_pooled else 0,
    # Required for Supabase transaction pooler compatibility
    **(
        {
            "pool_class": __import__("sqlalchemy.pool", fromlist=["NullPool"]).NullPool,
            "connect_args": {
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        }
        if _is_pooled
        else {}
    ),
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
