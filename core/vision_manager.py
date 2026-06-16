"""
Soul Companion v4.0 — Vision Manager
视觉管理器：图片理解 + 多模态分析

支持的后端：
  - openai: 使用多模态 LLM（GPT-4o / Qwen-VL 等）
"""
import base64
import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.llm_router import LLMRouter


class VisionManager:
    """视觉管理器

    支持图片理解和描述，用于菲菲的视觉能力：
    1. 接收图片（URL 或 base64）
    2. 调用多模态 LLM 分析图片内容
    3. 返回图片描述/分析结果
    """

    def __init__(self, config: dict):
        self.config = config
        vision_config = config.get("vision", {})
        self.enabled = vision_config.get("enabled", True)
        self.provider = vision_config.get("provider", "openai")
        self.max_image_size = vision_config.get("max_image_size", 1024)

        # 复用 LLM 路由器
        self.llm_router = LLMRouter(config)

        if self.enabled:
            logger.info(f"视觉管理器初始化完成 (provider={self.provider})")
        else:
            logger.info("视觉管理器已禁用")

    async def analyze_image(
        self,
        image_source: str,
        prompt: Optional[str] = None,
    ) -> str:
        """分析图片

        Args:
            image_source: 图片来源（URL 或 base64 编码字符串）
            prompt: 自定义分析提示（默认使用通用描述）

        Returns:
            图片描述/分析结果
        """
        if not self.enabled:
            return "菲菲暂时看不到图片呢~你可以用文字描述给我听哦~"

        analysis_prompt = prompt or "请仔细观察这张图片，然后用温暖自然的语气描述你看到了什么。如果是天哥发的生活照，可以夸夸他。"

        messages = [
            {
                "role": "system",
                "content": "你是菲菲，一个温柔的女生。你正在看天哥发给你的图片。请用温暖的语气回复。",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": analysis_prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": self._normalize_image_source(image_source),
                        },
                    },
                ],
            },
        ]

        try:
            response = await self.llm_router.generate(
                messages=messages,
                max_tokens=512,
                temperature=0.7,
            )
            return response
        except Exception as e:
            logger.error(f"图片分析失败: {e}")
            return "天哥...我看不太清楚这张图片，你能给我讲讲吗？~"

    async def describe_for_emotion(self, image_source: str) -> dict:
        """分析图片情感（用于 Live2D 表情驱动）

        Returns:
            {"description": "图片描述", "emotion": "情感标签"}
        """
        prompt = (
            "观察这张图片的氛围和内容，告诉我：\n"
            "1. 图片主要是什么内容？\n"
            "2. 如果图片中有情绪，是什么情绪？\n"
            "请用简短的话回答。"
        )

        description = await self.analyze_image(image_source, prompt)

        # 简单的情感映射
        emotion = "neutral"
        desc_lower = description.lower()
        if any(w in desc_lower for w in ["开心", "笑", "快乐", "漂亮", "好看"]):
            emotion = "happy"
        elif any(w in desc_lower for w in ["难过", "哭", "伤心"]):
            emotion = "sad"
        elif any(w in desc_lower for w in ["爱", "喜欢", "浪漫", "花"]):
            emotion = "love"
        elif any(w in desc_lower for w in ["惊讶", "天啊", "哇"]):
            emotion = "surprised"

        return {
            "description": description,
            "emotion": emotion,
        }

    def _normalize_image_source(self, source: str) -> str:
        """规范化图片来源为 URL 格式"""
        if source.startswith("http://") or source.startswith("https://"):
            return source
        elif source.startswith("data:image"):
            return source
        elif source.startswith("/9j/") or source.startswith("iVBOR"):
            # 纯 base64，添加前缀
            return f"data:image/jpeg;base64,{source}"
        else:
            # 可能是文件路径
            path = Path(source)
            if path.exists():
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                    suffix = path.suffix.lower().replace(".", "")
                    if suffix in ("jpg", "jpeg"):
                        mime = "image/jpeg"
                    elif suffix == "png":
                        mime = "image/png"
                    elif suffix == "gif":
                        mime = "image/gif"
                    else:
                        mime = "image/jpeg"
                    return f"data:{mime};base64,{b64}"
            return source

    def get_info(self) -> dict:
        """获取视觉模块状态信息"""
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "max_image_size": self.max_image_size,
        }
