"""FastAPI 应用入口和基础中间件配置。

当前骨架只提供不依赖数据库查询的存活检查；业务路由在领域模块完成后，通过
应用入口统一挂载。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.config import app_configs, settings
from src.database import close_database


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
    """管理应用生命周期内的数据库连接池。

    Args:
        _application: 当前 FastAPI 应用实例，保留该参数以符合生命周期接口。

    Yields:
        应用运行期间不携带额外值的生命周期标记。
    """

    try:
        yield
    finally:
        await close_database()


if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT.value,
    )

app = FastAPI(**app_configs, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGINS_REGEX,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
    allow_headers=settings.CORS_HEADERS,
)


@app.get("/healthcheck", include_in_schema=False)
async def healthcheck() -> dict[str, str]:
    """返回进程存活状态，不主动访问数据库或第三方服务。

    Returns:
        包含 ``status=ok`` 的健康检查响应。
    """

    return {"status": "ok"}
