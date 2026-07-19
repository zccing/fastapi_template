"""Pydantic 模型基础类和统一时间序列化规则。"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


def datetime_to_utc_str(value: datetime) -> str:
    """将时间转换为带 ``Z`` 后缀的 ISO-8601 UTC 字符串。

    Args:
        value: 待序列化的带时区时间。

    Returns:
        保留原始精度的 ISO-8601 UTC 时间字符串。

    Raises:
        ValueError: 时间没有明确时区时抛出。
    """

    if value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class CustomModel(BaseModel):
    """应用响应模型的共享 Pydantic 配置。

    所有直接出现的 ``datetime`` 字段在 JSON 模式下统一转换为 UTC 字符串，
    同时允许调用方使用字段别名进行输入校验。
    """

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetime(self, value: Any) -> Any:
        """序列化字段中的直接 datetime 值。

        Args:
            value: Pydantic 当前传入的字段值。

        Returns:
            datetime 对应的 UTC 字符串，或未处理的原始值。
        """

        if isinstance(value, datetime):
            return datetime_to_utc_str(value)
        return value
