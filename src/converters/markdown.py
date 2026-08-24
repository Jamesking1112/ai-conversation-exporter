"""把统一 Conversation 模型转换为一个会话一个 Markdown 文件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from src.models import Conversation, Message
from src.utils.filenames import display_title, safe_filename, unique_filename


ROLE_LABELS = {
    "user": "用户",
    "assistant": "DeepSeek",
    "system": "系统",
}


@dataclass(slots=True)
class ConversionIssue:
    stage: str
    conversation_id: str
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
class ConversionResult:
    written_count: int = 0
    issues: list[ConversionIssue] = field(default_factory=list)


def _role_label(message: Message) -> str:
    return ROLE_LABELS.get(message.role.lower(), message.role or "未知")


def conversation_to_markdown(conversation: Conversation) -> str:
    """生成单个会话的 Markdown 内容，标题保留原始文本。"""
    title = display_title(conversation.title)
    lines = [f"# {title}", "", "---", ""]

    if conversation.export_status != "complete":
        lines.extend(["> 聊天详情导出失败，未能获取该会话的消息内容。", ""])
        return "\n".join(lines)

    if not conversation.messages:
        lines.extend(["> 无内容", ""])
        return "\n".join(lines)

    for message in conversation.messages:
        lines.extend([f"## {_role_label(message)}", ""])
        lines.append(message.content if message.content else "> 无内容")
        lines.append("")

    return "\n".join(lines)


def write_markdown_files(
    conversations: Iterable[Conversation], output_dir: Path
) -> ConversionResult:
    """逐条写入 Markdown；某条失败时继续处理余下会话。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    result = ConversionResult()
    used_filenames: set[str] = set()

    for index, conversation in enumerate(conversations, start=1):
        try:
            filename = unique_filename(
                safe_filename(conversation.title, index), used_filenames
            )
            content = conversation_to_markdown(conversation)
            (output_dir / filename).write_text(content, encoding="utf-8")
            result.written_count += 1
        except Exception:
            result.issues.append(
                ConversionIssue(
                    stage="markdown_conversion",
                    conversation_id=conversation.id,
                    title=conversation.title,
                    message="Markdown 转换或写入失败，已跳过该会话。",
                )
            )

    return result
