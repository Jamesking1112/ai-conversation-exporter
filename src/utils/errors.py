"""对用户安全、可读的异常类型。"""

from __future__ import annotations


class ExporterError(Exception):
    """导出过程的基类异常；消息中不得包含认证信息。"""


class ConfigurationError(ExporterError):
    """config.json 缺失或格式无效。"""


class AuthenticationError(ExporterError):
    """Authorization 或 Cookie 已失效。"""


class RequestFailedError(ExporterError):
    """HTTP 请求在可重试次数用尽后仍失败。"""


class ResponseFormatError(ExporterError):
    """服务端响应无法解析为预期 JSON 结构。"""


class PaginationError(ResponseFormatError):
    """会话分页响应不完整，继续会导致漏导出。"""
