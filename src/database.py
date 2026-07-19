"""SQLAlchemy 异步数据库资源和最小查询辅助函数。

本模块只负责连接、查询结果转换和事务边界，不承载领域业务逻辑。读操作返回
普通字典，写操作在本模块创建连接时使用独立事务；如果调用方传入连接，则由
调用方负责该连接的事务提交或回滚。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import Delete, Insert, MetaData, Select, Update
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from src.config import settings
from src.constants import DB_NAMING_CONVENTION

# 引擎只在首次执行数据库操作时建立实际连接，应用关闭时由 lifespan 负责释放连接池。
engine = create_async_engine(
    str(settings.DATABASE_ASYNC_URL),
    pool_size=settings.DATABASE_POOL_SIZE,
    pool_recycle=settings.DATABASE_POOL_TTL,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
)
# 领域模型定义后应统一挂载到这个命名约定下，供迁移工具读取。
metadata = MetaData(naming_convention=DB_NAMING_CONVENTION)


@asynccontextmanager
async def _connection_context(
    connection: AsyncConnection | None = None,
) -> AsyncIterator[AsyncConnection]:
    """复用调用方连接，或临时创建一个自动关闭的连接。"""

    if connection is not None:
        yield connection
        return

    async with engine.connect() as managed_connection:
        yield managed_connection


async def fetch_one(
    statement: Select[Any],
    connection: AsyncConnection | None = None,
) -> dict[str, Any] | None:
    """执行查询并返回第一行。

    Args:
        statement: 只读的 SQLAlchemy ``Select`` 语句。
        connection: 可选的调用方连接；未提供时由本函数临时创建并关闭。

    Returns:
        第一行数据组成的字典；查询没有结果时返回 ``None``。
    """
    async with _connection_context(connection) as active_connection:
        result = await active_connection.execute(statement)
        row = result.mappings().first()
        return None if row is None else dict(row)


async def fetch_all(
    statement: Select[Any],
    connection: AsyncConnection | None = None,
) -> list[dict[str, Any]]:
    """执行查询并返回全部结果。

    Args:
        statement: 只读的 SQLAlchemy ``Select`` 语句。
        connection: 可选的调用方连接；未提供时由本函数临时创建并关闭。

    Returns:
        按查询顺序排列的字典列表；没有结果时返回空列表。
    """
    async with _connection_context(connection) as active_connection:
        result = await active_connection.execute(statement)
        return [dict(row) for row in result.mappings().all()]


async def execute(
    statement: Insert | Update | Delete,
    connection: AsyncConnection | None = None,
) -> None:
    """执行写语句，并在本函数拥有连接时自动提交事务。

    Args:
        statement: SQLAlchemy ``Insert``、``Update`` 或 ``Delete`` 语句。
        connection: 可选的调用方连接。传入后不会自动提交，事务由调用方管理。

    Raises:
        sqlalchemy.exc.SQLAlchemyError: 数据库执行失败时向调用方传播原始异常。
    """
    if connection is None:
        async with engine.begin() as managed_connection:
            await managed_connection.execute(statement)
        return

    await connection.execute(statement)


async def get_db_connection() -> AsyncIterator[AsyncConnection]:
    """为 FastAPI 依赖注入提供一个自动关闭的数据库连接。

    Yields:
        一个由本依赖负责关闭的异步数据库连接。
    """
    async with _connection_context() as connection:
        yield connection


async def close_database() -> None:
    """在应用关闭时释放数据库引擎的连接池资源。"""
    await engine.dispose()
