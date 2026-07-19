"""应用层 HTTP 异常定义。

异常类只描述客户端可见的状态码、消息和认证响应头；底层异常不应直接暴露给
客户端，路由或全局异常处理器应在边界处记录内部细节并返回安全消息。
"""

from collections.abc import Mapping

from fastapi import HTTPException, status


class DetailedHTTPException(HTTPException):
    """带有可覆写默认状态码和消息的 HTTP 异常基类。

    Attributes:
        STATUS_CODE: 子类默认返回的 HTTP 状态码。
        DETAIL: 子类默认返回的客户端消息。
    """

    STATUS_CODE = status.HTTP_500_INTERNAL_SERVER_ERROR
    DETAIL = "Server error"

    def __init__(
        self,
        *,
        detail: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """创建异常。

        Args:
            detail: 可选的本次异常消息；未提供时使用类级默认消息。
            headers: 可选的响应头映射，例如认证挑战头。
        """

        super().__init__(
            status_code=self.STATUS_CODE,
            detail=self.DETAIL if detail is None else detail,
            headers=None if headers is None else dict(headers),
        )


class PermissionDenied(DetailedHTTPException):
    """请求者已识别，但没有执行当前操作的权限。"""

    STATUS_CODE = status.HTTP_403_FORBIDDEN
    DETAIL = "Permission denied"


class NotFound(DetailedHTTPException):
    """请求的资源不存在。"""

    STATUS_CODE = status.HTTP_404_NOT_FOUND
    DETAIL = "Resource not found"


class BadRequest(DetailedHTTPException):
    """请求参数或请求状态不符合接口要求。"""

    STATUS_CODE = status.HTTP_400_BAD_REQUEST
    DETAIL = "Bad request"


class NotAuthenticated(DetailedHTTPException):
    """请求未提供有效的身份凭据。"""

    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = "User not authenticated"

    def __init__(self) -> None:
        """创建带 Bearer 认证挑战头的 401 异常。"""

        super().__init__(headers={"WWW-Authenticate": "Bearer"})
