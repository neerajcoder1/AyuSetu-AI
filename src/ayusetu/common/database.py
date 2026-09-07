"""
Database Engine and Session Factory
====================================
Provides sync and async SQLAlchemy engines, session factories, and base class.
"""

from typing import Generator, AsyncGenerator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from ayusetu.common.config import settings

# Base Declarative Class
Base = declarative_base()

# Sync Engine (for Alembic migrations, seeding, scripts, sync endpoints)
sync_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)
SyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
    expire_on_commit=False,
    class_=Session
)

def get_db() -> Generator[Session, None, None]:
    """Yield a sync database session."""
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Async Engine (for high-throughput FastAPI endpoints where needed)
try:
    async_engine = create_async_engine(
        settings.async_db_url,
        pool_pre_ping=True,
        future=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
except Exception:
    async_engine = None
    AsyncSessionLocal = None

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Async database session maker is not configured.")
    async with AsyncSessionLocal() as session:
        yield session
