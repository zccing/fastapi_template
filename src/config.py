"""应用运行时配置。

配置值按 Pydantic Settings 的优先级从环境变量和项目根目录的 ``.env`` 文件加载，
并在应用启动前完成格式、部署和安全边界校验。
"""

import re
from typing import Annotated, Any, Self

from pydantic import (
    AnyHttpUrl,
    BeforeValidator,
    Field,
    PostgresDsn,
    UrlConstraints,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.constants import Environment


class CustomBaseSettings(BaseSettings):
    """应用设置模型的共享基础配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )


class Config(CustomBaseSettings):
    """应用级配置模型。

    Attributes:
        DATABASE_ASYNC_URL: 供应用和异步迁移工具使用的 asyncpg 连接地址。
        DATABASE_POOL_SIZE: 连接池常驻连接数，不包含 SQLAlchemy 的临时溢出连接。
        DATABASE_POOL_TTL: 连接回收时间，单位为秒。
        DATABASE_POOL_PRE_PING: 是否在取出连接前检查连接可用性。
        ENVIRONMENT: 当前运行环境。
        SENTRY_DSN: 可选的 Sentry 数据源地址。
        CORS_ORIGINS: 允许跨域访问的明确 Origin 序列。
        CORS_ORIGINS_REGEX: 仅用于非部署环境的跨域 Origin 正则表达式。
        CORS_HEADERS: 允许浏览器跨域发送的请求头序列。
        CORS_ALLOW_CREDENTIALS: 是否允许浏览器携带 Cookie 等凭据。
        APP_VERSION: OpenAPI 展示的应用版本号。
        ROOT_PATH: 反向代理剥离的应用挂载前缀。
    """

    # `...` 让字段在运行时保持必填，同时避免 Pylance 误判 Settings 构造函数参数。
    # 先还原为字符串，避免已构造的 PostgresDsn 实例跳过 scheme 约束。
    DATABASE_ASYNC_URL: Annotated[
        PostgresDsn,
        UrlConstraints(allowed_schemes=["postgresql+asyncpg"]),
        BeforeValidator(str),
    ] = Field(default=...)
    DATABASE_POOL_SIZE: int = Field(default=16, ge=1, le=256)
    DATABASE_POOL_TTL: int = Field(default=60 * 20, ge=1)  # 连接池回收时间（20 分钟）。
    DATABASE_POOL_PRE_PING: bool = True

    ENVIRONMENT: Environment = Field(default=...)

    SENTRY_DSN: str | None = None

    CORS_ORIGINS: tuple[str, ...] = ()
    CORS_ORIGINS_REGEX: str | None = None
    CORS_HEADERS: tuple[str, ...] = (
        "Content-Type",
        "Authorization",
        "X-API-Key",
    )
    CORS_ALLOW_CREDENTIALS: bool = False

    APP_VERSION: str = Field(default="0.1.0", min_length=1)
    ROOT_PATH: str = Field(default="", pattern=r"^$|^/[^/\s]+(?:/[^/\s]+)*$")

    @field_validator("CORS_ORIGINS")
    @classmethod
    def normalize_cors_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        """校验并规范化浏览器 Origin 白名单。"""

        normalized: list[str] = []
        for origin in origins:
            if origin == "*":
                normalized.append(origin)
                continue

            url = AnyHttpUrl(origin)
            if (
                url.username is not None
                or url.password is not None
                or url.path != "/"
                or url.query is not None
                or url.fragment is not None
            ):
                raise ValueError("CORS origin must contain only scheme, host, and optional port")

            normalized.append(str(url).removesuffix("/"))

        return tuple(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_runtime_config(self) -> Self:
        """校验部署要求和跨字段安全约束。

        Returns:
            校验通过后的当前配置对象。

        Raises:
            ValueError: CORS 或正则配置不满足当前环境的安全要求时抛出。
        """

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

app_configs: dict[str, Any] = {
    "title": "App API",
    "version": settings.APP_VERSION,
}
if settings.ROOT_PATH:
    app_configs["root_path"] = settings.ROOT_PATH

if not settings.ENVIRONMENT.is_debug:
    app_configs["openapi_url"] = None  # 生产环境隐藏 OpenAPI 文档。
