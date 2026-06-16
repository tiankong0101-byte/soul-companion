# ============================================================
#  registry.py - ASR 工厂注册表（v3.2）
# ============================================================

from __future__ import annotations

from typing import Dict, Type

from .base import ASRError, BaseASR
from .whisper_asr import WhisperASR

_OPTIONAL = {}

try:
    from .funasr_asr import FunASRASR
    _OPTIONAL["funasr"] = FunASRASR
except ImportError:
    pass

try:
    from .sherpa_onnx_asr import SherpaOnnxASR
    _OPTIONAL["sherpa_onnx"] = SherpaOnnxASR
except ImportError:
    pass


ASR_REGISTRY: Dict[str, Type[BaseASR]] = {
    "whisper": WhisperASR,
    **_OPTIONAL,
}


def create_asr(name: str, cfg: dict) -> BaseASR:
    engine = cfg.get("engine", "whisper")
    cls = ASR_REGISTRY.get(engine)
    if cls is None:
        available = list(ASR_REGISTRY.keys())
        raise ASRError(f"未知 ASR 引擎: {engine}（可用: {available}）")
    return cls(name, cfg)
