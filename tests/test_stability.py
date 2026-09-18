"""第六阶段稳定性与本地 LLM 接入的离线回归测试。"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.service.llm_service import stream_chat
from app.service.parser.mineru_parser import MinerUParser
from app.utils.token_utils import estimate_token_count


class TokenEstimateTests(unittest.TestCase):
    """锁定输入保护使用的轻量 token 估算契约。"""

    def test_empty_text_is_zero(self):
        self.assertEqual(estimate_token_count(""), 0)

    def test_mixed_text_counts_non_ascii_and_ascii_words(self):
        # 中文按字符计，ASCII 单词按四字符一个 token 估算，标点单独计数。
        self.assertEqual(estimate_token_count("你好 hello"), 4)


class _FakeResponse:
    status_code = 200

    async def aiter_lines(self):
        yield '{"message":{"content":"你好"}}'
        yield '{"message":{"content":"，世界"},"done":true}'


class _FakeStream:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        self.attempt = _FakeClient.calls
        _FakeClient.calls += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        if self.attempt == 0:
            raise httpx.ConnectError("transient connection failure")
        return _FakeStream(_FakeResponse())


class LlmRetryTests(unittest.IsolatedAsyncioTestCase):
    """首 token 前的瞬时连接错误应重试，已开始输出后不重放。"""

    async def test_ollama_retries_before_first_token(self):
        _FakeClient.calls = 0
        fake_settings = SimpleNamespace(
            llm_provider="ollama",
            ollama_base_url="http://127.0.0.1:11434/v1",
            llm_base_url="https://api.example.test",
            llm_model="qwen3:8b",
            llm_api_key="",
            rag_temperature=0.3,
            rag_max_tokens=32,
            llm_max_retries=1,
            llm_retry_backoff_seconds=0,
        )
        with patch("app.service.llm_service.get_settings", return_value=fake_settings), \
                patch("app.service.llm_service.httpx.AsyncClient", _FakeClient):
            result = [part async for part in stream_chat("system", "question")]

        self.assertEqual(result, ["你好", "，世界"])
        self.assertEqual(_FakeClient.calls, 2)


class MinerURetryTests(unittest.TestCase):
    """MinerU 首次连接失败时只重试上传握手。"""

    def test_initial_connect_error_is_retried(self):
        settings = SimpleNamespace(mineru_connect_retries=1, mineru_retry_backoff_seconds=0)
        parser = MinerUParser()
        with patch.object(
            parser,
            "_create_upload",
            side_effect=[httpx.ConnectError("warming up"), {"id": "upload-1"}],
        ) as create_upload, patch("app.service.parser.mineru_parser.sleep") as retry_sleep:
            result = parser._create_upload_with_retry(None, "http://mineru", Path("sample.pdf"), {}, settings)

        self.assertEqual(result["id"], "upload-1")
        self.assertEqual(create_upload.call_count, 2)
        retry_sleep.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
