"""
Aegis MOS — Shared FastAPI dependencies.

Provides dependency injection for database sessions, configuration,
and shared state used across API routes.
"""

import os

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db_session


async def get_db(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    """Alias dependency for database session injection."""
    return session


def get_hmac_secret() -> bytes:
    """Return the HMAC secret key for command signing (F6)."""
    key = os.getenv("HMAC_SECRET_KEY", "dev-secret-key-change-in-production")
    return key.encode("utf-8")
