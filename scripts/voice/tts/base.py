# ============================================================
#  base.py - TTS 抽象基类（v3.2）
# ============================================================

from __future__ import annotations

import abc
import asyncio
import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


class TTSError(RuntimeError):
    """TTS 调用错误。"""


@dataclass
class TTSResult:
    """TTS 合成结果。"""
    audio_path: str                  # 输出音频文件路径
    text: str                        # 输入文本
    engine: str                      # 引擎名
    voice: str                       # 使用的 voice
    duration_sec: float = 0.0        # 音频时长
    sample_rate: int = 24000         # 采样率
    file_size: int = 0               # 文件字节数

    def __str__(self) -> str:
        return f"<TTSResult engine={self.engine} voice={self.voice} path={self.audio_path}>"


class BaseTTS(abc.ABC):
    """所有 TTS 引擎的抽象基类。"""

    engine_name: str = "base"
    supports_ssml: bool = False
    supports_streaming: bool = True
    output_format: str = "mp3"  # mp3 / wav / opus

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.voice: str = cfg.get("voice", "default")
        self.output_dir: str = cfg.get("output_dir", "data/voice_out")
        self.rate: str = cfg.get("rate", "+0%")
        self.volume: str = cfg.get("volume", "+0%")
        self.pitch: str = cfg.get("pitch", "+0Hz")
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    @abc.abstractmethod
    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        """实际合成：必须被实现。"""
        ...

    def synth(self, text: str, voice: Optional[str] = None,
              output_path: Optional[str] = None) -> TTSResult:
        """合成入口。"""
        if not text or not text.strip():
            raise TTSError("text 不能为空")
        text = self._preprocess(text)
        if not text.strip():
            raise TTSError("text 预处理后为空（可能全是 emoji/特殊字符）")

        voice = voice or self.voice
        if output_path is None:
            output_path = self._default_output_path(text, voice)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        self._synthesize(text, voice, output_path)

        p = Path(output_path)
        if not p.exists() or p.stat().st_size == 0:
            raise TTSError(f"合成失败：未生成有效文件 {output_path}")

        return TTSResult(
            audio_path=str(p),
            text=text,
            engine=self.name,
            voice=voice,
            file_size=p.stat().st_size,
        )

    # ---------- 工具方法 ----------

    def _default_output_path(self, text: str, voice: str) -> str:
        h = hashlib.md5(f"{text}|{voice}|{self.name}".encode("utf-8")).hexdigest()[:12]
        return str(Path(self.output_dir) / f"{self.name}_{h}.{self.output_format}")

    @staticmethod
    def _preprocess(text: str) -> str:
        """去掉 emoji、控制字符、合并多空格。"""
        # 去 emoji（仅匹配实际 emoji 块，避免误删 CJK）
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\u2600-\u26FF"
            "\u2700-\u27BF]+",
            flags=re.UNICODE,
        )
        text = emoji_pattern.sub("", text)
        # 去控制字符（保留 \t \n \r）
        text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)
        # 合并空白
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def play(path: str, player: str = "auto") -> bool:
        """播放音频。返回是否成功。"""
        p = Path(path)
        if not p.exists():
            return False
        if player == "auto":
            if sys.platform == "win32":
                player = "ffplay"
            elif sys.platform == "darwin":
                player = "afplay"
            else:
                player = "ffplay"
        try:
            if player == "ffplay":
                # 异步播放，ffplay 启动后立即返回
                subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(p)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            elif player == "afplay":
                subprocess.Popen(["afplay", str(p)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif player == "start":  # Windows start
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                return False
            return True
        except (FileNotFoundError, OSError):
            return False

    @staticmethod
    def list_voices() -> List[str]:
        """列出可用 voice。"""
        return []


# ---------- 异步入口（可选） ----------

async def asynth(self, text: str, voice: Optional[str] = None,
                 output_path: Optional[str] = None) -> TTSResult:
    """异步合成（默认实现是 sync 转 async）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self.synth, text, voice, output_path)
