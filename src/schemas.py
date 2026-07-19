"""Pydantic 模型基础类和统一时间序列化规则。"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


def datetime_to_utc_str(value: datetime) -> str:
    """将时间转换为带 ``Z`` 后缀的 ISO-8601 UTC 字符串。

    Args:
        value: 待序列化的时间。无时区时间按 UTC 解释；有时区时间先转换为 UTC。

    Returns:
        精确到秒的 ISO-8601 UTC 时间字符串。
    """

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)

    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


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

    def serializable_dict(self, **kwargs: Any) -> dict[str, Any]:
        """返回可直接编码为 JSON 的模型字典。

        Args:
            **kwargs: 传递给 ``model_dump`` 的过滤和别名选项，例如 ``exclude``。

        Returns:
            已完成 JSON 类型转换的字典。
        """

        return self.model_dump(mode="json", **kwargs)
