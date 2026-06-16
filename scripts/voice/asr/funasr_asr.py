# ============================================================
#  funasr_asr.py - 阿里 FunASR 模板（v3.2）
# ============================================================
#
#  FunASR: 阿里达摩院开源 ASR 工具包
#  GitHub: https://github.com/modelscope/FunASR
#  pip install funasr modelscope
#
#  支持模型：
#    - paraformer-zh / paraformer-zh-streaming
#    - SenseVoiceSmall（多语言情感识别）
#    - Whisper-large-v3（via funasr）
# ============================================================

from __future__ import annotations

import wave
from typing import Optional

from .base import ASRError, ASRResult, BaseASR


class FunASRASR(BaseASR):
    """FunASR 模板（in-process SDK）。"""

    engine_name = "funasr"
    supports_streaming = True
    supports_language_detection = True

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.model = cfg.get("model", "paraformer-zh")
        self.vad_model = cfg.get("vad_model", "fsmn-vad")
        self.punc_model = cfg.get("punc_model", "ct-punc")
        self.device = cfg.get("device", "cpu")  # funasr 默认 cpu
        self._asr = None

    def _ensure_loaded(self) -> None:
        if self._asr is not None:
            return
        try:
            from funasr import AutoModel  # type: ignore
        except ImportError:
            raise ASRError(
                "FunASR 未安装：pip install funasr modelscope\n"
                "（首次运行会从 ModelScope 下载模型）"
            )
        self._asr = AutoModel(
            model=self.model,
            vad_model=self.vad_model,
            punc_model=self.punc_model,
            device=self.device,
        )

    def _audio_duration(self, path: str) -> float:
        try:
            with wave.open(path, "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0

    def _transcribe(self, audio_path: str, language: Optional[str]) -> ASRResult:
        self._ensure_loaded()
        try:
            result = self._asr.generate(input=audio_path)
        except Exception as e:
            raise ASRError(f"FunASR 转写失败: {e}")
        # FunASR 返回 list[dict]，含 sentence info
        if not result:
            return ASRResult(text="", engine=self.name, audio_path=audio_path)
        first = result[0]
        text = first.get("text", "")
        segs = []
        # 尝试解析 timestamp
        if "timestamp" in first and first["timestamp"]:
            for ts, txt in zip(first["timestamp"], text.split()):
                segs.append({"start": ts[0] / 1000.0, "end": ts[1] / 1000.0, "text": txt})
        return ASRResult(
            text=text,
            segments=segs,
            language="zh" if "zh" in self.model else (language or "auto"),
            engine=self.name,
            audio_path=audio_path,
            duration_sec=self._audio_duration(audio_path),
        )
