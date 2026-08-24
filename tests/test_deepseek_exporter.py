from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import requests

from src.converters import write_markdown_files
from src.exporters.deepseek import BASE_URL, FETCH_PAGE_PATH, DeepSeekExporter
from src.models import ExportDocument
from src.utils.config import DeepSeekConfig, RequestConfig
from src.utils.errors import AuthenticationError
from src.utils.http import RetryingHttpClient


class FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response  # type: ignore[return-value]


def exporter_with(
    responses: list[object], *, max_retries: int = 0, sleeps: list[float] | None = None
) -> tuple[DeepSeekExporter, FakeSession]:
    fake_session = FakeSession(responses)
    sleep_values = sleeps if sleeps is not None else []
    client = RetryingHttpClient(
        RequestConfig(max_retries=max_retries, retry_base_delay_seconds=1),
        session=fake_session,  # type: ignore[arg-type]
        sleep=sleep_values.append,
    )
    exporter = DeepSeekExporter(
        DeepSeekConfig(authorization="Bearer test-token", cookie="test-cookie"),
        client,
        sleep=sleep_values.append,
        progress=lambda _message: None,
    )
    return exporter, fake_session


class DeepSeekExporterTests(unittest.TestCase):
    def test_fetch_page_uses_original_cursor_pagination(self) -> None:
        exporter, session = exporter_with(
            [
                FakeResponse(
                    200,
                    {
                        "data": {
                            "biz_data": {
                                "chat_sessions": [{"id": "a", "updated_at": 20}],
                                "has_more": True,
                            }
                        }
                    },
                ),
                FakeResponse(
                    200,
                    {
                        "data": {
                            "biz_data": {
                                "chat_sessions": [{"id": "b", "updated_at": 10}],
                                "has_more": False,
                            }
                        }
                    },
                ),
            ]
        )

        sessions = exporter.fetch_all_sessions()

        self.assertEqual([item["id"] for item in sessions], ["a", "b"])
        self.assertEqual(session.calls[0]["url"], BASE_URL + FETCH_PAGE_PATH)
        self.assertEqual(session.calls[0]["params"], {"lte_cursor.pinned": "false"})
        self.assertEqual(
            session.calls[1]["params"],
            {"lte_cursor.pinned": "false", "lte_cursor.updated_at": "20"},
        )

    def test_history_request_keeps_chat_session_id_query_parameter(self) -> None:
        exporter, session = exporter_with([FakeResponse(200, {"data": []})])

        self.assertEqual(exporter.fetch_history("chat id"), [])

        self.assertEqual(
            session.calls[0]["url"],
            "https://chat.deepseek.com/api/v0/chat/history_messages?chat_session_id=chat+id",
        )
        self.assertIsNone(session.calls[0]["params"])

    def test_history_failure_does_not_stop_remaining_conversations(self) -> None:
        exporter, _session = exporter_with(
            [
                FakeResponse(
                    200,
                    {
                        "data": {
                            "biz_data": {
                                "chat_sessions": [
                                    {"id": "bad", "title": "失败会话"},
                                    {"id": "good", "title": "成功会话"},
                                ],
                                "has_more": False,
                            }
                        }
                    },
                ),
                FakeResponse(500, {}),
                FakeResponse(
                    200,
                    {"data": [{"role": "ASSISTANT", "content": "仍会继续"}]},
                ),
            ]
        )

        result = exporter.export_conversations()

        self.assertEqual(len(result.conversations), 2)
        self.assertEqual(result.conversations[0].export_status, "failed")
        self.assertEqual(result.conversations[1].messages[0].content, "仍会继续")
        self.assertEqual(len(result.issues), 1)

        with tempfile.TemporaryDirectory() as temporary_directory:
            document = ExportDocument(result.conversations).to_dict()
            json_path = Path(temporary_directory) / "deepseek_conversations.json"
            json_path.write_text(
                json.dumps(document, ensure_ascii=False), encoding="utf-8"
            )
            conversion = write_markdown_files(
                result.conversations, Path(temporary_directory) / "markdown"
            )

            self.assertEqual(document["schema_version"], "0.1")
            self.assertEqual(conversion.written_count, 2)
            self.assertEqual(
                len(json.loads(json_path.read_text(encoding="utf-8"))["conversations"]), 2
            )

    def test_authentication_error_is_safe_and_not_retried(self) -> None:
        exporter, session = exporter_with([FakeResponse(401, {})], max_retries=3)

        with self.assertRaises(AuthenticationError) as raised:
            exporter.fetch_all_sessions()

        self.assertEqual(len(session.calls), 1)
        self.assertNotIn("test-token", str(raised.exception))
        self.assertNotIn("test-cookie", str(raised.exception))

    def test_network_error_is_retried(self) -> None:
        sleeps: list[float] = []
        exporter, session = exporter_with(
            [
                requests.ConnectionError("offline"),
                FakeResponse(
                    200,
                    {
                        "data": {
                            "biz_data": {"chat_sessions": [], "has_more": False}
                        }
                    },
                ),
            ],
            max_retries=1,
            sleeps=sleeps,
        )

        sessions = exporter.fetch_all_sessions()

        self.assertEqual(sessions, [])
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(sleeps, [1])


if __name__ == "__main__":
    unittest.main()
