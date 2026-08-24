from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.converters.markdown import conversation_to_markdown, write_markdown_files
from src.models import Conversation, Message
from src.utils.filenames import safe_filename, unique_filename


class MarkdownTests(unittest.TestCase):
    def test_safe_filename_cleans_required_title_cases(self) -> None:
        self.assertEqual(safe_filename(None, 1), "001_无标题聊天.md")
        self.assertEqual(safe_filename("  ", 2), "002_无标题聊天.md")
        cleaned = safe_filename("🙂标题\n含:非法?字符", 3)
        self.assertEqual(cleaned, "003_标题_含_非法_字符.md")
        self.assertNotIn("🙂", cleaned)
        self.assertLessEqual(len(safe_filename("a" * 200, 4)), 90)

    def test_duplicate_filenames_receive_suffixes(self) -> None:
        used: set[str] = set()
        self.assertEqual(unique_filename("001_相同.md", used), "001_相同.md")
        self.assertEqual(unique_filename("001_相同.md", used), "001_相同_2.md")
        self.assertEqual(unique_filename("001_相同.md", used), "001_相同_3.md")

    def test_markdown_keeps_original_title_and_writes_each_conversation(self) -> None:
        conversation = Conversation(
            id="1",
            provider="deepseek",
            title="🙂 原始\n标题",
            messages=[Message(id="m1", role="user", content="消息内容")],
        )
        content = conversation_to_markdown(conversation)
        self.assertIn("# 🙂 原始\n标题", content)
        self.assertIn("## 用户", content)

        with tempfile.TemporaryDirectory() as temporary_directory:
            result = write_markdown_files([conversation], Path(temporary_directory))
            files = list(Path(temporary_directory).glob("*.md"))

            self.assertEqual(result.written_count, 1)
            self.assertEqual(len(files), 1)
            self.assertNotIn("🙂", files[0].name)


if __name__ == "__main__":
    unittest.main()
