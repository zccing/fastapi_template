import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Config, settings
from src.constants import Environment


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


def test_sentry_dsn_is_optional_and_validated() -> None:
    assert settings.SENTRY_DSN is None

    config = Config.model_validate(
        {
            "DATABASE_ASYNC_URL": settings.DATABASE_ASYNC_URL,
            "ENVIRONMENT": Environment.TESTING,
            "SENTRY_DSN": "https://public@example.ingest.sentry.io/1",
        }
    )
    assert str(config.SENTRY_DSN) == "https://public@example.ingest.sentry.io/1"

    with pytest.raises(ValidationError, match="SENTRY_DSN"):
        Config.model_validate(
            {
                "DATABASE_ASYNC_URL": settings.DATABASE_ASYNC_URL,
                "ENVIRONMENT": Environment.TESTING,
                "SENTRY_DSN": "not-a-url",
            }
        )


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
        Config(  # pyright: ignore[reportCallIssue]
            DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL
        )


def test_config_accepts_file_sqlite_url_in_production() -> None:
    config = Config(
        DATABASE_ASYNC_URL="sqlite+aiosqlite:///./db.sqlite3",
        ENVIRONMENT=Environment.PRODUCTION,
    )

    assert config.DATABASE_ASYNC_URL == "sqlite+aiosqlite:///./db.sqlite3"


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://app:app@localhost/app",
        "sqlite:///./db.sqlite3",
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite://localhost/db.sqlite3",
        "sqlite+aiosqlite:///./db.sqlite3?mode=ro",
        "sqlite+aiosqlite:///./db.sqlite3?",
        "sqlite+aiosqlite:///./db.sqlite3#fragment",
        "sqlite+aiosqlite://user:password@/db.sqlite3",
        "sqlite+aiosqlite:///",
        "postgresql+asyncpg:///app",
        "postgresql+asyncpg://localhost:not-a-port/app",
        "postgresql+asyncpg://localhost:65536/app",
        "not-a-url",
    ),
)
def test_config_rejects_unsupported_database_url(database_url: str) -> None:
    with pytest.raises(ValidationError, match="DATABASE_ASYNC_URL"):
        Config(
            DATABASE_ASYNC_URL=database_url,
            ENVIRONMENT=Environment.TESTING,
        )


def test_config_errors_hide_database_credentials() -> None:
    unsafe_url = "postgresql://u:pw123@x/d"

    with pytest.raises(ValidationError) as exc_info:
        Config(
            DATABASE_ASYNC_URL=unsafe_url,
            ENVIRONMENT=Environment.TESTING,
        )

    assert "pw123" not in str(exc_info.value)


def test_config_repr_hides_connection_secrets() -> None:
    config = Config(
        DATABASE_ASYNC_URL="postgresql+asyncpg://user:example-only@localhost/app",
        ENVIRONMENT=Environment.TESTING,
        SENTRY_DSN="https://example-key@example.invalid/1",  # pyright: ignore[reportArgumentType]
    )

    assert "example-only" not in repr(config)
    assert "example-key" not in repr(config)


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


@pytest.mark.parametrize(
    "database_url",
    (
        "sqlite+aiosqlite:///../data/app.db",
        "sqlite+aiosqlite:///./my data.db",
        "sqlite+aiosqlite:////tmp/link/../app.db",
        "sqlite+aiosqlite:///./数据库.db",
        "postgresql+asyncpg://app:sample%40value@localhost/app",
    ),
)
def test_database_url_preserves_driver_path(database_url: str) -> None:
    config = Config(
        DATABASE_ASYNC_URL=database_url,
        ENVIRONMENT=Environment.TESTING,
    )

    assert str(config.DATABASE_ASYNC_URL) == database_url


def test_empty_environment_values_override_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "SENTRY_DSN=https://public@example.invalid/1\n"
        "ROOT_PATH=/local-only\n"
        "CORS_ORIGINS_REGEX=^https://local.invalid$\n",
        encoding="utf-8",
    )
    for field in ("SENTRY_DSN", "ROOT_PATH", "CORS_ORIGINS_REGEX"):
        monkeypatch.setenv(field, "")

    config = Config(
        DATABASE_ASYNC_URL=settings.DATABASE_ASYNC_URL,
        ENVIRONMENT=Environment.TESTING,
    )

    assert config.SENTRY_DSN is None
    assert config.ROOT_PATH == ""
    assert config.CORS_ORIGINS_REGEX is None


@pytest.mark.parametrize("field", ("ENVIRONMENT", "DATABASE_ASYNC_URL", "DATABASE_POOL_SIZE"))
def test_empty_required_or_numeric_setting_does_not_fall_back(
    field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ENVIRONMENT=LOCAL\n"
        "DATABASE_ASYNC_URL=sqlite+aiosqlite:///local.db\n"
        "DATABASE_POOL_SIZE=16\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(field, "")

    with pytest.raises(ValidationError, match=field):
        Config()  # pyright: ignore[reportCallIssue]
