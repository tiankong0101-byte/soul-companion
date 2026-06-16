# ============================================================
#  fish_speech.py - FishSpeech TTS 模板（v3.2）
# ============================================================
#
#  FishSpeech: 少样本多语言 TTS（0.5B 参数）
#  GitHub: https://github.com/fishaudio/fish-speech
#  API 服务：
#    python -m tools.api \
#      --listen 0.0.0.0:8180 \
#      --llama-checkpoint-path checkpoints/fish-speech-1.4
# ============================================================

from __future__ import annotations

from typing import Optional

try:
    import requests  # type: ignore
except ImportError:
    raise ImportError("fish_speech 需要 requests：pip install requests")

from .base import BaseTTS, TTSError


class FishSpeechTTS(BaseTTS):
    """FishSpeech 模板：通过 HTTP API 调用本地服务。"""

    engine_name = "fish_speech"
    output_format = "wav"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.base_url = cfg.get("base_url", "http://127.0.0.1:8180").rstrip("/")
        self.reference_audio = cfg.get("reference_audio", "")
        self.reference_text = cfg.get("reference_text", "")
        self.max_new_tokens = cfg.get("max_new_tokens", 1024)
        self.timeout = cfg.get("timeout", 120)

    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        url = f"{self.base_url}/v1/tts"
        payload = {
            "text": text,
            "reference_audio": self.reference_audio,
            "reference_text": self.reference_text,
            "max_new_tokens": self.max_new_tokens,
        }
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise TTSError(f"FishSpeech API 调用失败：{e}")
        if r.status_code != 200:
            raise TTSError(f"FishSpeech HTTP {r.status_code}: {r.text[:200]}")
        with open(output_path, "wb") as f:
            f.write(r.content)
