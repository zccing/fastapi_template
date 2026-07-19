import re
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select
from sqlalchemy.ext.asyncio import create_async_engine

import src.database as database
from src.config import Config, settings
from src.constants import Environment
from src.exceptions import NotFound
from src.main import app
from src.schemas import CustomModel, datetime_to_utc_str
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


def test_not_found_has_a_resource_detail() -> None:
    exception = NotFound()

    assert (exception.status_code, exception.detail) == (404, "Resource not found")


def test_datetime_serialization_is_utc_and_honors_dump_options() -> None:
    class Example(CustomModel):
        created_at: datetime
        value: int

    model = Example(
        created_at=datetime.fromisoformat("2026-01-02T03:04:05+08:00"),
        value=1,
    )

    assert datetime_to_utc_str(model.created_at) == "2026-01-01T19:04:05Z"
    assert model.serializable_dict(exclude={"value"}) == {"created_at": "2026-01-01T19:04:05Z"}


def test_random_alphanum_validates_length() -> None:
    value = generate_random_alphanum(32)

    assert len(value) == 32
    assert value.isalnum()

    with pytest.raises(ValueError, match="positive"):
        generate_random_alphanum(0)


async def test_healthcheck_allows_configured_origin_only() -> None:
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


async def test_execute_commits_when_it_owns_the_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(database, "engine", test_engine)
    table = Table("items", MetaData(), Column("id", Integer, primary_key=True))

    try:
        async with test_engine.begin() as connection:
            await connection.run_sync(table.metadata.create_all)

        await database.execute(insert(table).values(id=1))

        assert await database.fetch_all(select(table)) == [{"id": 1}]
    finally:
        await test_engine.dispose()
