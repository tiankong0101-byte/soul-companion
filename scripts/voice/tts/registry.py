# ============================================================
#  registry.py - TTS 工厂注册表（v3.2）
# ============================================================

from __future__ import annotations

from typing import Dict, Type

from .base import BaseTTS, TTSError
from .edge_tts import EdgeTTS

# 尝试导入其他 TTS
_OPTIONAL_IMPORTS = {}

try:
    from .gpt_sovits import GPTSoVITSTTS
    _OPTIONAL_IMPORTS["gpt_sovits"] = GPTSoVITSTTS
except ImportError:
    pass

try:
    from .cosyvoice import CosyVoiceTTS
    _OPTIONAL_IMPORTS["cosyvoice"] = CosyVoiceTTS
except ImportError:
    pass

try:
    from .fish_speech import FishSpeechTTS
    _OPTIONAL_IMPORTS["fish_speech"] = FishSpeechTTS
except ImportError:
    pass

try:
    from .melotts import MeloTTSTTS
    _OPTIONAL_IMPORTS["melotts"] = MeloTTSTTS
except ImportError:
    pass

try:
    from .spark_tts import SparkTTSTTS
    _OPTIONAL_IMPORTS["spark_tts"] = SparkTTSTTS
except ImportError:
    pass


# 注册表
TTS_REGISTRY: Dict[str, Type[BaseTTS]] = {
    "edge": EdgeTTS,
    **_OPTIONAL_IMPORTS,
}


def create_tts(name: str, cfg: dict) -> BaseTTS:
    """根据 cfg.engine 创建对应 TTS 客户端。"""
    engine = cfg.get("engine", "edge")
    cls = TTS_REGISTRY.get(engine)
    if cls is None:
        available = list(TTS_REGISTRY.keys())
        raise TTSError(f"未知 TTS 引擎: {engine}（可用: {available}）")
    return cls(name, cfg)
