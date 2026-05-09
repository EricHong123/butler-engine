"""Async SQLAlchemy session management for PostgreSQL."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from butler.config import settings

_engine = None
_sessionmaker = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session per request."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            await session.close()


async def set_tenant_context(tenant_id: str, session=None) -> None:
    """
    Set PostgreSQL session variable for RLS tenant isolation.

    Must be called before any query on tenant-scoped tables.
    Uses SET LOCAL so it applies only to the current transaction.
    """
    if not tenant_id:
        return
    if session:
        await session.execute(
            __import__("sqlalchemy").text(
                f"SELECT set_config('app.tenant_id', :tid, true)"
            ),
            {"tid": tenant_id},
        )
    else:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text(
                    f"SELECT set_config('app.tenant_id', :tid, false)"
                ),
                {"tid": tenant_id},
            )
            await conn.commit()


async def init_db() -> None:
    """Create all tables (dev only — use Alembic in production)."""
    from butler.models.base import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose engine on shutdown."""
    if _engine:
        await _engine.dispose()
