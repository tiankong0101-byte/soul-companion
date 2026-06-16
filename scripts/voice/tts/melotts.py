# ============================================================
#  melotts.py - MeloTTS 模板（v3.2）
# ============================================================
#
#  MeloTTS: 高质量多语言 TTS（MIT 协议）
#  GitHub: https://github.com/myshell-ai/MeloTTS
#  Python 包: melotts (pip install melotts)
#  注意：MeloTTS 是同步 in-process SDK，没有官方 HTTP API
# ============================================================

from __future__ import annotations

from typing import Optional

from .base import BaseTTS, TTSError


class MeloTTSTTS(BaseTTS):
    """MeloTTS 模板（in-process SDK）。"""

    engine_name = "melotts"
    output_format = "wav"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.language = cfg.get("language", "ZH")  # ZH / EN / JP / KR / ES / FR
        self.speaker = cfg.get("speaker", "ZH_MIX_EN")  # 内置 speaker
        self.speed = cfg.get("speed", 1.0)
        self.device = cfg.get("device", "auto")  # auto / cpu / cuda
        self._tts = None

    def _ensure_loaded(self) -> None:
        if self._tts is not None:
            return
        try:
            from melo.api import TTS  # type: ignore
        except ImportError:
            raise TTSError("MeloTTS 未安装：pip install melotts")
        device = self.device
        if device == "auto":
            try:
                import torch  # type: ignore
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        self._tts = TTS(language=self.language, device=device)
        self._speaker_ids = self._tts.hps.data.spk2id

    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        self._ensure_loaded()
        spk = voice or self.speaker
        if spk not in self._speaker_ids:
            raise TTSError(f"MeloTTS 未知 speaker: {spk}（可用: {list(self._speaker_ids.keys())}）")
        self._tts.tts_to_file(
            text, self._speaker_ids[spk], output_path, speed=self.speed,
        )

    @staticmethod
    def list_voices() -> list:
        try:
            from melo.api import TTS
            tts = TTS(language="ZH")
            return list(tts.hps.data.spk2id.keys())
        except Exception:
            return ["ZH_MIX_EN", "ZH", "EN", "JP", "KR", "ES", "FR"]
