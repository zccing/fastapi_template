"""数据库命名约定和运行环境枚举。"""

from enum import StrEnum
from typing import Final

# 统一数据库索引、约束和外键的名称，便于迁移文件和故障排查保持一致。
DB_NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}


class Environment(StrEnum):
    """应用支持的运行环境。

    ``LOCAL``、``TESTING`` 和 ``STAGING`` 保留 OpenAPI；生产环境关闭文档。
    这些选项不启用 FastAPI 的异常调试页面。
    """

    LOCAL = "LOCAL"
    TESTING = "TESTING"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"

    @property
    def is_debug(self) -> bool:
        """判断当前环境是否保留 OpenAPI 文档。

        Returns:
            如果当前环境是本地、测试或预发布环境，则返回 ``True``。
        """

        return self in (Environment.LOCAL, Environment.STAGING, Environment.TESTING)

    @property
    def is_testing(self) -> bool:
        """判断当前环境是否为自动化测试环境。

        Returns:
            当前环境为 ``TESTING`` 时返回 ``True``。
        """

        return self == Environment.TESTING

    @property
    def is_deployed(self) -> bool:
        """判断当前环境是否属于部署环境。

        Returns:
            当前环境为预发布或生产环境时返回 ``True``。
        """

        return self in (Environment.STAGING, Environment.PRODUCTION)
