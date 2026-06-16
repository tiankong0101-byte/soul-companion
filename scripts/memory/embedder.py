# ============================================================
#  embedder.py - 文本向量化（v3.1）
# ============================================================
#
#  支持三种 embedding 后端（按优先级自动 fallback）：
#    1. ollama        : 本地 Ollama（推荐，零成本、隐私好）
#    2. openai_compat : OpenAI 兼容的 embedding API（OpenAI/Cohere…）
#    3. hash          : 哈希降级方案（无外部依赖，但语义检索质量差，仅做兜底）
#
#  维度需与 vector_index 保持一致（默认 768）
# ============================================================

from __future__ import annotations

import hashlib
import os
import sys
from typing import List, Optional

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

try:
    import requests
except ImportError:
    print("缺少依赖 requests", file=sys.stderr)
    raise


class EmbeddingError(RuntimeError):
    """Embedding 失败。"""


class BaseEmbedder:
    dim: int = 768

    def embed(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OllamaEmbedder(BaseEmbedder):
    """Ollama 本地 embedding（POST /api/embeddings）"""
    DEFAULT_MODEL = "nomic-embed-text"

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = "http://localhost:11434",
                 dim: int = 768, timeout: int = 30):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dim = dim
        self.timeout = timeout

    def _embed_one(self, text: str) -> List[float]:
        r = requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise EmbeddingError(f"Ollama embedding HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        emb = data.get("embedding")
        if not emb:
            raise EmbeddingError(f"Ollama 返回无 embedding: {data}")
        return list(emb)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        out = []
        for t in texts:
            out.append(self._embed_one(t))
        return out


class OpenAICompatEmbedder(BaseEmbedder):
    """OpenAI 兼容 embedding（/v1/embeddings）"""
    DEFAULT_URL = "https://api.openai.com/v1/embeddings"
    DEFAULT_MODEL = "text-embedding-3-small"
    DEFAULT_DIM = 1536

    def __init__(self, model: str = DEFAULT_MODEL, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, dim: int = DEFAULT_DIM, timeout: int = 30):
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or self.DEFAULT_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise EmbeddingError("OpenAI 兼容 embedding 需要 api_key（设置 OPENAI_API_KEY）")
        self.dim = dim
        self.timeout = timeout

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        r = requests.post(
            self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"input": texts, "model": self.model},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise EmbeddingError(f"OpenAI embed HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        return [d["embedding"] for d in data["data"]]


class HashEmbedder(BaseEmbedder):
    """哈希降级方案（无外部依赖）。仅用于没有 ollama/embedding API 时的兜底。
    警告：这不是真正的语义 embedding，相似度检索质量极差，仅保证系统能跑起来。
    """
    def __init__(self, dim: int = 768):
        self.dim = dim

    def _hash_vector(self, text: str) -> List[float]:
        # 用多个 hash 函数生成 dim 维向量（特征哈希 trick）
        if np is None:
            # 纯 Python 路径
            v = [0.0] * self.dim
            for word in text.split():
                h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 128) & 1 else -1.0
                v[idx] += sign
            return v
        v = np.zeros(self.dim, dtype=np.float32)
        for word in text.split():
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 128) & 1 else -1.0
            v[idx] += sign
        # L2 normalize
        n = float(np.linalg.norm(v))
        if n > 0:
            v = v / n
        return v.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(t) for t in texts]


def create_embedder(backend: str = "auto", dim: int = 768, **kwargs) -> BaseEmbedder:
    """工厂：按 backend 创建 embedder，auto 模式按 ollama → openai → hash 顺序探测。"""
    if backend == "ollama":
        return OllamaEmbedder(dim=dim, **kwargs)
    if backend == "openai_compat":
        return OpenAICompatEmbedder(dim=dim, **kwargs)
    if backend == "hash":
        return HashEmbedder(dim=dim)
    if backend == "auto":
        # 1) 尝试 Ollama
        try:
            emb = OllamaEmbedder(dim=dim)
            emb.embed("test")
            return emb
        except Exception:
            pass
        # 2) 尝试 OpenAI 兼容
        try:
            if os.environ.get("OPENAI_API_KEY"):
                return OpenAICompatEmbedder(dim=dim)
        except Exception:
            pass
        # 3) 哈希降级
        print("[embedder] 警告：未找到 Ollama/OpenAI，使用哈希降级（语义检索质量差）", file=sys.stderr)
        return HashEmbedder(dim=dim)
    raise EmbeddingError(f"未知 embedder backend: {backend}")
