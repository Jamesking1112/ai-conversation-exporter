from __future__ import annotations

import unittest

from src.models import Conversation
from src.models.conversation import extract_history_messages


class ConversationModelTests(unittest.TestCase):
    def test_deepseek_fragments_are_joined_and_source_is_preserved(self) -> None:
        session = {
            "id": "session-1",
            "title": "测试标题",
            "created_at": 10,
            "updated_at": 20,
            "extra_session_field": "preserved",
        }
        history = [
            {
                "id": "message-1",
                "role": "USER",
                "created_at": 11,
                "fragments": [{"content": "你好"}, {"content": "，世界"}],
                "extra_message_field": {"kept": True},
            },
            {"id": "message-2", "role": "ASSISTANT", "content": "你好！"},
        ]

        conversation = Conversation.from_deepseek(session, history, fallback_id="fallback")

        self.assertEqual(conversation.id, "session-1")
        self.assertEqual(conversation.messages[0].role, "user")
        self.assertEqual(conversation.messages[0].content, "你好，世界")
        self.assertEqual(conversation.messages[1].role, "assistant")
        self.assertEqual(conversation.messages[1].content, "你好！")
        self.assertEqual(conversation.source["session"]["extra_session_field"], "preserved")
        self.assertEqual(
            conversation.messages[0].source["extra_message_field"], {"kept": True}
        )

    def test_history_message_container_and_empty_data_are_supported(self) -> None:
        self.assertEqual(
            extract_history_messages({"messages": [{"role": "USER", "content": "a"}]}),
            [{"role": "USER", "content": "a"}],
        )
        self.assertEqual(extract_history_messages({"data": []}), [])
        self.assertEqual(extract_history_messages(None), [])


if __name__ == "__main__":
    unittest.main()
