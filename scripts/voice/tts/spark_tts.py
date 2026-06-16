# ============================================================
#  spark_tts.py - SparkTTS 模板（v3.2）
# ============================================================
#
#  SparkTTS: 字节跳动开源的高质量 TTS（基于 0.5B LLM）
#  GitHub: https://github.com/SparkAudio/Spark-TTS
#  使用方式：本地加载模型 + 推理（in-process）
# ============================================================

from __future__ import annotations

from typing import Optional

from .base import BaseTTS, TTSError


class SparkTTSTTS(BaseTTS):
    """SparkTTS 模板。"""

    engine_name = "spark_tts"
    output_format = "wav"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.model_dir = cfg.get("model_dir", "models/Spark-TTS-0.5B")
        self.device = cfg.get("device", "auto")
        self._model = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sparktts import SparkTTS  # type: ignore  # 官方 pip 包名待确认
        except ImportError:
            raise TTSError(
                "SparkTTS 未安装或包名不匹配。请访问 https://github.com/SparkAudio/Spark-TTS "
                "按 README 自行部署（目前以源码方式使用）"
            )
        device = self.device
        if device == "auto":
            try:
                import torch  # type: ignore
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        self._model = SparkTTS(model_dir=self.model_dir, device=device)

    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        self._ensure_loaded()
        self._model.synthesize(text=text, output_path=output_path, speaker=voice)
