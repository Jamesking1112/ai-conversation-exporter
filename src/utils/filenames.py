"""Windows 兼容的 Markdown 文件名清洗。"""

from __future__ import annotations

import re
from typing import Any


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
_EMOJI_AND_JOINERS = re.compile(
    r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0E\uFE0F\u200D]"
)


def display_title(title: Any) -> str:
    """生成 Markdown 中使用的标题；尽可能保留原始文本。"""
    if title is None:
        return "无标题聊天"
    text = str(title)
    return text if text.strip() else "无标题聊天"


def safe_filename(title: Any, index: int) -> str:
    """把标题转为稳定、安全的 Markdown 文件名。"""
    text = display_title(title)
    text = text.replace("\n", "_").replace("\r", "_").replace("\t", "_")
    text = _CONTROL_CHARACTERS.sub("", text)
    text = _EMOJI_AND_JOINERS.sub("", text)
    text = _WINDOWS_FORBIDDEN.sub("_", text)
    text = text.strip(" .")
    text = text[:80].strip(" .")
    if not text:
        text = "无标题聊天"
    return f"{index:03d}_{text}.md"


def unique_filename(filename: str, used: set[str]) -> str:
    """保证同一批次中不会因标题重复而覆盖文件。"""
    if filename not in used:
        used.add(filename)
        return filename

    stem, extension = filename.rsplit(".", 1)
    counter = 2
    candidate = f"{stem}_{counter}.{extension}"
    while candidate in used:
        counter += 1
        candidate = f"{stem}_{counter}.{extension}"
    used.add(candidate)
    return candidate
