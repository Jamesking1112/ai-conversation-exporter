"""跨平台会话导出的统一数据模型。

该模块只使用 Python 标准库。DeepSeek 的原始字段会保留在 ``source`` 中，
这样在模型标准化的同时不会丢掉以后可能有用的平台信息。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def _optional_string(value: Any) -> str | None:
    """把可选标识符规范为字符串，空值保持为 ``None``。"""
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _text_from_value(value: Any) -> str:
    """从常见的 API 文本字段中提取可展示文本。

    DeepSeek 当前成功脚本使用的是 ``fragments[*].content``。对于没有
    fragments 的消息，这个小回退让简单 ``content`` 字段也能正常导出，
    但不会递归扫描整条消息，避免把元数据误写进 Markdown。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for key in ("content", "text", "value"):
            if key in value:
                return _text_from_value(value[key])
        return ""
    if isinstance(value, list):
        return "".join(_text_from_value(item) for item in value)
    return str(value)


def extract_history_messages(history_data: Any) -> list[dict[str, Any]]:
    """从 DeepSeek history 返回值中取得消息数组。

    已有脚本会直接保存 API ``data`` 字段；通常它是列表。为了让导入与
    不同批次的历史返回更稳健，也兼容几个常见的容器字段。
    """
    if isinstance(history_data, list):
        return [item for item in history_data if isinstance(item, dict)]

    if not isinstance(history_data, Mapping):
        return []

    for key in ("messages", "chat_messages", "history", "data"):
        value = history_data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, Mapping):
            return [dict(value)]

    return []


@dataclass(slots=True)
class Message:
    """一条标准化消息。"""

    id: str | None
    role: str
    content: str
    created_at: Any = None
    source: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_deepseek(cls, raw_message: Mapping[str, Any]) -> "Message":
        """把一条 DeepSeek 原始消息转换为标准消息。"""
        fragments = raw_message.get("fragments")
        if isinstance(fragments, list):
            content = "".join(
                _text_from_value(fragment.get("content"))
                for fragment in fragments
                if isinstance(fragment, Mapping)
            )
        else:
            content = _text_from_value(raw_message.get("content"))

        role_value = raw_message.get("role", "unknown")
        role_text = str(role_value).lower() if role_value is not None else "unknown"
        role_map = {
            "user": "user",
            "assistant": "assistant",
            "system": "system",
        }

        return cls(
            id=_optional_string(raw_message.get("id") or raw_message.get("message_id")),
            role=role_map.get(role_text, role_text or "unknown"),
            content=content,
            created_at=raw_message.get("created_at"),
            source=dict(raw_message),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Conversation:
    """一个可被不同 AI 平台共用的会话。"""

    id: str
    provider: str
    title: str | None
    created_at: Any = None
    updated_at: Any = None
    messages: list[Message] = field(default_factory=list)
    export_status: str = "complete"
    source: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_deepseek(
        cls,
        session: Mapping[str, Any],
        history_data: Any,
        *,
        fallback_id: str,
    ) -> "Conversation":
        """由 DeepSeek session 和 history 数据构造一条完整会话。"""
        raw_messages = extract_history_messages(history_data)
        messages = [Message.from_deepseek(item) for item in raw_messages]
        raw_id = session.get("id") or session.get("chat_session_id") or fallback_id
        raw_title = session.get("title")

        return cls(
            id=str(raw_id),
            provider="deepseek",
            title=None if raw_title is None else str(raw_title),
            created_at=session.get("created_at"),
            updated_at=session.get("updated_at"),
            messages=messages,
            source={"session": dict(session)},
        )

    @classmethod
    def failed_from_deepseek(
        cls,
        session: Mapping[str, Any],
        *,
        fallback_id: str,
    ) -> "Conversation":
        """为详情下载失败的 session 保留一条可追踪的标准会话。"""
        raw_id = session.get("id") or session.get("chat_session_id") or fallback_id
        raw_title = session.get("title")
        return cls(
            id=str(raw_id),
            provider="deepseek",
            title=None if raw_title is None else str(raw_title),
            created_at=session.get("created_at"),
            updated_at=session.get("updated_at"),
            messages=[],
            export_status="failed",
            source={"session": dict(session)},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExportDocument:
    """写入 ``deepseek_conversations.json`` 的根对象。"""

    conversations: list[Conversation]
    schema_version: str = "0.1"
    provider: str = "deepseek"
    exported_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "exported_at": self.exported_at,
            "conversations": [conversation.to_dict() for conversation in self.conversations],
        }
