# ============================================================
#  llm_backends.py - 多 LLM 后端实现（v3.0）
# ============================================================
#
#  提供统一的 BaseLLMClient 抽象 + 5 种后端实现：
#    - AnthropicClient      : Claude（原生 Messages API）
#    - OpenAIClient         : OpenAI（原生 Chat Completions）
#    - OpenAICompatClient   : 任何 OpenAI 兼容端点（DeepSeek/Zhipu/Moonshot/Ollama OpenAI 模式/vLLM）
#    - GeminiClient         : Google Gemini（generativelanguage API）
#    - OllamaClient         : Ollama（原生 /api/chat）
#
#  统一接口：
#    client.chat(messages, system=None, max_tokens=None, temperature=None, stream=False) -> LLMResponse
#    client.stream_chat(messages, **kwargs) -> Iterator[str]
#
#  所有实现只依赖 requests + pyyaml（见 requirements-v3.0.txt）
# ============================================================

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Union

try:
    import requests
except ImportError:  # pragma: no cover
    raise SystemExit("缺少依赖：pip install requests>=2.31")

# 消息格式统一为：
#   {"role": "system"|"user"|"assistant", "content": "..."}
#   {"role": "user", "content": [{"type": "text", "text": "..."}, ...]}  (多模态可扩展)

Message = Dict[str, Any]


@dataclass
class LLMResponse:
    """统一的 LLM 响应对象。"""
    text: str
    backend: str
    model: str
    raw: Any = None
    usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: int = 0

    def __str__(self) -> str:
        return self.text


class LLMError(RuntimeError):
    """LLM 调用错误基类。"""


class BaseLLMClient(ABC):
    """所有 LLM 后端的抽象基类。"""

    backend_name: str = "base"
    supports_stream: bool = True

    def __init__(self, name: str, cfg: Dict[str, Any]):
        self.name = name
        self.cfg = cfg
        self.model: str = cfg.get("model", "")
        self.max_tokens: int = int(cfg.get("max_tokens", 4096))
        self.temperature: float = float(cfg.get("temperature", 0.7))
        self.top_p: float = float(cfg.get("top_p", 0.95))
        self.timeout: int = int(cfg.get("timeout", 60))
        self.retry: int = int(cfg.get("retry", 3))

    @abstractmethod
    def _do_chat(self, messages: List[Message], system: Optional[str],
                 max_tokens: int, temperature: float, stream: bool) -> Union[LLMResponse, Iterator[str]]:
        ...

    def chat(self, messages: List[Message], system: Optional[str] = None,
             max_tokens: Optional[int] = None, temperature: Optional[float] = None,
             stream: bool = False) -> Union[LLMResponse, Iterator[str]]:
        # 把 system 从 messages 中拆出来（如果有）
        msgs = [m for m in messages if m.get("role") != "system"]
        sys_from_msgs = next((m["content"] for m in messages if m.get("role") == "system"), None)
        sys_final = system or sys_from_msgs

        if not msgs:
            raise LLMError("messages 至少需要一条 user 消息")

        return self._do_chat(
            messages=msgs,
            system=sys_final,
            max_tokens=int(max_tokens or self.max_tokens),
            temperature=float(temperature if temperature is not None else self.temperature),
            stream=stream,
        )

    def stream_chat(self, messages: List[Message], **kwargs) -> Iterator[str]:
        if not self.supports_stream:
            resp = self.chat(messages, **kwargs)
            if isinstance(resp, LLMResponse):
                yield resp.text
            return
        it = self.chat(messages, stream=True, **kwargs)
        if isinstance(it, LLMResponse):
            yield it.text
        else:
            yield from it


# =============================================================================
#  Anthropic Claude（原生 Messages API）
# =============================================================================

class AnthropicClient(BaseLLMClient):
    backend_name = "anthropic"
    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, name: str, cfg: Dict[str, Any]):
        super().__init__(name, cfg)
        self.api_key: str = self._resolve(cfg.get("api_key", ""))
        if not self.api_key:
            raise LLMError(f"[{name}] 缺少 Anthropic api_key（设置环境变量 ANTHROPIC_API_KEY）")
        self.base_url: str = cfg.get("base_url", "https://api.anthropic.com").rstrip("/") + "/v1/messages"

    @staticmethod
    def _resolve(v: str) -> str:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], "")
        return v or ""

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def _payload(self, messages, system, max_tokens, temperature, stream):
        p: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": self.top_p,
            "messages": messages,
            "stream": stream,
        }
        if system:
            p["system"] = system
        return p

    def _do_chat(self, messages, system, max_tokens, temperature, stream):
        payload = self._payload(messages, system, max_tokens, temperature, stream)
        t0 = time.time()
        last_err: Optional[Exception] = None
        for attempt in range(self.retry):
            try:
                r = requests.post(self.base_url, headers=self._headers(),
                                  json=payload, timeout=self.timeout, stream=stream)
                if r.status_code >= 400:
                    raise LLMError(f"Anthropic HTTP {r.status_code}: {r.text[:500]}")
                if stream:
                    return self._parse_stream(r, t0)
                data = r.json()
                text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
                return LLMResponse(
                    text=text,
                    backend=self.name,
                    model=data.get("model", self.model),
                    raw=data,
                    usage=data.get("usage", {}),
                    latency_ms=int((time.time() - t0) * 1000),
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < self.retry - 1:
                    time.sleep(2 ** attempt)
        raise LLMError(f"[{self.name}] 重试 {self.retry} 次仍失败: {last_err}")

    def _parse_stream(self, r: requests.Response, t0: float) -> Iterator[str]:
        # Anthropic SSE 事件：event: content_block_delta  data: {"delta":{"type":"text_delta","text":"..."}}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            try:
                evt = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "content_block_delta":
                delta = evt.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield delta.get("text", "")


# =============================================================================
#  OpenAI（原生 Chat Completions）
# =============================================================================

class OpenAIClient(BaseLLMClient):
    backend_name = "openai"
    DEFAULT_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, name: str, cfg: Dict[str, Any]):
        super().__init__(name, cfg)
        self.api_key = self._resolve(cfg.get("api_key", ""))
        if not self.api_key:
            raise LLMError(f"[{name}] 缺少 OpenAI api_key")
        self.base_url = cfg.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

    @staticmethod
    def _resolve(v: str) -> str:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], "")
        return v or ""

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(self, messages, system):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        return msgs

    def _do_chat(self, messages, system, max_tokens, temperature, stream):
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": self.top_p,
            "stream": stream,
        }
        t0 = time.time()
        last_err: Optional[Exception] = None
        for attempt in range(self.retry):
            try:
                r = requests.post(self.base_url, headers=self._headers(),
                                  json=payload, timeout=self.timeout, stream=stream)
                if r.status_code >= 400:
                    raise LLMError(f"OpenAI HTTP {r.status_code}: {r.text[:500]}")
                if stream:
                    return self._parse_stream(r, t0)
                data = r.json()
                choice = data.get("choices", [{}])[0]
                text = choice.get("message", {}).get("content", "")
                return LLMResponse(
                    text=text,
                    backend=self.name,
                    model=data.get("model", self.model),
                    raw=data,
                    usage=data.get("usage", {}),
                    latency_ms=int((time.time() - t0) * 1000),
                )
            except Exception as e:
                last_err = e
                if attempt < self.retry - 1:
                    time.sleep(2 ** attempt)
        raise LLMError(f"[{self.name}] 重试 {self.retry} 次仍失败: {last_err}")

    def _parse_stream(self, r: requests.Response, t0: float) -> Iterator[str]:
        # OpenAI SSE: data: {"choices":[{"delta":{"content":"..."}}]}
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:].strip()
            if chunk == "[DONE]":
                break
            try:
                evt = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            for c in evt.get("choices", []):
                delta = c.get("delta", {})
                if "content" in delta and delta["content"] is not None:
                    yield delta["content"]


# =============================================================================
#  OpenAI 兼容（DeepSeek / Zhipu / Moonshot / vLLM / Ollama OpenAI 模式）
# =============================================================================

class OpenAICompatClient(OpenAIClient):
    """OpenAIClient 的子类，复用 OpenAI Chat Completions 协议。
    适合：DeepSeek、Zhipu、Moonshot、vLLM、Ollama（启动时带 OPENAI 兼容层）、LM Studio、SiliconFlow 等。
    """
    backend_name = "openai_compat"

    def __init__(self, name: str, cfg: Dict[str, Any]):
        super().__init__(name, cfg)
        # 一些 OpenAI 兼容服务允许 api_key 为 "not-needed" 或任意字符串
        if self.api_key.lower() in ("", "not-needed", "none", "empty"):
            self.api_key = cfg.get("api_key", "not-needed")
        # Ollama 在 OpenAI 兼容模式下默认端口 11434 + /v1
        if "11434" in self.base_url and not self.base_url.endswith("/chat/completions"):
            self.base_url = self.base_url.rstrip("/") + "/chat/completions"


# =============================================================================
#  Google Gemini
# =============================================================================

class GeminiClient(BaseLLMClient):
    backend_name = "gemini"
    DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, name: str, cfg: Dict[str, Any]):
        super().__init__(name, cfg)
        self.api_key = self._resolve(cfg.get("api_key", ""))
        if not self.api_key:
            raise LLMError(f"[{name}] 缺少 Gemini api_key")
        self.model = cfg.get("model", "gemini-1.5-pro")
        # url 形如 https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=KEY
        self.base_url = cfg.get("base_url", self.DEFAULT_URL).rstrip("/")

    @staticmethod
    def _resolve(v: str) -> str:
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return os.environ.get(v[2:-1], "")
        return v or ""

    def _contents(self, messages, system):
        # Gemini 协议：contents: [{role: "user|model", parts:[{text:"..."}]}]
        out = []
        if system:
            out.append({"role": "user", "parts": [{"text": f"[SYSTEM]\n{system}"}]})
            out.append({"role": "model", "parts": [{"text": "好，我明白了。"}]})
        for m in messages:
            role = "model" if m.get("role") == "assistant" else "user"
            content = m.get("content", "")
            if isinstance(content, list):
                parts = content
            else:
                parts = [{"text": content or ""}]
            out.append({"role": role, "parts": parts})
        return out

    def _do_chat(self, messages, system, max_tokens, temperature, stream):
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": self._contents(messages, system),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
                "topP": self.top_p,
            },
        }
        t0 = time.time()
        last_err: Optional[Exception] = None
        for attempt in range(self.retry):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout)
                if r.status_code >= 400:
                    raise LLMError(f"Gemini HTTP {r.status_code}: {r.text[:500]}")
                data = r.json()
                cands = data.get("candidates", [])
                if not cands:
                    raise LLMError(f"Gemini 无候选返回: {data}")
                parts = cands[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                usage = data.get("usageMetadata", {})
                return LLMResponse(
                    text=text,
                    backend=self.name,
                    model=self.model,
                    raw=data,
                    usage={
                        "input_tokens": usage.get("promptTokenCount", 0),
                        "output_tokens": usage.get("candidatesTokenCount", 0),
                        "total_tokens": usage.get("totalTokenCount", 0),
                    },
                    latency_ms=int((time.time() - t0) * 1000),
                )
            except Exception as e:
                last_err = e
                if attempt < self.retry - 1:
                    time.sleep(2 ** attempt)
        raise LLMError(f"[{self.name}] 重试 {self.retry} 次仍失败: {last_err}")


# =============================================================================
#  Ollama（原生 /api/chat）
# =============================================================================

class OllamaClient(BaseLLMClient):
    backend_name = "ollama"
    DEFAULT_URL = "http://localhost:11434"

    def __init__(self, name: str, cfg: Dict[str, Any]):
        super().__init__(name, cfg)
        self.base_url = cfg.get("base_url", self.DEFAULT_URL).rstrip("/")

    def _payload(self, messages, system, max_tokens, temperature, stream):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        return {
            "model": self.model,
            "messages": msgs,
            "stream": stream,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "top_p": self.top_p,
            },
        }

    def _do_chat(self, messages, system, max_tokens, temperature, stream):
        url = f"{self.base_url}/api/chat"
        payload = self._payload(messages, system, max_tokens, temperature, stream)
        t0 = time.time()
        last_err: Optional[Exception] = None
        for attempt in range(self.retry):
            try:
                r = requests.post(url, json=payload, timeout=self.timeout, stream=stream)
                if r.status_code >= 400:
                    raise LLMError(f"Ollama HTTP {r.status_code}: {r.text[:500]}")
                if stream:
                    return self._parse_stream(r, t0)
                data = r.json()
                text = data.get("message", {}).get("content", "")
                return LLMResponse(
                    text=text,
                    backend=self.name,
                    model=data.get("model", self.model),
                    raw=data,
                    usage={
                        "input_tokens": data.get("prompt_eval_count", 0),
                        "output_tokens": data.get("eval_count", 0),
                    },
                    latency_ms=int((time.time() - t0) * 1000),
                )
            except Exception as e:
                last_err = e
                if attempt < self.retry - 1:
                    time.sleep(2 ** attempt)
        raise LLMError(f"[{self.name}] 重试 {self.retry} 次仍失败: {last_err}")

    def _parse_stream(self, r: requests.Response, t0: float) -> Iterator[str]:
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            chunk = evt.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if evt.get("done"):
                break


# =============================================================================
#  工厂
# =============================================================================

CLIENT_REGISTRY = {
    "anthropic": AnthropicClient,
    "openai": OpenAIClient,
    "openai_compat": OpenAICompatClient,
    "gemini": GeminiClient,
    "ollama": OllamaClient,
}


def create_client(name: str, cfg: Dict[str, Any]) -> BaseLLMClient:
    """根据 cfg.type 创建对应后端客户端。"""
    t = cfg.get("type", "").lower()
    cls = CLIENT_REGISTRY.get(t)
    if not cls:
        raise LLMError(f"未知后端类型: {t}（可选: {list(CLIENT_REGISTRY.keys())}）")
    return cls(name, cfg)
