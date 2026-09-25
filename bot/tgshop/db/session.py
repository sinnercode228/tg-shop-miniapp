"""Engine / session factory helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from .models import Base

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    if url.startswith("sqlite") and ":memory:" in url:
        # One shared connection, otherwise every session would see its own empty database.
        return create_async_engine(
            url, echo=echo, poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    return create_async_engine(url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine) -> None:
    """Create tables if they don't exist (demo-friendly; use Alembic for real migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
