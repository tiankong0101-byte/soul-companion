#!/usr/bin/env python3
# ============================================================
#  llm_router.py - 菲菲 LLM 统一路由（v3.0）
# ============================================================
#
#  功能：
#    - 从 config/llm.yaml 加载多后端配置
#    - ${ENV_VAR} 自动展开为环境变量
#    - 提供 Python API + CLI
#
#  用法：
#    python scripts/llm_router.py list
#    python scripts/llm_router.py show anthropic
#    python scripts/llm_router.py test --backend anthropic
#    python scripts/llm_router.py chat --backend anthropic --message "你好"
#    python scripts/llm_router.py chat --backend ollama-qwen --system "你是菲菲" --message "今天好累"
#    python scripts/llm_router.py chat --backend deepseek --stream --message "讲个笑话"
# ============================================================

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("缺少依赖 pyyaml，请先：pip install pyyaml", file=sys.stderr)
    raise

# 允许从 scripts/ 同级目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_backends import LLMError, LLMResponse, create_client  # noqa: E402

ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def expand_env(value: Any) -> Any:
    """递归展开 ${VAR} → os.environ[VAR]（找不到则保留原样）。"""
    if isinstance(value, str):
        def _sub(m: "re.Match[str]") -> str:
            var = m.group(1)
            return os.environ.get(var, m.group(0))
        return ENV_PATTERN.sub(_sub, value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


class LLMRouter:
    """多 LLM 后端路由。"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.backends: Dict[str, Dict[str, Any]] = config.get("backends", {})
        self.default_backend: str = config.get("default_backend", next(iter(self.backends), ""))
        self.feifei_persona: Dict[str, Any] = config.get("feifei_persona", {})
        self._client_cache: Dict[str, Any] = {}

    # ---------- 工厂 ----------

    @classmethod
    def from_config(cls, path: str | Path) -> "LLMRouter":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"找不到配置: {p}")
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls(expand_env(raw))

    def get_client(self, name: Optional[str] = None):
        name = name or self.default_backend
        if name not in self.backends:
            raise LLMError(f"未知后端: {name}（可用: {list(self.backends.keys())}）")
        if name not in self._client_cache:
            self._client_cache[name] = create_client(name, self.backends[name])
        return self._client_cache[name]

    # ---------- 业务 ----------

    def list_backends(self) -> List[Dict[str, Any]]:
        out = []
        for n, b in self.backends.items():
            out.append({
                "name": n,
                "type": b.get("type", "?"),
                "model": b.get("model", ""),
                "description": b.get("description", ""),
                "is_default": n == self.default_backend,
            })
        return out

    def feifei_system_prompt(self, mode: Optional[str] = None) -> str:
        persona = self.feifei_persona or {}
        base = persona.get("system_prompt", "")
        overrides = persona.get("mode_overrides", {}) or {}
        if mode and overrides.get(mode):
            base = overrides[mode] + "\n\n" + base
        return base

    def chat(self, messages: List[Dict[str, Any]],
             backend: Optional[str] = None,
             system: Optional[str] = None,
             mode: Optional[str] = None,
             stream: Optional[bool] = None,
             **kwargs) -> LLMResponse:
        client = self.get_client(backend)
        if system is None:
            system = self.feifei_system_prompt(mode)
        if stream is None:
            stream = bool(self.config.get("defaults", {}).get("stream", False))
        resp = client.chat(messages, system=system, stream=stream, **kwargs)
        if stream:
            # 流式 → 拼成完整响应返回
            return self._collect_stream(client, messages, system, **kwargs)
        assert isinstance(resp, LLMResponse)
        return resp

    def stream_chat(self, messages: List[Dict[str, Any]], **kwargs):
        client = self.get_client(kwargs.pop("backend", None))
        if "system" not in kwargs and "mode" in kwargs:
            kwargs["system"] = self.feifei_system_prompt(kwargs.pop("mode"))
        yield from client.stream_chat(messages, **kwargs)

    @staticmethod
    def _collect_stream(client, messages, system, **kwargs):
        """收集流式响应为完整 LLMResponse。"""
        import time
        t0 = time.time()
        chunks: List[str] = []
        for c in client.stream_chat(messages, system=system, **kwargs):
            chunks.append(c)
        return LLMResponse(
            text="".join(chunks),
            backend=client.name,
            model=client.model,
            latency_ms=int((time.time() - t0) * 1000),
        )


# =============================================================================
#  CLI
# =============================================================================

def _default_config_path() -> Path:
    # 优先：环境变量 SOUL_COMPANION_CONFIG
    env = os.environ.get("SOUL_COMPANION_CONFIG")
    if env:
        return Path(env)
    # 回退：脚本同级 ../config/llm.yaml
    return Path(__file__).resolve().parent.parent / "config" / "llm.yaml"


def cmd_list(rt: LLMRouter, _args):
    print("可用后端（* = default）：\n")
    for b in rt.list_backends():
        star = "*" if b["is_default"] else " "
        desc = f"  — {b['description']}" if b["description"] else ""
        print(f"  {star} {b['name']:<22} {b['type']:<13} {b['model']}{desc}")
    print(f"\n默认: {rt.default_backend}")


def cmd_show(rt: LLMRouter, args):
    name = args.name
    if name not in rt.backends:
        print(f"未知后端: {name}", file=sys.stderr)
        return 1
    import json
    print(json.dumps(rt.backends[name], ensure_ascii=False, indent=2))
    return 0


def cmd_test(rt: LLMRouter, args):
    """连通性测试：发一条极短消息看是否成功。"""
    backend = args.backend or rt.default_backend
    msgs = [{"role": "user", "content": "请用一句话回答：1+1=?"}]
    print(f"→ 测试后端 [{backend}] ...")
    try:
        resp = rt.chat(msgs, backend=backend, max_tokens=64)
        print(f"✓ 成功 ({resp.latency_ms}ms, model={resp.model})")
        print(f"  回答: {resp.text.strip()}")
        if resp.usage:
            print(f"  用量: {resp.usage}")
        return 0
    except LLMError as e:
        print(f"✗ 失败: {e}", file=sys.stderr)
        return 2


def cmd_chat(rt: LLMRouter, args):
    """单轮对话。"""
    backend = args.backend or rt.default_backend
    msgs = []
    if args.system:
        msgs.append({"role": "system", "content": args.system})
    if not args.message and not args.message_file:
        print("需要 --message 或 --message-file", file=sys.stderr)
        return 1
    user_text = args.message or Path(args.message_file).read_text(encoding="utf-8")
    msgs.append({"role": "user", "content": user_text})

    if args.stream:
        print(f"[{backend}] (stream) >>>")
        for chunk in rt.stream_chat(msgs, backend=backend):
            print(chunk, end="", flush=True)
        print()
        return 0
    else:
        try:
            resp = rt.chat(msgs, backend=backend, mode=args.mode)
        except LLMError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
        print(f"[{backend} | {resp.model} | {resp.latency_ms}ms]")
        print(resp.text)
        if resp.usage:
            print(f"\n[usage: {resp.usage}]")
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llm_router",
        description="soul-companion v3.0 多 LLM 路由",
    )
    p.add_argument("-c", "--config", default=str(_default_config_path()),
                   help="YAML 配置文件路径")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="列出所有后端")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="显示某个后端的详细配置")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("test", help="连通性测试")
    sp.add_argument("--backend", "-b", default=None)
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("chat", help="单轮对话")
    sp.add_argument("--backend", "-b", default=None)
    sp.add_argument("--message", "-m", default=None)
    sp.add_argument("--message-file", "-f", default=None)
    sp.add_argument("--system", "-s", default=None)
    sp.add_argument("--mode", default=None, help="菲菲模式（comfort/listener/playful/default）")
    sp.add_argument("--stream", action="store_true")
    sp.set_defaults(func=cmd_chat)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        rt = LLMRouter.from_config(args.config)
    except FileNotFoundError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return args.func(rt, args) or 0


if __name__ == "__main__":
    sys.exit(main())
