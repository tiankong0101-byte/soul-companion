# ============================================================
#  gpt_sovits.py - GPT-SoVITS TTS 模板（v3.2）
# ============================================================
#
#  GPT-SoVITS: 少样本中文语音克隆 + TTS
#  GitHub: https://github.com/RVC-Boss/GPT-SoVITS
#  推荐部署方式：使用官方 WebUI + API 模式启动
#
#  启动 API 服务：
#    python api.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
#
#  API 端点：
#    POST /tts  (text, text_language, ref_audio_path, prompt_text, prompt_language)
# ============================================================

from __future__ import annotations

import json
from typing import Optional

try:
    import requests  # type: ignore
except ImportError:
    raise ImportError("gpt_sovits 需要 requests：pip install requests")

from .base import BaseTTS, TTSError


class GPTSoVITSTTS(BaseTTS):
    """GPT-SoVITS 模板：通过 HTTP API 调用本地服务。"""

    engine_name = "gpt_sovits"
    output_format = "wav"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.base_url = cfg.get("base_url", "http://127.0.0.1:9880").rstrip("/")
        self.text_language = cfg.get("text_language", "zh")  # zh / en / ja
        self.prompt_language = cfg.get("prompt_language", "zh")
        self.ref_audio_path = cfg.get("ref_audio_path", "")    # 参考音频路径
        self.prompt_text = cfg.get("prompt_text", "")          # 参考音频对应文本
        self.timeout = cfg.get("timeout", 60)

    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        if not self.ref_audio_path or not self.prompt_text:
            raise TTSError("GPT-SoVITS 需要配置 ref_audio_path 和 prompt_text（参考音频 + 文本）")
        url = f"{self.base_url}/tts"
        payload = {
            "text": text,
            "text_language": self.text_language,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_language": self.prompt_language,
        }
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise TTSError(f"GPT-SoVITS API 调用失败：{e}")
        if r.status_code != 200:
            raise TTSError(f"GPT-SoVITS HTTP {r.status_code}: {r.text[:200]}")
        with open(output_path, "wb") as f:
            f.write(r.content)
