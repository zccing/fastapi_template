import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import get_args

import httpx
import pytest
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import Column, Integer, MetaData, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import src.database as database
from src.config import Config, settings
from src.constants import DB_NAMING_CONVENTION, Environment
from src.exceptions import NotFound
from src.main import app
from src.models import Base
from src.schemas import CustomModel, datetime_to_utc_str


def test_env_example_documents_every_setting() -> None:
    example_path = Path(__file__).parents[1] / ".env.example"
    example = example_path.read_text(encoding="utf-8")
    documented = set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", example, re.MULTILINE))

    assert documented == set(Config.model_fields)


@pytest.mark.parametrize(
    ("environment", "origins", "allow_credentials", "origin_regex", "message"),
    [
        (Environment.TESTING, ("*",), True, None, "Wildcard CORS"),
        (Environment.PRODUCTION, ("*",), False, None, "Wildcard CORS"),
        (Environment.PRODUCTION, (), False, "https://.*", "CORS_ORIGINS_REGEX"),
    ],
    ids=("credentials", "deployed-wildcard", "deployed-regex"),
)
def test_config_rejects_invalid_cors(
    environment: Environment,
    origins: tuple[str, ...],
    allow_credentials: bool,
    origin_regex: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Config(
            DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
            ENVIRONMENT=environment,
            SENTRY_DSN="https://public@example.ingest.sentry.io/1",
            CORS_ORIGINS=origins,
            CORS_ALLOW_CREDENTIALS=allow_credentials,
            CORS_ORIGINS_REGEX=origin_regex,
        )


def test_deployed_config_allows_sentry_to_be_disabled() -> None:
    config = Config(
        DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
        ENVIRONMENT=Environment.PRODUCTION,
        ROOT_PATH="/gateway/api",
    )

    assert config.SENTRY_DSN is None
    assert config.ROOT_PATH == "/gateway/api"


@pytest.mark.parametrize("root_path", ("v1", "/v1/", "/v1//items", "/v 1"))
def test_config_rejects_invalid_root_path(root_path: str) -> None:
    with pytest.raises(ValidationError, match="ROOT_PATH"):
        Config(
            DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
            ENVIRONMENT=Environment.TESTING,
            ROOT_PATH=root_path,
        )


def test_environment_must_be_selected_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT")

    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        Config(DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL, _env_file=None)


def test_not_found_has_a_resource_detail() -> None:
    exception = NotFound()

    assert (exception.status_code, exception.detail) == (404, "Resource not found")


def test_datetime_serialization_is_utc_and_honors_dump_options() -> None:
    class Example(CustomModel):
        created_at: AwareDatetime
        value: int

    model = Example(
        created_at=datetime.fromisoformat("2026-01-02T03:04:05.123456+08:00"),
        value=1,
    )

    assert datetime_to_utc_str(model.created_at) == "2026-01-01T19:04:05.123456Z"
    assert model.model_dump(mode="json", exclude={"value"}) == {
        "created_at": "2026-01-01T19:04:05.123456Z"
    }

    with pytest.raises(ValueError, match="timezone-aware"):
        datetime_to_utc_str(datetime(2026, 1, 2, 3, 4, 5))

    with pytest.raises(ValidationError, match="timezone"):
        Example(created_at=datetime(2026, 1, 2, 3, 4, 5), value=1)


async def test_healthcheck_allows_configured_origin_only() -> None:
    assert app.version == settings.APP_VERSION
    assert app.root_path == settings.ROOT_PATH

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/healthcheck",
            headers={"Origin": "http://localhost:3000"},
        )
        denied = await client.get(
            "/healthcheck",
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_orm_base_uses_shared_naming_convention() -> None:
    assert Base.metadata.naming_convention == DB_NAMING_CONVENTION


async def test_db_session_commit_is_explicit_and_uncommitted_changes_roll_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency = get_args(database.DBSession)[1]
    assert dependency.dependency is database.get_db_session

    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionFactory", session_factory)
    table = Table("items", MetaData(), Column("id", Integer, primary_key=True))

    try:
        async with test_engine.begin() as connection:
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
        await test_engine.dispose()
