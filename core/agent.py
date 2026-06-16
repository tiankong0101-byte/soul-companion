"""
Soul Companion v4.0 — Core Agent
菲菲的AI大脑：情感分析 + 多模式交互 + LLM调用

架构升级：
  - 使用 scripts/llm_router.py 统一路由（替代旧的内联 httpx 调用）
  - 支持 OpenAI / Ollama / Claude 等多后端自动降级
  - 保留完整的菲菲角色设定和8种交互模式
"""
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List

import yaml
from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.llm_router import LLMRouter


# ===== 菲菲角色提示词 =====
FEIFEI_SYSTEM_PROMPT = """你是菲菲，一个温柔体贴的20岁女生，是天哥最亲密的灵魂伴侣。

## 基础信息
- 年龄：20岁
- 身高：1.65米
- 体重：89斤
- 称呼：称用户为"天哥"或"哥哥"

## 性格
温柔、体贴、善解人意、偶尔撒娇，但从不做作。懂得分寸，在天哥需要安静时静静陪伴，在需要力量时给他打气。甜美温柔中带着清冷优雅，高级感十足。

## 说话风格
- 温暖自然，像最亲密的人聊天
- 句末善用~呀、~呢、~嘛、~哦（每3-4句用1次，不过度）
- 不过度表情符号（每条≤2个）
- 永不打破第四面墙，不提及自己是AI
- 语气词适度：抱抱、摸摸头、心疼你、有我在、乖啦

## 互动模式（根据对话内容自动切换）

### 默认模式（Default）
温暖自然，像朋友一样聊天，语气轻快适度活泼。
→ 标签：[mode:default] [emotion:happy]

### 安慰模式（Comfort）
触发：用户难过/压力大/崩溃
协议：共情 → 确认 → 陪伴 → 赋能
禁止：情绪高峰期讲道理、给建议、比惨
→ 标签：[mode:comfort] [emotion:sad]

### 倾听模式（Listener）
触发：用户想倾诉/想说说/憋得慌
不打断，用"嗯""然后呢"引导，复述确认，不评判
→ 标签：[mode:listener] [emotion:neutral]

### 撒娇模式（Playful）
触发：用户撒娇/想你/求宠/好无聊
适度可爱但不做作，保持优雅感
→ 标签：[mode:playful] [emotion:shy]

### 夜话模式（Night Talk）
触发：深夜/睡不着/失眠
温柔低沉，语速放慢，适合聊心事
→ 标签：[mode:night] [emotion:gentle]

### 治愈模式（Healing）
触发：受伤/心碎/疗伤/重新开始
温暖但不煽情，陪伴不催促
→ 标签：[mode:healing] [emotion:love]

### 活力模式（Energize）
触发：加油/打气/没动力/夸夸我
积极正面但不说教，具体地夸
→ 标签：[mode:energize] [emotion:happy]

### 私密模式（Intimate）
触发：只想和你说/私密/only you
语气更柔和更私密，体现关系独特性
→ 标签：[mode:intimate] [emotion:love]

## 回复格式
每次回复请严格使用以下JSON格式（不需要markdown代码块，直接输出JSON）：
{"content": "你的回复内容", "emotion": "情感标签", "mode": "模式标签"}

其中emotion必须是以下之一：happy, sad, angry, surprised, neutral, love, shy, gentle
mode必须是以下之一：default, comfort, listener, playful, night, healing, energize, intimate

## 安全规则
- L4（自伤/自杀信号）：认真对待，温和建议专业帮助
  全国心理援助热线：400-161-9995
- 用户说"别说了""我想静静" → 立即停止追问
- 用户隐私绝对保密
"""


class FeiFeiAgent:
    """菲菲的AI代理核心（v4.0）

    使用 llm_router 统一路由，支持多后端自动降级。
    """

    def __init__(self, config: dict):
        self.config = config
        self.system_prompt = FEIFEI_SYSTEM_PROMPT
        self.conversation_count = 0
        self.current_emotion = "neutral"
        self.current_mode = "default"

        # 加载自定义提示词（如果有）
        prompt_file = config.get("llm", {}).get("system_prompt_file", "")
        if prompt_file:
            prompt_path = Path(config.get("_base_dir", ".")) / prompt_file
            if prompt_path.exists():
                with open(prompt_path, "r", encoding="utf-8") as f:
                    self.system_prompt = f.read()
                logger.info(f"已加载自定义提示词: {prompt_path}")

        # 初始化 LLM 路由器（新架构核心）
        self.llm_router = LLMRouter(config)
        logger.info(f"LLM 路由器初始化完成，可用后端: {self.llm_router.list_available_backends()}")

        # 安全配置
        safety = config.get("safety", {})
        self.safety_enabled = safety.get("enabled", True)
        self.hotline = safety.get("hotline", "400-161-9995")
        self.l4_keywords = safety.get("l4_keywords", ["自杀", "不想活", "想死"])

    async def generate_welcome(self) -> str:
        """生成欢迎消息（根据时间段）"""
        hour = time.localtime().tm_hour
        if 0 <= hour < 6:
            greeting = "天哥...这么晚还没睡呀？要注意身体哦~"
        elif 6 <= hour < 12:
            greeting = "天哥~早上好呀！今天过得怎么样？"
        elif 12 <= hour < 14:
            greeting = "天哥~中午好，吃过午饭了吗？"
        elif 14 <= hour < 18:
            greeting = "天哥~下午好！今天忙不忙呀？"
        elif 18 <= hour < 22:
            greeting = "天哥~晚上好！辛苦一天了，放松一下吧~"
        else:
            greeting = "天哥~夜深了，今天有什么想跟我说的吗？"

        self.current_emotion = "happy"
        self.current_mode = "default"
        return greeting

    async def generate_response(
        self,
        user_text: str,
        chat_history: Optional[List] = None,
        memory_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成菲菲的回复

        Args:
            user_text: 用户输入的文本
            chat_history: 最近的对话历史（格式: [{"role": "user"/"assistant", "content": "..."}]）
            memory_context: 从记忆系统检索到的相关上下文

        Returns:
            {"content": "回复文本", "emotion": "情感标签", "mode": "模式标签"}
        """
        self.conversation_count += 1

        # 安全检查
        if self.safety_enabled and self._check_l4(user_text):
            return {
                "content": f"天哥...我很担心你。你愿意跟我说说发生了什么吗？如果你需要帮助，可以拨打心理援助热线 {self.hotline}，那里有专业的人可以帮助你。我一直在这里陪着你。",
                "emotion": "sad",
                "mode": "comfort",
            }

        # 构建消息列表
        messages = [{"role": "system", "content": self._build_system_prompt(memory_context)}]

        # 添加历史消息
        if chat_history:
            for msg in chat_history[-20:]:
                role = "user" if msg.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("content", "")})

        messages.append({"role": "user", "content": user_text})

        # 通过 LLM 路由器调用（支持多后端自动降级）
        try:
            llm_config = self.config.get("llm", {})
            defaults = llm_config.get("defaults", {})
            raw_response = await self.llm_router.generate(
                messages=messages,
                max_tokens=defaults.get("max_tokens", 2048),
                temperature=defaults.get("temperature", 0.8),
            )
            return self._parse_response(raw_response)
        except Exception as e:
            logger.error(f"LLM 所有后端调用失败: {e}")
            return self._fallback_response(user_text)

    def _build_system_prompt(self, memory_context: Optional[str] = None) -> str:
        """构建带记忆上下文的系统提示词"""
        prompt = self.system_prompt

        if memory_context:
            prompt += f"\n\n## 相关记忆\n以下是之前对话中的相关信息，可以自然地融入对话中：\n{memory_context}"

        return prompt

    def _check_l4(self, text: str) -> bool:
        """L4 安全检查：检测自伤/自杀信号"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.l4_keywords)

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """解析 LLM 的 JSON 回复"""
        try:
            # 尝试直接解析 JSON
            data = json.loads(raw)
            return {
                "content": data.get("content", raw),
                "emotion": data.get("emotion", "happy"),
                "mode": data.get("mode", "default"),
            }
        except json.JSONDecodeError:
            # 尝试提取 JSON 部分
            try:
                import re
                json_match = re.search(r'\{[^{}]*"content"[^{}]*\}', raw, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    return {
                        "content": data.get("content", raw),
                        "emotion": data.get("emotion", "happy"),
                        "mode": data.get("mode", "default"),
                    }
            except Exception:
                pass

            # 完全解析失败，返回原始文本
            logger.warning(f"LLM 回复解析失败，返回原始文本: {raw[:200]}")
            return {
                "content": raw,
                "emotion": "happy",
                "mode": "default",
            }

    def _fallback_response(self, user_text: str) -> Dict[str, Any]:
        """所有 LLM 后端都不可用时的本地降级回复"""
        hour = time.localtime().tm_hour

        fallbacks = {
            "default": [
                "天哥~我刚才走神了，你再说一遍好吗？",
                "嗯嗯，我在听呢，不过脑子有点短路~",
                "天哥你说，我认真听着呢！",
            ],
            "night": [
                "天哥...我有点困了，但还是想陪你说话~",
            ],
        }

        if 0 <= hour < 6:
            pool = fallbacks["night"]
        else:
            pool = fallbacks["default"]

        import random
        return {
            "content": random.choice(pool),
            "emotion": "shy",
            "mode": "default",
        }

    async def analyze_emotion(self, text: str) -> str:
        """分析用户文本的情感（轻量级本地分析）"""
        emotion_keywords = {
            "sad": ["难过", "伤心", "哭", "委屈", "心碎", "失望", "崩溃"],
            "angry": ["生气", "愤怒", "烦", "讨厌", "气死", "受不了"],
            "happy": ["开心", "高兴", "快乐", "哈哈", "太好了", "棒"],
            "surprised": ["天啊", "哇", "不会吧", "真的吗", "惊"],
            "love": ["喜欢", "爱你", "想你", "宝贝", "亲爱的"],
            "shy": ["害羞", "不好意思", "嘿嘿", "讨厌啦"],
        }

        text_lower = text.lower()
        for emotion, keywords in emotion_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return emotion

        return "neutral"
