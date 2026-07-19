"""测试环境的统一配置。

测试进程使用本地虚拟配置，避免依赖开发机上的真实数据库或外部服务环境。
"""

import os

os.environ.update(
    {
        "DATABASE_ASYNC_URL": "postgresql+asyncpg://app:app@localhost:5432/app",
        "ENVIRONMENT": "TESTING",
        "CORS_ORIGINS": '["http://localhost:3000"]',
        "CORS_HEADERS": '["Content-Type", "Authorization", "X-API-Key"]',
        "CORS_ALLOW_CREDENTIALS": "false",
    }
)
