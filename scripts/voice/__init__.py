"""soul-companion 语音模块（v3.2）"""
from .tts import TTS_REGISTRY, BaseTTS, create_tts
from .asr import ASR_REGISTRY, BaseASR, create_asr

__all__ = [
    "TTS_REGISTRY", "BaseTTS", "create_tts",
    "ASR_REGISTRY", "BaseASR", "create_asr",
]
__version__ = "3.2.0"
