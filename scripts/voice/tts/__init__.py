"""soul-companion TTS 子模块（v3.2）"""
from .base import BaseTTS, TTSError
from .registry import TTS_REGISTRY, create_tts
from .edge_tts import EdgeTTS

# 可选：尝试导入其他 TTS（包不存在也不影响主程序）
try:
    from .gpt_sovits import GPTSoVITSTTS
except ImportError:
    GPTSoVITSTTS = None

try:
    from .cosyvoice import CosyVoiceTTS
except ImportError:
    CosyVoiceTTS = None

try:
    from .fish_speech import FishSpeechTTS
except ImportError:
    FishSpeechTTS = None

try:
    from .melotts import MeloTTSTTS
except ImportError:
    MeloTTSTTS = None

try:
    from .spark_tts import SparkTTSTTS
except ImportError:
    SparkTTSTTS = None

__all__ = [
    "BaseTTS", "TTSError", "TTS_REGISTRY", "create_tts",
    "EdgeTTS",
    "GPTSoVITSTTS", "CosyVoiceTTS", "FishSpeechTTS",
    "MeloTTSTTS", "SparkTTSTTS",
]
