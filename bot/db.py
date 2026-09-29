from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from bot.config import DB_PATH, ensure_dirs
from bot.models import Base

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False, future=True)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    ensure_dirs()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    await engine.dispose()
