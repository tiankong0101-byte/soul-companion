# ============================================================
#  edge_tts.py - 微软 Edge TTS（v3.2，refactored from v2.2）
# ============================================================
#
#  - 异步 edge-tts SDK（pip install edge-tts）
#  - 内置 4 种菲菲人设语音
#  - 支持速率、音量、音高调节
# ============================================================

from __future__ import annotations

import asyncio
from typing import List, Optional

from .base import BaseTTS, TTSError


# 菲菲的 4 种语音预设（v2.2 沿用）
FEIFEI_VOICES = {
    "default":  "zh-CN-XiaoxiaoNeural",   # 阳光少女（默认）
    "gentle":   "zh-CN-XiaomengNeural",    # 温柔甜妹
    "mature":   "zh-CN-YunxiNeural",       # 成熟男声（适合陪伴对话的稳重感）
    "night":    "zh-CN-YunyangNeural",     # 深夜电台男声
}


class EdgeTTS(BaseTTS):
    """Microsoft Edge TTS 实现。"""

    engine_name = "edge"
    supports_streaming = True
    output_format = "mp3"

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        # voice 字段可以是字符串，也可以是 FEIFEI_VOICES 的 key
        v = cfg.get("voice", "default")
        if v in FEIFEI_VOICES:
            self.voice = FEIFEI_VOICES[v]
            self.voice_alias = v
        else:
            self.voice = v
            self.voice_alias = None

    def _synthesize(self, text: str, voice: Optional[str], output_path: str) -> None:
        # edge-tts 是 async 包
        try:
            asyncio.run(self._async_synth(text, voice, output_path))
        except RuntimeError:
            # 已有 event loop 的情况
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._async_synth(text, voice, output_path))
            finally:
                loop.close()

    async def _async_synth(self, text: str, voice: Optional[str], output_path: str) -> None:
        try:
            import edge_tts  # type: ignore
        except ImportError:
            raise TTSError("缺少 edge-tts：pip install edge-tts")
        comm = edge_tts.Communicate(
            text, voice=voice or self.voice,
            rate=self.rate, volume=self.volume, pitch=self.pitch,
        )
        await comm.save(output_path)

    @staticmethod
    def list_voices() -> List[str]:
        return list(FEIFEI_VOICES.keys())
