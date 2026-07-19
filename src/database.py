"""SQLAlchemy 异步引擎、Session 工厂和 FastAPI 数据库依赖。"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

# 引擎只在首次执行数据库操作时建立实际连接，应用关闭时由 lifespan 负责释放连接池。
engine = create_async_engine(
    str(settings.DATABASE_ASYNC_URL),
    pool_size=settings.DATABASE_POOL_SIZE,
    pool_recycle=settings.DATABASE_POOL_TTL,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """提供请求级 Session；写事务由领域顶层 Service 显式提交。

    Yields:
        由本依赖负责关闭的 SQLAlchemy 异步 Session。
    """
    async with SessionFactory() as session:
        yield session


DBSession = Annotated[
    AsyncSession,
    Depends(get_db_session),
]


async def close_database() -> None:
    """在应用关闭时释放数据库引擎的连接池资源。"""
    await engine.dispose()
