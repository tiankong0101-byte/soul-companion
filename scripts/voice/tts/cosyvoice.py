# ============================================================
#  cosyvoice.py - 阿里 CosyVoice TTS 模板（v3.2）
# ============================================================
#
#  CosyVoice: 阿里达摩院开源多语言 TTS，支持声音克隆
#  GitHub: https://github.com/FunAudioLLM/CosyVoice
#  Python 包: cosyvoice (pip install -U cosyvoice)
#  或通过 HTTP API 调用 cosyvoice-runtime 服务
#
#  启动 API 服务（官方 docker）：
#    docker run -d --gpus all -p 50000:50000 \
#      registry.cn-hangzhou.aliyuncs.com/funaudio/cosyvoice:v1
# ============================================================

from __future__ import annotations

from typing import Optional

try:
    import requests  # type: ignore
except ImportError:
    raise ImportError("cosyvoice 需要 requests：pip install requests")

from .base import BaseTTS, TTSError


class CosyVoiceTTS(BaseTTS):
    """CosyVoice 模板：通过 HTTP API 调用本地服务。"""

    engine_name = "cosyvoice"
    output_format = "wav"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.base_url = cfg.get("base_url", "http://127.0.0.1:50000").rstrip("/")
        self.mode = cfg.get("mode", "zero_shot")  # sft / zero_shot / cross_lingual / instruct
        self.spk_id = cfg.get("spk_id", "中文女")  # 内置音色名
        self.prompt_text = cfg.get("prompt_text", "")
        self.prompt_wav = cfg.get("prompt_wav", "")  # 6s+ 参考音频
        self.instruct_text = cfg.get("instruct_text", "")
        self.timeout = cfg.get("timeout", 60)

    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        url = f"{self.base_url}/inference_{self.mode}"
        if self.mode == "sft":
            payload = {"tts_text": text, "spk_id": self.spk_id}
        elif self.mode == "zero_shot":
            payload = {
                "tts_text": text,
                "prompt_text": self.prompt_text,
                "prompt_wav": self.prompt_wav,
            }
        elif self.mode == "cross_lingual":
            payload = {"tts_text": text, "prompt_wav": self.prompt_wav}
        elif self.mode == "instruct":
            payload = {
                "tts_text": text,
                "spk_id": self.spk_id,
                "instruct_text": self.instruct_text,
            }
        else:
            raise TTSError(f"未知 CosyVoice mode: {self.mode}")
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise TTSError(f"CosyVoice API 调用失败：{e}")
        if r.status_code != 200:
            raise TTSError(f"CosyVoice HTTP {r.status_code}: {r.text[:200]}")
        with open(output_path, "wb") as f:
            f.write(r.content)
