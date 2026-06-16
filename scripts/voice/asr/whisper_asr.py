# ============================================================
#  whisper_asr.py - Whisper ASR（v3.2）
# ============================================================
#
#  真实实现：使用 faster-whisper（CTranslate2 后端，比 openai-whisper 快 4x）
#  pip install faster-whisper
#
#  模型大小：tiny / base / small / medium / large-v3 / distil-large-v3
#  多语言：99+ 种（含中英日韩）
#  支持 VAD（语音活动检测）+ 时间戳
# ============================================================

from __future__ import annotations

import os
import wave
from typing import Optional

from .base import ASRError, ASRResult, BaseASR


class WhisperASR(BaseASR):
    """faster-whisper ASR 实现。"""

    engine_name = "whisper"
    supports_streaming = False
    supports_language_detection = True

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.compute_type = cfg.get("compute_type", "float16")  # float16 / int8 / float32
        self.beam_size = cfg.get("beam_size", 5)
        self.vad_filter = cfg.get("vad_filter", True)
        self.model_dir = cfg.get("model_dir", None)  # 自定义模型目录
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError:
            raise ASRError(
                "缺少 faster-whisper：pip install faster-whisper\n"
                "（首次运行会从 HuggingFace 下载模型，需联网）"
            )
        device = self.device
        if device == "auto":
            try:
                import torch  # type: ignore
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        # int8 兼容性最好，CPU 推荐
        if device == "cpu" and self.compute_type == "float16":
            self.compute_type = "int8"
        kw = {"device": device, "compute_type": self.compute_type}
        if self.model_dir:
            kw["download_root"] = self.model_dir
        self._model = WhisperModel(self.model_size, **kw)

    def _audio_duration(self, path: str) -> float:
        try:
            with wave.open(path, "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0

    def _transcribe(self, audio_path: str, language: Optional[str]) -> ASRResult:
        self._ensure_loaded()
        # auto 表示自动检测
        lang = None if language == "auto" else language
        try:
            segments, info = self._model.transcribe(
                audio_path,
                language=lang,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
            )
        except Exception as e:
            raise ASRError(f"Whisper 转写失败: {e}")
        segs: list = []
        text_parts: list = []
        for s in segments:
            segs.append({"start": s.start, "end": s.end, "text": s.text})
            text_parts.append(s.text.strip())
        full_text = " ".join(text_parts)
        return ASRResult(
            text=full_text,
            segments=segs,
            language=info.language if lang is None else (lang or "unknown"),
            engine=self.name,
            confidence=info.language_probability if hasattr(info, "language_probability") else 0.0,
            audio_path=audio_path,
            duration_sec=self._audio_duration(audio_path),
        )
