"""DeepSeek 会话导出器。

这里刻意沿用原脚本已经验证成功的两个接口和分页顺序；本模块只负责把
它们包装成可测试、可重试、不会泄露登录凭据的工程化实现。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from src.models import Conversation
from src.utils.config import DeepSeekConfig
from src.utils.errors import (
    AuthenticationError,
    ExporterError,
    PaginationError,
    ResponseFormatError,
)
from src.utils.http import RetryingHttpClient


BASE_URL = "https://chat.deepseek.com"
FETCH_PAGE_PATH = "/api/v0/chat_session/fetch_page"
HISTORY_MESSAGES_PATH = "/api/v0/chat/history_messages"

# 除 Authorization 与 Cookie 外，以下字段均来自原有已验证脚本。
FIXED_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Referer": "https://chat.deepseek.com/",
    "x-client-bundle-id": "com.deepseek.chat",
    "x-client-platform": "web",
    "x-client-version": "2.4.0",
    "x-client-locale": "zh_CN",
}


@dataclass(slots=True)
class ExportIssue:
    """一条可写入 export_errors.json 的脱敏错误记录。"""

    stage: str
    conversation_id: str | None
    title: str | None
    message: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "stage": self.stage,
            "conversation_id": self.conversation_id,
            "title": self.title,
            "message": self.message,
        }


@dataclass(slots=True)
class ExportResult:
    conversations: list[Conversation] = field(default_factory=list)
    issues: list[ExportIssue] = field(default_factory=list)


class DeepSeekExporter:
    """按原脚本的 API 调用顺序导出所有 DeepSeek 会话。"""

    def __init__(
        self,
        config: DeepSeekConfig,
        http_client: RetryingHttpClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        progress: Callable[[str], None] = print,
    ) -> None:
        self._config = config
        self._http = http_client
        self._sleep = sleep
        self._progress = progress

    @property
    def headers(self) -> dict[str, str]:
        """按请求构造请求头，避免把登录信息保存在源码常量中。"""
        return {
            **FIXED_HEADERS,
            "Authorization": self._config.authorization,
            "Cookie": self._config.cookie,
        }

    @staticmethod
    def _json(response: Any, context: str) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except (ValueError, TypeError) as error:
            raise ResponseFormatError(f"{context} 返回的不是合法 JSON。") from error
        if not isinstance(payload, Mapping):
            raise ResponseFormatError(f"{context} 返回结构异常。")
        return payload

    def fetch_all_sessions(self) -> list[dict[str, Any]]:
        """使用原脚本的 lte_cursor 分页方式获取全部 session。"""
        self._progress("\n开始获取聊天列表")
        self._progress("=" * 30)

        sessions: list[dict[str, Any]] = []
        cursor: Any = None

        while True:
            params = {"lte_cursor.pinned": "false"}
            if cursor:
                params["lte_cursor.updated_at"] = str(cursor)

            response = self._http.get(
                BASE_URL + FETCH_PAGE_PATH,
                headers=self.headers,
                params=params,
            )
            payload = self._json(response, "聊天列表接口")
            data = payload.get("data")
            if not isinstance(data, Mapping):
                raise PaginationError("聊天列表返回异常，无法继续分页。")
            business_data = data.get("biz_data")
            if not isinstance(business_data, Mapping):
                raise PaginationError("聊天列表缺少 biz_data，无法继续分页。")
            page = business_data.get("chat_sessions")
            if not isinstance(page, list) or not all(isinstance(item, Mapping) for item in page):
                raise PaginationError("聊天列表缺少 chat_sessions，无法继续分页。")

            normalized_page = [dict(item) for item in page]
            self._progress(f"本页: {len(normalized_page)}")
            sessions.extend(normalized_page)

            if not business_data.get("has_more"):
                break
            if not normalized_page:
                raise PaginationError("聊天列表仍有下一页但当前页为空，已停止以避免漏导出。")

            new_cursor = normalized_page[-1].get("updated_at")
            if not new_cursor:
                raise PaginationError("聊天列表缺少 updated_at 游标，无法继续分页。")
            if new_cursor == cursor:
                self._progress("cursor 重复停止")
                break

            cursor = new_cursor
            self._sleep(0.5)

        self._progress(f"聊天总数: {len(sessions)}")
        return sessions

    def fetch_history(self, chat_id: str) -> Any:
        """获取单个会话详情，保留旧脚本中 urlencode 后拼接查询参数的方式。"""
        query = urlencode({"chat_session_id": chat_id})
        url = f"{BASE_URL}{HISTORY_MESSAGES_PATH}?{query}"
        response = self._http.get(url, headers=self.headers)
        payload = self._json(response, "聊天详情接口")
        if "data" not in payload or payload.get("data") is None:
            raise ResponseFormatError("聊天详情返回异常，缺少 data。")
        return payload["data"]

    def export_conversations(self) -> ExportResult:
        """获取全部会话；单条详情失败会记录后继续下一条。"""
        sessions = self.fetch_all_sessions()
        result = ExportResult()
        self._progress("\n开始下载聊天内容...")

        for index, session in enumerate(sessions, start=1):
            fallback_id = f"deepseek-session-{index}"
            raw_id = session.get("id") or session.get("chat_session_id")
            conversation_id = str(raw_id) if raw_id is not None else fallback_id
            raw_title = session.get("title")
            title = None if raw_title is None else str(raw_title)
            self._progress(f"{index}/{len(sessions)} {title or '无标题聊天'}")

            try:
                if raw_id is None or not str(raw_id):
                    raise ResponseFormatError("聊天列表中的 session 缺少 id。")
                history = self.fetch_history(str(raw_id))
                result.conversations.append(
                    Conversation.from_deepseek(session, history, fallback_id=fallback_id)
                )
            except AuthenticationError:
                # 认证问题是全局问题，继续请求只会扩大无效请求。
                raise
            except ExporterError as error:
                result.conversations.append(
                    Conversation.failed_from_deepseek(session, fallback_id=fallback_id)
                )
                result.issues.append(
                    ExportIssue(
                        stage="history_messages",
                        conversation_id=conversation_id,
                        title=title,
                        message=str(error),
                    )
                )
                self._progress(f"  详情失败，已跳过并继续：{error}")
            except Exception:
                # 未预料的单条解析问题也不能打断整批导出，且不回显原始响应。
                result.conversations.append(
                    Conversation.failed_from_deepseek(session, fallback_id=fallback_id)
                )
                result.issues.append(
                    ExportIssue(
                        stage="history_messages",
                        conversation_id=conversation_id,
                        title=title,
                        message="聊天详情解析发生未知错误，已跳过该会话。",
                    )
                )
                self._progress("  详情解析失败，已跳过并继续。")

            # 与旧脚本一致：每个会话详情请求后均暂停 0.3 秒。
            self._sleep(0.3)

        return result
