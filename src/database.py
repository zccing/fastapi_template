"""SQLAlchemy 异步引擎、Session 工厂和 FastAPI 数据库依赖。"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import ConnectionPoolEntry

from src.config import Config, settings


def _enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(config: Config) -> AsyncEngine:
    """为应用或隔离测试创建惰性连接引擎；调用方负责 dispose。"""

    database_engine = create_async_engine(
        config.DATABASE_ASYNC_URL,
        pool_size=config.DATABASE_POOL_SIZE,
        pool_recycle=config.DATABASE_POOL_TTL,
        pool_pre_ping=config.DATABASE_POOL_PRE_PING,
    )
    if database_engine.dialect.name == "sqlite":
        event.listen(database_engine.sync_engine, "connect", _enable_sqlite_foreign_keys)

    return database_engine


# 首次数据库操作才建立连接，应用关闭时由 lifespan 释放连接池。
engine = create_database_engine(settings)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """提供路径操作作用域的 Session；写事务由领域顶层 Service 显式提交。

    Yields:
        由本依赖负责关闭的 SQLAlchemy 异步 Session。
    """
    async with SessionFactory() as session:
        yield session


DBSession = Annotated[
    AsyncSession,
    Depends(get_db_session, scope="function"),
]


async def close_database() -> None:
    """在应用关闭时释放数据库引擎的连接池资源。"""
    await engine.dispose()
