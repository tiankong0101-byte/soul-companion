"""
Soul Companion v4.0 — Live2D Controller
Live2D 动画控制器：表情/动作驱动

支持的 Live2D 表情：
  - happy, sad, angry, surprised, neutral, love, shy, gentle

集成方式：
  - 通过 WebSocket 向前端推送表情/动作事件
  - 前端 Live2D SDK 接收事件并播放对应动画
"""
import asyncio
from typing import Dict, Any, Optional

from loguru import logger


# 情感 → Live2D 动作/表情映射
EMOTION_MOTION_MAP = {
    "happy": {"motion": "happy", "expression": "happy"},
    "sad": {"motion": "sad", "expression": "sad"},
    "angry": {"motion": "angry", "expression": "angry"},
    "surprised": {"motion": "surprised", "expression": "surprised"},
    "neutral": {"motion": "idle", "expression": "normal"},
    "love": {"motion": "love", "expression": "love"},
    "shy": {"motion": "shy", "expression": "shy"},
    "gentle": {"motion": "gentle", "expression": "gentle"},
}

# 模式 → 特殊动画
MODE_MOTION_MAP = {
    "comfort": {"motion": "comfort", "expression": "gentle"},
    "listener": {"motion": "nod", "expression": "neutral"},
    "playful": {"motion": "dance", "expression": "happy"},
    "night": {"motion": "sleepy", "expression": "gentle"},
    "healing": {"motion": "hug", "expression": "love"},
    "energize": {"motion": "cheer", "expression": "happy"},
    "intimate": {"motion": "close", "expression": "love"},
    "default": {"motion": "idle", "expression": "normal"},
}


class Live2DController:
    """Live2D 动画控制器

    将菲菲的回复情感和模式转换为 Live2D 动画事件，
    通过 WebSocket 推送到前端。
    """

    def __init__(self, config: dict):
        self.config = config
        live2d_config = config.get("live2d", {})
        self.enabled = live2d_config.get("enabled", True)

        # 自定义情感映射（如果有）
        custom_map = live2d_config.get("emotion_map", {})
        if custom_map:
            for emotion, motion in custom_map.items():
                if emotion in EMOTION_MOTION_MAP:
                    EMOTION_MOTION_MAP[emotion]["expression"] = motion

        if self.enabled:
            logger.info("Live2D 控制器初始化完成")
        else:
            logger.info("Live2D 控制器已禁用")

    def get_emotion_event(self, emotion: str, mode: str = "default") -> Dict[str, Any]:
        """根据情感和模式生成 Live2D 事件

        Args:
            emotion: 情感标签（happy, sad, angry...）
            mode: 交互模式标签（default, comfort...）

        Returns:
            Live2D 事件字典
        """
        if not self.enabled:
            return {"type": "none"}

        # 获取情感对应的动画
        emotion_data = EMOTION_MOTION_MAP.get(emotion, EMOTION_MOTION_MAP["neutral"])
        # 获取模式对应的动画
        mode_data = MODE_MOTION_MAP.get(mode, MODE_MOTION_MAP["default"])

        # 模式优先级高于情感（模式更具体）
        event = {
            "type": "live2d_event",
            "emotion": emotion,
            "mode": mode,
            "motion": mode_data["motion"],
            "expression": mode_data["expression"],
            # 同时发送情感动画作为 fallback
            "fallback_motion": emotion_data["motion"],
            "fallback_expression": emotion_data["expression"],
        }

        logger.debug(f"Live2D 事件: {event}")
        return event

    def get_speaking_event(self, is_speaking: bool = True) -> Dict[str, Any]:
        """口型同步事件"""
        return {
            "type": "live2d_speaking",
            "speaking": is_speaking,
        }

    def get_idle_event(self) -> Dict[str, Any]:
        """待机动画"""
        return {
            "type": "live2d_event",
            "emotion": "neutral",
            "mode": "idle",
            "motion": "idle",
            "expression": "normal",
        }

    def get_info(self) -> Dict[str, Any]:
        """获取控制器状态信息"""
        return {
            "enabled": self.enabled,
            "supported_emotions": list(EMOTION_MOTION_MAP.keys()),
            "supported_modes": list(MODE_MOTION_MAP.keys()),
        }
