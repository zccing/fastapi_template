"""应用运行时配置。

配置值按 Pydantic Settings 的优先级从环境变量和项目根目录的 ``.env`` 文件加载，
并在应用启动前完成格式、部署和安全边界校验。
"""

import re
from typing import Any, Self

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.constants import Environment


class CustomBaseSettings(BaseSettings):
    """应用设置模型的共享基础配置。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class Config(CustomBaseSettings):
    """应用级配置模型。

    Attributes:
        DATABASE_ASYNC_URL: 供应用和异步迁移工具使用的 PostgreSQL 连接地址。
        DATABASE_POOL_SIZE: 连接池允许维持的最大连接数。
        DATABASE_POOL_TTL: 连接回收时间，单位为秒。
        DATABASE_POOL_PRE_PING: 是否在取出连接前检查连接可用性。
        ENVIRONMENT: 当前运行环境。
        SENTRY_DSN: 部署环境的 Sentry 数据源地址。
        CORS_ORIGINS: 允许跨域访问的明确 Origin 序列。
        CORS_ORIGINS_REGEX: 仅用于非部署环境的跨域 Origin 正则表达式。
        CORS_HEADERS: 允许浏览器跨域发送的请求头序列。
        CORS_ALLOW_CREDENTIALS: 是否允许浏览器携带 Cookie 等凭据。
        APP_VERSION: 应用版本号，用于部署时生成根路径。
    """

    # `...` 让字段在运行时保持必填，同时避免 Pylance 误判 Settings 构造函数参数。
    DATABASE_ASYNC_URL: PostgresDsn = Field(default=...)
    DATABASE_POOL_SIZE: int = Field(default=16, ge=1, le=256)
    DATABASE_POOL_TTL: int = Field(default=60 * 20, ge=0)  # 连接池回收时间（20 分钟）。
    DATABASE_POOL_PRE_PING: bool = True

    ENVIRONMENT: Environment = Environment.PRODUCTION

    SENTRY_DSN: str | None = None

    CORS_ORIGINS: tuple[str, ...] = ()
    CORS_ORIGINS_REGEX: str | None = None
    CORS_HEADERS: tuple[str, ...] = (
        "Content-Type",
        "Authorization",
        "X-API-Key",
    )
    CORS_ALLOW_CREDENTIALS: bool = False

    APP_VERSION: str = Field(default="1", min_length=1)

    @model_validator(mode="after")
    def validate_runtime_config(self) -> Self:
        """校验部署要求和跨字段安全约束。

        Returns:
            校验通过后的当前配置对象。

        Raises:
            ValueError: Sentry、CORS 或正则配置不满足当前环境的安全要求时抛出。
        """

        if self.ENVIRONMENT.is_deployed and not self.SENTRY_DSN:
            raise ValueError("Sentry is not set")

        if "*" in self.CORS_ORIGINS and self.CORS_ALLOW_CREDENTIALS:
            raise ValueError("Wildcard CORS cannot be used with credentials")

        if self.ENVIRONMENT.is_deployed and "*" in self.CORS_ORIGINS:
            raise ValueError("Wildcard CORS is not allowed in deployed environments")

        if self.CORS_ORIGINS_REGEX:
            try:
                re.compile(self.CORS_ORIGINS_REGEX)
            except re.error as exc:
                raise ValueError("CORS_ORIGINS_REGEX is invalid") from exc

            if self.ENVIRONMENT.is_deployed:
                raise ValueError("CORS_ORIGINS_REGEX is not allowed in deployed environments")

        return self


settings = Config()

app_configs: dict[str, Any] = {"title": "App API"}
if settings.ENVIRONMENT.is_deployed:
    app_configs["root_path"] = f"/v{settings.APP_VERSION}"

if not settings.ENVIRONMENT.is_debug:
    app_configs["openapi_url"] = None  # 部署环境隐藏 OpenAPI 文档。
