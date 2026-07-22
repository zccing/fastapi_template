"""Pydantic 模型基础类和显式 UTC 时间类型。"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, PlainSerializer, WithJsonSchema


def datetime_to_utc_str(value: datetime) -> str:
    """将时间转换为带 ``Z`` 后缀的 ISO-8601 UTC 字符串。

    Args:
        value: 待序列化的带时区时间。

    Returns:
        不截断微秒值的 ISO-8601 UTC 时间字符串。

    Raises:
        ValueError: 时间没有明确时区时抛出。
    """

    if value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[
    AwareDatetime,
    PlainSerializer(datetime_to_utc_str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}, mode="serialization"),
]
"""必须携带时区，并在 JSON 中序列化为 UTC ``Z`` 格式的时间类型。"""


class CustomModel(BaseModel):
    """允许字段名和别名输入的应用共享 Pydantic 模型。"""

    model_config = ConfigDict(
        validate_by_name=True,
        validate_by_alias=True,
    )
