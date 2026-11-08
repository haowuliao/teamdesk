"""异步引擎/会话工厂 + 建表/seed 启动钩子。"""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import config
from .models import Base


async def ensure_data_dir() -> None:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(config.DATA_DIR, "corpus"), exist_ok=True)


engine = create_async_engine(config.DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    await ensure_data_dir()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    await engine.dispose()


def get_session():
    """FastAPI dependency：一个请求一个会话。"""
    async def _dep():
        async with SessionLocal() as session:
            yield session
    return _dep
