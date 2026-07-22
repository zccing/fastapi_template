"""测试环境的统一配置。

测试进程使用本地虚拟配置，避免依赖开发机上的真实数据库或外部服务环境。
"""

import os
from typing import Final

import pytest

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
