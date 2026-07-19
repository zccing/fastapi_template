"""无领域依赖的通用辅助函数。"""

import secrets
import string
from typing import Final

ALPHA_NUM: Final = string.ascii_letters + string.digits


def generate_random_alphanum(length: int = 20) -> str:
    """生成指定长度的密码学安全字母数字字符串。

    Args:
        length: 结果长度，必须为正整数。

    Returns:
        仅由 ASCII 字母和数字组成的随机字符串。

    Raises:
        ValueError: ``length`` 小于或等于零时抛出。
    """

    if length <= 0:
        raise ValueError("length must be positive")

    return "".join(secrets.choice(ALPHA_NUM) for _ in range(length))
