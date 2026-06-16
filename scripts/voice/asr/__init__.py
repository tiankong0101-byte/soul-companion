"""soul-companion ASR 子模块（v3.2）"""
from .base import BaseASR, ASRResult, ASRError
from .registry import ASR_REGISTRY, create_asr
from .whisper_asr import WhisperASR

try:
    from .funasr_asr import FunASRASR
except ImportError:
    FunASRASR = None

try:
    from .sherpa_onnx_asr import SherpaOnnxASR
except ImportError:
    SherpaOnnxASR = None

__all__ = [
    "BaseASR", "ASRResult", "ASRError", "ASR_REGISTRY", "create_asr",
    "WhisperASR", "FunASRASR", "SherpaOnnxASR",
]
