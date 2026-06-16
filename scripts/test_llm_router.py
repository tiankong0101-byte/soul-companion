#!/usr/bin/env python3
# ============================================================
#  test_llm_router.py - 单元测试（v3.0）
# ============================================================
#
#  涵盖：
#    1. 配置加载 + ${ENV} 展开
#    2. 后端注册表完整性
#    3. mock HTTP 后测试 chat() / 错误重试 / 流式
#    4. CLI 子命令解析
#
#  运行：python scripts/test_llm_router.py
#  或：  python -m unittest scripts/test_llm_router.py
# ============================================================

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_router  # noqa: E402
import llm_backends  # noqa: E402
from llm_backends import (  # noqa: E402
    AnthropicClient, GeminiClient, LLMError, LLMResponse,
    OpenAIClient, OpenAICompatClient, OllamaClient, create_client,
    CLIENT_REGISTRY,
)


SAMPLE_YAML = """
version: "3.0"
default_backend: "mock-a"
backends:
  mock-a:
    type: "openai"
    api_key: "${TEST_API_KEY}"
    model: "mock-model"
    max_tokens: 100
  mock-b:
    type: "anthropic"
    api_key: "static-key"
    model: "claude-mock"
feifei_persona:
  system_prompt: "你是菲菲。"
  mode_overrides:
    comfort: "陪伴模式"
    listener: "树洞模式"
defaults:
  stream: false
"""


class TestEnvExpansion(unittest.TestCase):
    def test_expand_env_string(self):
        os.environ["FOO_BAR"] = "hello"
        self.assertEqual(llm_router.expand_env("${FOO_BAR}"), "hello")
        self.assertEqual(llm_router.expand_env("plain"), "plain")
        self.assertEqual(llm_router.expand_env("${MISSING_VAR_XYZ}"), "${MISSING_VAR_XYZ}")

    def test_expand_env_nested(self):
        os.environ["API"] = "sk-xyz"
        d = {"a": "${API}", "b": {"c": ["${API}", "static"]}}
        out = llm_router.expand_env(d)
        self.assertEqual(out["a"], "sk-xyz")
        self.assertEqual(out["b"]["c"], ["sk-xyz", "static"])


class TestRouterLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).resolve().parent / "_test_cfg.yaml"
        self.tmp.write_text(SAMPLE_YAML, encoding="utf-8")
        os.environ["TEST_API_KEY"] = "test-key-123"

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def test_from_config(self):
        rt = llm_router.LLMRouter.from_config(self.tmp)
        self.assertEqual(rt.default_backend, "mock-a")
        self.assertEqual(rt.backends["mock-a"]["api_key"], "test-key-123")
        self.assertEqual(rt.feifei_persona["system_prompt"], "你是菲菲。")

    def test_feifei_system_prompt(self):
        rt = llm_router.LLMRouter.from_config(self.tmp)
        self.assertEqual(rt.feifei_system_prompt(), "你是菲菲。")
        self.assertIn("陪伴模式", rt.feifei_system_prompt("comfort"))
        self.assertIn("树洞模式", rt.feifei_system_prompt("listener"))
        self.assertEqual(rt.feifei_system_prompt("default"), "你是菲菲。")
        self.assertEqual(rt.feifei_system_prompt("unknown_mode"), "你是菲菲。")

    def test_list_backends(self):
        rt = llm_router.LLMRouter.from_config(self.tmp)
        bks = rt.list_backends()
        names = [b["name"] for b in bks]
        self.assertIn("mock-a", names)
        self.assertTrue(any(b["is_default"] for b in bks if b["name"] == "mock-a"))


class TestBackendFactory(unittest.TestCase):
    def test_create_openai(self):
        c = create_client("x", {"type": "openai", "api_key": "k", "model": "m"})
        self.assertIsInstance(c, OpenAIClient)
        self.assertFalse(isinstance(c, OpenAICompatClient))

    def test_create_openai_compat(self):
        c = create_client("x", {"type": "openai_compat", "api_key": "k",
                                 "base_url": "https://api.deepseek.com/v1", "model": "m"})
        self.assertIsInstance(c, OpenAICompatClient)

    def test_create_anthropic(self):
        c = create_client("x", {"type": "anthropic", "api_key": "k", "model": "m"})
        self.assertIsInstance(c, AnthropicClient)

    def test_create_gemini(self):
        c = create_client("x", {"type": "gemini", "api_key": "k", "model": "gemini-1.5-pro"})
        self.assertIsInstance(c, GeminiClient)

    def test_create_ollama(self):
        c = create_client("x", {"type": "ollama", "model": "qwen2.5:7b"})
        self.assertIsInstance(c, OllamaClient)

    def test_create_unknown(self):
        with self.assertRaises(LLMError):
            create_client("x", {"type": "nope"})

    def test_registry_covers_all_types(self):
        self.assertEqual(
            set(CLIENT_REGISTRY.keys()),
            {"anthropic", "openai", "openai_compat", "gemini", "ollama"},
        )


class TestOpenAIClientChat(unittest.TestCase):
    def _client(self):
        return OpenAIClient("oai", {"type": "openai", "api_key": "k", "model": "gpt-4o"})

    @patch("llm_backends.requests.post")
    def test_chat_success(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.json.return_value = {
            "model": "gpt-4o",
            "choices": [{"message": {"content": "你好！"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        m_post.return_value = m_resp
        c = self._client()
        resp = c.chat([{"role": "user", "content": "hi"}], system="sys")
        self.assertIsInstance(resp, LLMResponse)
        self.assertEqual(resp.text, "你好！")
        self.assertEqual(resp.usage["total_tokens"], 8)
        # 验证请求体
        call_kwargs = m_post.call_args.kwargs
        body = call_kwargs["json"]
        self.assertEqual(body["model"], "gpt-4o")
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][1]["content"], "hi")

    @patch("llm_backends.requests.post")
    def test_chat_http_error(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 401
        m_resp.text = "Unauthorized"
        m_post.return_value = m_resp
        c = self._client()
        # retry=3 会跑 3 次
        c.retry = 1
        with self.assertRaises(LLMError) as ctx:
            c.chat([{"role": "user", "content": "hi"}])
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(m_post.call_count, 1)

    @patch("llm_backends.requests.post")
    def test_chat_no_user_message(self, m_post):
        c = self._client()
        with self.assertRaises(LLMError):
            c.chat([])


class TestAnthropicClient(unittest.TestCase):
    @patch("llm_backends.requests.post")
    def test_chat_success(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.json.return_value = {
            "model": "claude-3-5-sonnet-20241022",
            "content": [{"type": "text", "text": "我在听。"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        m_post.return_value = m_resp
        c = AnthropicClient("ant", {"type": "anthropic", "api_key": "k", "model": "claude-3-5-sonnet-20241022"})
        resp = c.chat([{"role": "user", "content": "今天好累"}], system="你是菲菲")
        self.assertEqual(resp.text, "我在听。")
        body = m_post.call_args.kwargs["json"]
        # 验证 system 字段独立于 messages
        self.assertEqual(body["system"], "你是菲菲")
        # 所有 messages 都不应是 system role（Anthropic 协议下 system 是顶层字段）
        for m in body["messages"]:
            self.assertNotEqual(m.get("role"), "system")
        self.assertEqual(body["messages"][0]["role"], "user")

    def test_missing_api_key_raises(self):
        # 显式删除环境变量以确保失败
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with self.assertRaises(LLMError):
            AnthropicClient("ant", {"type": "anthropic", "api_key": "${ANTHROPIC_API_KEY}", "model": "m"})


class TestOpenAICompatOverrides(unittest.TestCase):
    def test_ollama_openai_compat_url(self):
        c = OpenAICompatClient("o", {
            "type": "openai_compat",
            "api_key": "not-needed",
            "base_url": "http://localhost:11434/v1",
            "model": "qwen2.5:7b",
        })
        self.assertTrue(c.base_url.endswith("/chat/completions"))

    def test_ollama_openai_compat_no_url_suffix(self):
        c = OpenAICompatClient("o", {
            "type": "openai_compat",
            "api_key": "not-needed",
            "base_url": "http://localhost:11434",
            "model": "qwen2.5:7b",
        })
        self.assertTrue(c.base_url.endswith("/chat/completions"))


class TestOllamaClient(unittest.TestCase):
    @patch("llm_backends.requests.post")
    def test_chat_success(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.json.return_value = {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": "Hi"},
            "prompt_eval_count": 8,
            "eval_count": 2,
        }
        m_post.return_value = m_resp
        c = OllamaClient("ol", {"type": "ollama", "model": "qwen2.5:7b"})
        resp = c.chat([{"role": "user", "content": "hi"}], system="你是菲菲")
        self.assertEqual(resp.text, "Hi")
        body = m_post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "qwen2.5:7b")
        # 验证 system 消息被加入
        roles = [m["role"] for m in body["messages"]]
        self.assertIn("system", roles)
        self.assertIn("user", roles)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).resolve().parent / "_test_cfg.yaml"
        self.tmp.write_text(SAMPLE_YAML, encoding="utf-8")
        os.environ["TEST_API_KEY"] = "test-key-123"

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def test_list_command(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = llm_router.main(["-c", str(self.tmp), "list"])
        self.assertEqual(rc, 0)
        self.assertIn("mock-a", out.getvalue())
        self.assertIn("*", out.getvalue())

    def test_show_command(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = llm_router.main(["-c", str(self.tmp), "show", "mock-a"])
        self.assertEqual(rc, 0)
        self.assertIn("mock-model", out.getvalue())

    def test_chat_missing_message(self):
        with redirect_stdout(io.StringIO()):
            rc = llm_router.main(["-c", str(self.tmp), "chat"])
        self.assertEqual(rc, 1)

    @patch("llm_backends.requests.post")
    def test_chat_command(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.json.return_value = {
            "model": "mock-model",
            "choices": [{"message": {"content": "pong"}}],
            "usage": {"total_tokens": 1},
        }
        m_post.return_value = m_resp
        out = io.StringIO()
        with redirect_stdout(out):
            rc = llm_router.main(["-c", str(self.tmp), "chat", "-b", "mock-a", "-m", "ping"])
        self.assertEqual(rc, 0)
        self.assertIn("pong", out.getvalue())


class TestResolveStaticFallback(unittest.TestCase):
    """验证 ${VAR} 解析失败时不会自动回退到字面量 —— 应当被替换为空。"""

    def test_resolve_returns_empty_when_unset(self):
        from llm_backends import AnthropicClient
        # 通过反射拿到 _resolve（避免重复实现）
        v = AnthropicClient._resolve("${DEFINITELY_NOT_SET_XYZ}")
        self.assertEqual(v, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
