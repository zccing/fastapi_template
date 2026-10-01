from contextlib import asynccontextmanager
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import src.database as database
from src.config import Config
from src.constants import DB_NAMING_CONVENTION, Environment
from src.models import Base


def test_orm_base_uses_shared_naming_convention() -> None:
    assert Base.metadata.naming_convention == DB_NAMING_CONVENTION


async def test_db_session_commit_is_explicit_and_uncommitted_changes_roll_back(
    database_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency = get_args(database.DBSession)[1]
    assert dependency.dependency is database.get_db_session
    assert dependency.scope == "function"

    session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionFactory", session_factory)
    table = Table("template_test_item", MetaData(), Column("id", Integer, primary_key=True))

    try:
        async with database_engine.begin() as connection:
            await connection.run_sync(table.metadata.create_all)

        dependency_context = asynccontextmanager(database.get_db_session)
        async with dependency_context() as session:
            assert isinstance(session, AsyncSession)
            await session.execute(insert(table).values(id=1))
            await session.commit()

        async with dependency_context() as session:
            await session.execute(insert(table).values(id=2))

        with pytest.raises(RuntimeError, match="rollback"):
            async with dependency_context() as session:
                await session.execute(insert(table).values(id=3))
                raise RuntimeError("rollback")

        async with session_factory() as session:
            result = await session.execute(select(table))
            assert [dict(row) for row in result.mappings()] == [{"id": 1}]
    finally:
        async with database_engine.begin() as connection:
            await connection.run_sync(table.metadata.drop_all)


async def test_database_enforces_foreign_keys(database_engine: AsyncEngine) -> None:
    metadata = MetaData()
    parent = Table("template_test_parent", metadata, Column("id", Integer, primary_key=True))
    child = Table(
        "template_test_child",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey(parent.c.id), nullable=False),
    )

    try:
        async with database_engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            await connection.execute(insert(parent).values(id=1))
            await connection.execute(insert(child).values(id=1, parent_id=1))

        with pytest.raises(IntegrityError):
            async with database_engine.begin() as connection:
                await connection.execute(insert(child).values(id=2, parent_id=999))
    finally:
        async with database_engine.begin() as connection:
            await connection.run_sync(metadata.drop_all)


async def test_sqlite_enables_foreign_keys_on_every_connection(tmp_path: Path) -> None:
    engine = database.create_database_engine(
        Config(
            DATABASE_ASYNC_URL=f"sqlite+aiosqlite:///{tmp_path / '数据库 with spaces.db'}",
            ENVIRONMENT=Environment.TESTING,
        )
    )
    try:
        async with engine.connect() as first, engine.connect() as second:
            assert await first.scalar(text("PRAGMA foreign_keys")) == 1
            assert await second.scalar(text("PRAGMA foreign_keys")) == 1
        assert (tmp_path / "数据库 with spaces.db").is_file()
    finally:
        await engine.dispose()
