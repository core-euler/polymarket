import asyncio
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_engine_pid: int | None = None
_engine_loop_id: int | None = None


def _get_loop_id() -> int | None:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def _get_or_create_engine_and_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    global _engine, _session_factory, _engine_pid, _engine_loop_id
    current_pid = os.getpid()
    current_loop_id = _get_loop_id()
    loop_mismatch = (
        _engine_loop_id is not None
        and current_loop_id is not None
        and _engine_loop_id != current_loop_id
    )
    if _engine is None or _session_factory is None or _engine_pid != current_pid or loop_mismatch:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        _engine_pid = current_pid
        _engine_loop_id = current_loop_id
    return _engine, _session_factory


def get_engine() -> AsyncEngine:
    engine, _ = _get_or_create_engine_and_factory()
    return engine


def SessionLocal() -> AsyncSession:
    _, factory = _get_or_create_engine_and_factory()
    return factory()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
