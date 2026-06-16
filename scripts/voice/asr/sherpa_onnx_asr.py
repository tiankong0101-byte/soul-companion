# ============================================================
#  sherpa_onnx_asr.py - sherpa-onnx ASR 模板（v3.2）
# ============================================================
#
#  sherpa-onnx: 跨平台 ONNX 离线 ASR（无 PyTorch 依赖）
#  GitHub: https://github.com/k2-fsa/sherpa-onnx
#  pip install sherpa-onnx
#
#  适合：嵌入式 / 边缘设备 / 不想装 PyTorch 的场景
#  支持模型：Whisper / Paraformer / Zipformer / SenseVoice 等 ONNX 版
# ============================================================

from __future__ import annotations

import wave
from typing import Optional

from .base import ASRError, ASRResult, BaseASR


class SherpaOnnxASR(BaseASR):
    """sherpa-onnx ASR 模板。"""

    engine_name = "sherpa_onnx"
    supports_streaming = True
    supports_language_detection = False

    def __init__(self, name: str, cfg: dict):
        super().__init__(name, cfg)
        self.encoder = cfg.get("encoder", "")          # *.onnx
        self.decoder = cfg.get("decoder", "")          # *.onnx
        self.joiner = cfg.get("joiner", "")            # *.onnx
        self.tokens = cfg.get("tokens", "")            # tokens.txt
        self.num_threads = cfg.get("num_threads", 2)
        self.provider = cfg.get("provider", "cpu")     # cpu / cuda / coreml
        self._recognizer = None

    def _ensure_loaded(self) -> None:
        if self._recognizer is not None:
            return
        if not all([self.encoder, self.decoder, self.joiner, self.tokens]):
            raise ASRError(
                "sherpa-onnx 需要配置 encoder/decoder/joiner/tokens 4 个文件路径。\n"
                "请先下载 ONNX 模型，例如：\n"
                "  wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-06-26.tar.bz2"
            )
        try:
            import sherpa_onnx  # type: ignore
        except ImportError:
            raise ASRError("sherpa-onnx 未安装：pip install sherpa-onnx")
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            encoder=self.encoder,
            decoder=self.decoder,
            joiner=self.joiner,
            tokens=self.tokens,
            num_threads=self.num_threads,
            provider=self.provider,
        )

    def _audio_duration(self, path: str) -> float:
        try:
            with wave.open(path, "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 0.0

    def _transcribe(self, audio_path: str, language: Optional[str]) -> ASRResult:
        self._ensure_loaded()
        # 读 wav
        with wave.open(audio_path, "rb") as w:
            assert w.getsampwidth() == 2, "只支持 16-bit PCM"
            sample_rate = w.getframerate()
            audio = w.readframes(w.getnframes())
        import numpy as np  # type: ignore
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        # 简单实现：一次性喂完
        # 生产代码应分块喂并检查 is_endpoint
        while self._recognizer.is_ready(stream):
            self._recognizer.decode_stream(stream)
        text = self._recognizer.get_result(stream)
        return ASRResult(
            text=text, segments=[],
            language=language or "unknown",
            engine=self.name, audio_path=audio_path,
            duration_sec=self._audio_duration(audio_path),
        )
