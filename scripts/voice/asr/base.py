# ============================================================
#  base.py - ASR 抽象基类（v3.2）
# ============================================================

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


class ASRError(RuntimeError):
    """ASR 调用错误。"""


@dataclass
class ASRResult:
    """ASR 识别结果。"""
    text: str                                # 完整识别文本
    segments: List[dict] = field(default_factory=list)  # [{start, end, text}]
    language: str = "zh"
    engine: str = "base"
    confidence: float = 0.0
    audio_path: str = ""
    duration_sec: float = 0.0

    def __str__(self) -> str:
        return f"<ASRResult engine={self.engine} lang={self.language} text={self.text[:50]!r}>"


class BaseASR(abc.ABC):
    """ASR 引擎抽象基类。"""

    engine_name: str = "base"
    supports_streaming: bool = False
    supports_language_detection: bool = True

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.language: str = cfg.get("language", "auto")  # auto / zh / en / ja
        self.model_size: str = cfg.get("model_size", "base")
        self.device: str = cfg.get("device", "auto")

    @abc.abstractmethod
    def _transcribe(self, audio_path: str, language: Optional[str]) -> ASRResult:
        ...

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> ASRResult:
        if not Path(audio_path).exists():
            raise ASRError(f"音频文件不存在: {audio_path}")
        lang = language or self.language
        return self._transcribe(audio_path, lang)
