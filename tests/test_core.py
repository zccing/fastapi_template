import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import cast, get_args

import httpx
import pytest
from pydantic import PostgresDsn, ValidationError
from sqlalchemy import Column, Integer, MetaData, Table, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import src.database as database
from src.config import Config, settings
from src.constants import DB_NAMING_CONVENTION, Environment
from src.exceptions import NotFound
from src.main import app
from src.models import Base
from src.schemas import CustomModel, UTCDateTime, datetime_to_utc_str
from src.utils import generate_random_alphanum


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
        SENTRY_DSN=None,
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


def test_environment_must_be_selected_explicitly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENVIRONMENT")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        Config(DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL)


def test_config_requires_asyncpg_database_url() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Config(
            DATABASE_ASYNC_URL=PostgresDsn("postgresql://app:app@localhost/app"),
            ENVIRONMENT=Environment.TESTING,
        )


def test_config_errors_hide_database_credentials() -> None:
    unsafe_url = cast(PostgresDsn, "postgresql://u:pw123@x/d")

    with pytest.raises(ValidationError) as exc_info:
        Config(
            DATABASE_ASYNC_URL=unsafe_url,
            ENVIRONMENT=Environment.TESTING,
        )

    assert "pw123" not in str(exc_info.value)


@pytest.mark.parametrize("pool_ttl", (0, -1))
def test_database_pool_ttl_must_be_positive(pool_ttl: int) -> None:
    with pytest.raises(ValidationError, match="DATABASE_POOL_TTL"):
        Config(
            DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
            DATABASE_POOL_TTL=pool_ttl,
            ENVIRONMENT=Environment.TESTING,
        )


def test_config_normalizes_cors_origins() -> None:
    config = Config(
        DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
        ENVIRONMENT=Environment.TESTING,
        CORS_ORIGINS=(
            "HTTPS://EXAMPLE.COM/",
            "https://example.com:443",
            "http://[::1]:8000/",
        ),
    )

    assert config.CORS_ORIGINS == ("https://example.com", "http://[::1]:8000")


@pytest.mark.parametrize(
    "origin",
    (
        "not-an-origin",
        "ftp://example.com",
        "https://user:password@example.com",
        "https://example.com/path",
        "https://example.com?query=value",
        "https://example.com#fragment",
    ),
)
def test_config_rejects_invalid_cors_origin(origin: str) -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Config(
            DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
            ENVIRONMENT=Environment.TESTING,
            CORS_ORIGINS=(origin,),
        )


def test_not_found_has_a_resource_detail() -> None:
    exception = NotFound()

    assert (exception.status_code, exception.detail) == (404, "Resource not found")


def test_datetime_serialization_is_utc_and_honors_dump_options() -> None:
    class Example(CustomModel):
        created_at: UTCDateTime
        history: list[UTCDateTime]
        indexed: dict[str, UTCDateTime]
        value: int

    model = Example(
        created_at=datetime.fromisoformat("2026-01-02T03:04:05.123456+08:00"),
        history=[datetime.fromisoformat("2026-01-02T03:04:05+08:00")],
        indexed={"updated": datetime.fromisoformat("2026-01-02T03:04:05.12-05:00")},
        value=1,
    )

    assert datetime_to_utc_str(model.created_at) == "2026-01-01T19:04:05.123456Z"
    assert model.model_dump(mode="json", exclude={"value"}) == {
        "created_at": "2026-01-01T19:04:05.123456Z",
        "history": ["2026-01-01T19:04:05Z"],
        "indexed": {"updated": "2026-01-02T08:04:05.120000Z"},
    }
    schema = Example.model_json_schema(mode="serialization")
    assert schema["properties"]["created_at"]["format"] == "date-time"

    with pytest.raises(ValueError, match="timezone-aware"):
        datetime_to_utc_str(datetime(2026, 1, 2, 3, 4, 5))

    with pytest.raises(ValidationError, match="timezone"):
        Example(
            created_at=datetime(2026, 1, 2, 3, 4, 5),
            history=[],
            indexed={},
            value=1,
        )


def test_custom_model_does_not_implicitly_normalize_datetime() -> None:
    class Example(CustomModel):
        created_at: datetime

    model = Example(created_at=datetime.fromisoformat("2026-01-02T03:04:05+08:00"))

    assert model.model_dump(mode="json") == {"created_at": "2026-01-02T03:04:05+08:00"}


def test_random_alphanum_validates_length() -> None:
    value = generate_random_alphanum(32)

    assert len(value) == 32
    assert value.isalnum()

    with pytest.raises(ValueError, match="positive"):
        generate_random_alphanum(0)


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


async def test_cors_allows_head_preflight() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/healthcheck",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "HEAD",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "HEAD" in response.headers["access-control-allow-methods"]


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
