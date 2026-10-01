"""测试环境的统一配置。

测试进程使用本地虚拟配置，避免依赖开发机上的真实数据库或外部服务环境。
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

TEST_ENVIRONMENT: Final[dict[str, str]] = {
    "DATABASE_ASYNC_URL": "postgresql+asyncpg://app:app@localhost:5432/app",
    "DATABASE_POOL_SIZE": "16",
    "DATABASE_POOL_TTL": "1200",
    "DATABASE_POOL_PRE_PING": "true",
    "ENVIRONMENT": "TESTING",
    "SENTRY_DSN": "",
    "CORS_ORIGINS": '["http://localhost:3000"]',
    "CORS_ORIGINS_REGEX": "",
    "CORS_HEADERS": '["Content-Type", "Authorization", "X-API-Key"]',
    "CORS_ALLOW_CREDENTIALS": "false",
    "APP_VERSION": "0.1.0-test",
    "ROOT_PATH": "",
}
os.environ.update(TEST_ENVIRONMENT)


def pytest_configure(config: pytest.Config) -> None:
    """确保新增应用配置时必须同步提供隔离的测试值。"""

    del config
    from src.config import Config

    if set(TEST_ENVIRONMENT) != set(Config.model_fields):
        raise pytest.UsageError("TEST_ENVIRONMENT must override every Config field")


@pytest.fixture(params=("sqlite", "postgres"))
async def database_engine(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[AsyncEngine]:
    """使用应用引擎配置验证两个后端；PostgreSQL 只使用显式指定的测试库。"""

    from src.config import Config
    from src.constants import Environment
    from src.database import create_database_engine

    if request.param == "postgres":
        database_url = os.environ.get("TEST_POSTGRES_URL")
        if not database_url:
            pytest.skip("Set TEST_POSTGRES_URL to a disposable PostgreSQL database")
        if not database_url.startswith("postgresql+asyncpg://"):
            raise pytest.UsageError("TEST_POSTGRES_URL must use postgresql+asyncpg")
    else:
        database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"

    engine = create_database_engine(
        Config(DATABASE_ASYNC_URL=database_url, ENVIRONMENT=Environment.TESTING)
    )
    try:
        yield engine
    finally:
        await engine.dispose()
