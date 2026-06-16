"""
Soul Companion v4.0 — ASR Manager
语音识别管理器：支持多后端语音转文字

支持的后端：
  - funasr: 阿里 FunASR（本地离线，高精度）
  - whisper: OpenAI Whisper（本地离线，多语言）
"""
import io
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, BinaryIO

from loguru import logger


@dataclass
class ASRResult:
    """语音识别结果"""
    text: str
    confidence: float = 0.0
    language: str = "zh"
    duration_ms: int = 0


class ASRBackend(ABC):
    """ASR 后端基类"""

    @abstractmethod
    async def recognize(self, audio_data: bytes, language: str = "zh") -> ASRResult:
        """识别音频"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查后端是否可用"""
        ...


class FunASRBackend(ASRBackend):
    """阿里 FunASR 后端（本地离线）"""

    def __init__(self, model: str = "paraformer-zh"):
        self.model = model
        self._model_instance = None

    def is_available(self) -> bool:
        try:
            from funasr import AutoModel
            return True
        except ImportError:
            return False

    async def recognize(self, audio_data: bytes, language: str = "zh") -> ASRResult:
        try:
            from funasr import AutoModel

            if self._model_instance is None:
                self._model_instance = AutoModel(model=self.model)

            # FunASR 需要文件路径，写入临时文件
            import tempfile
            import os

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_data)
                    tmp_path = f.name

                result = self._model_instance.generate(input=tmp_path)
                text = result[0]["text"] if result else ""
                return ASRResult(text=text, confidence=0.9, language=language)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"FunASR 识别失败: {e}")
            raise


class WhisperBackend(ASRBackend):
    """OpenAI Whisper 后端（本地离线）"""

    def __init__(self, model_size: str = "medium"):
        self.model_size = model_size
        self._model = None

    def is_available(self) -> bool:
        try:
            import whisper
            return True
        except ImportError:
            return False

    async def recognize(self, audio_data: bytes, language: str = "zh") -> ASRResult:
        try:
            import whisper

            if self._model is None:
                self._model = whisper.load_model(self.model_size)

            # 写入临时文件
            import tempfile
            import os

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_data)
                    tmp_path = f.name

                result = self._model.transcribe(
                    tmp_path,
                    language=language if language != "auto" else None,
                )
                text = result.get("text", "")
                return ASRResult(text=text, confidence=0.85, language=language)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"Whisper 识别失败: {e}")
            raise


class ASRManager:
    """语音识别管理器

    自动选择可用的 ASR 后端，支持降级：
    funasr → whisper → 失败
    """

    def __init__(self, config: dict):
        self.config = config
        voice_config = config.get("voice", {}).get("asr", {})
        self.provider = voice_config.get("provider", "funasr")
        self.model = voice_config.get("model", "paraformer-zh")
        self.language = voice_config.get("language", "zh")

        # 初始化后端
        self.backends = {
            "funasr": FunASRBackend(model=self.model),
            "whisper": WhisperBackend(),
        }

        # 检查可用后端
        available = [name for name, b in self.backends.items() if b.is_available()]
        logger.info(f"ASR 可用后端: {available}")

        if not available:
            logger.warning("没有可用的 ASR 后端！请安装 funasr 或 openai-whisper")

    async def recognize(
        self,
        audio_data: bytes,
        language: Optional[str] = None,
    ) -> ASRResult:
        """识别语音

        Args:
            audio_data: 音频数据（WAV 格式）
            language: 语言代码（默认使用配置值）

        Returns:
            ASRResult 识别结果
        """
        lang = language or self.language

        # 按优先级尝试后端
        order = [self.provider] + [b for b in self.backends if b != self.provider]

        for backend_name in order:
            backend = self.backends.get(backend_name)
            if backend and backend.is_available():
                try:
                    result = await backend.recognize(audio_data, lang)
                    logger.debug(f"ASR[{backend_name}] 识别成功: {result.text[:50]}")
                    return result
                except Exception as e:
                    logger.warning(f"ASR[{backend_name}] 失败: {e}")
                    continue

        raise RuntimeError("所有 ASR 后端都不可用")

    def get_info(self) -> dict:
        """获取 ASR 状态信息"""
        return {
            "provider": self.provider,
            "model": self.model,
            "language": self.language,
            "available_backends": [name for name, b in self.backends.items() if b.is_available()],
        }
