"""
database.py — Async SQLAlchemy engine wired to Neon PostgreSQL.

Reads DATABASE_URL from .env.  The URL must use the asyncpg driver:
  postgresql+asyncpg://user:pass@host/db?ssl=require

Usage in routes:
  from app.db.database import get_db
  async def my_route(db: AsyncSession = Depends(get_db)): ...
"""

import os
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI dependency — yields an async session, auto-closes."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
