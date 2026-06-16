"""
Soul Companion v5.0 — Image Generator
图片生成模块：AI 画图 + 表情包 + 图片处理

支持的后端：
  - pollinations: Pollinations.ai 免费 API（无需 key）
  - stability: Stability AI（需 API key）
  - local: 本地 Stable Diffusion WebUI API
"""
import io
import os
import json
import uuid
import asyncio
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

import httpx
from loguru import logger


class ImageGenerator:
    """图片生成器

    支持多种后端生成图片：
    1. Pollinations.ai（默认，免费无需 key）
    2. Stability AI（高质量，需 API key）
    3. 本地 SD WebUI（本地部署）
    """

    def __init__(self, config: dict):
        self.config = config
        img_config = config.get("image", {})
        self.provider = img_config.get("provider", "pollinations")
        self.output_dir = Path(config.get("_base_dir", ".")) / "data" / "images"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_width = img_config.get("width", 512)
        self.default_height = img_config.get("height", 512)

        logger.info(f"图片生成器初始化完成 (provider={self.provider})")

    async def generate(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        style: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成图片

        Args:
            prompt: 图片描述
            width: 图片宽度
            height: 图片高度
            style: 风格（如 anime, realistic, watercolor）

        Returns:
            {"image_path": "本地路径", "image_url": "在线URL", "prompt": "使用的提示词"}
        """
        w = width or self.default_width
        h = height or self.default_height

        # 优化提示词
        enhanced_prompt = self._enhance_prompt(prompt, style)

        if self.provider == "pollinations":
            return await self._generate_pollinations(enhanced_prompt, w, h)
        elif self.provider == "stability":
            return await self._generate_stability(enhanced_prompt, w, h)
        elif self.provider == "local":
            return await self._generate_local(enhanced_prompt, w, h)
        else:
            return {"error": f"不支持的图片生成后端: {self.provider}"}

    async def _generate_pollinations(self, prompt: str, width: int, height: int) -> Dict[str, Any]:
        """使用 Pollinations.ai 生成图片（免费）"""
        try:
            # 使用种子确保可复现
            seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % 100000
            encoded_prompt = prompt.replace(" ", "%20").replace(",", "%2C")

            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&seed={seed}&nologo=true"

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    # 保存图片
                    filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{seed}.png"
                    filepath = self.output_dir / filename
                    filepath.write_bytes(resp.content)

                    logger.info(f"图片生成成功: {filepath}")
                    return {
                        "image_path": str(filepath),
                        "image_url": url,
                        "prompt": prompt,
                        "filename": filename,
                    }
                else:
                    logger.error(f"Pollinations API 返回 {resp.status_code}")
                    return {"error": f"图片生成失败（HTTP {resp.status_code}）"}
        except Exception as e:
            logger.error(f"Pollinations 图片生成失败: {e}")
            return {"error": f"图片生成失败: {e}"}

    async def _generate_stability(self, prompt: str, width: int, height: int) -> Dict[str, Any]:
        """使用 Stability AI 生成图片"""
        api_key = self.config.get("image", {}).get("stability_api_key", "")
        if not api_key:
            return {"error": "未配置 Stability AI API Key"}

        try:
            url = "https://api.stability.ai/v1/generation/stable-diffusion-xl/text-to-image"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text_prompts": [{"text": prompt, "weight": 1}],
                "cfg_scale": 7,
                "height": height,
                "width": width,
                "steps": 30,
                "samples": 1,
            }

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload, headers=headers)
                data = resp.json()

            if "artifacts" in data:
                import base64
                img_b64 = data["artifacts"][0]["base64"]
                img_bytes = base64.b64decode(img_b64)

                filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                filepath = self.output_dir / filename
                filepath.write_bytes(img_bytes)

                return {
                    "image_path": str(filepath),
                    "image_url": None,
                    "prompt": prompt,
                    "filename": filename,
                }
            else:
                return {"error": f"Stability API 错误: {data}"}
        except Exception as e:
            logger.error(f"Stability 图片生成失败: {e}")
            return {"error": f"图片生成失败: {e}"}

    async def _generate_local(self, prompt: str, width: int, height: int) -> Dict[str, Any]:
        """使用本地 Stable Diffusion WebUI API"""
        sd_url = self.config.get("image", {}).get("local_url", "http://127.0.0.1:7860")

        try:
            url = f"{sd_url}/sdapi/v1/txt2img"
            payload = {
                "prompt": prompt,
                "negative_prompt": "ugly, blurry, low quality, deformed",
                "width": width,
                "height": height,
                "steps": 25,
                "cfg_scale": 7,
            }

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload)
                data = resp.json()

            if "images" in data:
                import base64
                img_b64 = data["images"][0]
                img_bytes = base64.b64decode(img_b64)

                filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                filepath = self.output_dir / filename
                filepath.write_bytes(img_bytes)

                return {
                    "image_path": str(filepath),
                    "image_url": None,
                    "prompt": prompt,
                    "filename": filename,
                }
            else:
                return {"error": "本地 SD WebUI 返回错误"}
        except Exception as e:
            logger.error(f"本地 SD 生成失败: {e}")
            return {"error": f"本地图片生成失败，请检查 SD WebUI 是否启动: {e}"}

    def _enhance_prompt(self, prompt: str, style: Optional[str] = None) -> str:
        """优化图片提示词"""
        # 添加质量词
        quality_words = "high quality, detailed, beautiful"

        style_map = {
            "anime": "anime style, manga, vibrant colors",
            "realistic": "photorealistic, 8k, detailed, natural lighting",
            "watercolor": "watercolor painting, soft colors, artistic",
            "pixel": "pixel art, retro game style, 16-bit",
            "oil": "oil painting, classical art, rich textures",
            "cute": "kawaii, cute, chibi, pastel colors",
            "dark": "dark fantasy, gothic, dramatic lighting",
        }

        style_suffix = style_map.get(style, "") if style else ""

        enhanced = f"{prompt}, {quality_words}"
        if style_suffix:
            enhanced += f", {style_suffix}"

        return enhanced

    def get_info(self) -> dict:
        """获取图片生成模块信息"""
        return {
            "provider": self.provider,
            "output_dir": str(self.output_dir),
            "default_size": f"{self.default_width}x{self.default_height}",
            "generated_count": len(list(self.output_dir.glob("img_*.png"))),
        }
