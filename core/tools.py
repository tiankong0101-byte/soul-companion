"""
Soul Companion v5.0 — Tool Calling Framework
工具调用框架：天气 / 搜索 / 计算 / 网页抓取 / 翻译等

架构：
  - 每个工具是一个 Tool 子类，实现 execute() 方法
  - ToolManager 管理所有工具的注册、查找、执行
  - Agent 在回复时可以调用工具获取实时信息
"""
import re
import json
import math
import asyncio
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from urllib.parse import quote_plus

import httpx
from loguru import logger


# ===== 工具基类 =====
class Tool(ABC):
    """工具基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（给 LLM 看的）"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """参数 JSON Schema"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """执行工具，返回结果文本"""
        ...

    def to_schema(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ===== 天气工具 =====
class WeatherTool(Tool):
    """查询天气（使用 wttr.in 免费 API）"""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "查询指定城市的天气信息，包括温度、天气状况、风力等。支持中文城市名。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，如 '北京', '上海', 'Shanghai'",
                },
            },
            "required": ["city"],
        }

    async def execute(self, city: str = "北京") -> str:
        """查询天气"""
        try:
            url = f"https://wttr.in/{quote_plus(city)}?format=j1&lang=zh"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers={"Accept-Language": "zh-CN"})
                data = resp.json()

            current = data.get("current_condition", [{}])[0]
            temp = current.get("temp_C", "未知")
            feels_like = current.get("FeelsLikeC", "未知")
            humidity = current.get("humidity", "未知")
            wind_speed = current.get("windspeedKmph", "未知")
            desc_list = current.get("lang_zh", current.get("weatherDesc", [{}]))
            desc = desc_list[0].get("value", "未知") if desc_list else "未知"

            # 获取未来天气
            forecast = data.get("weather", [])
            tomorrow = forecast[1] if len(forecast) > 1 else None

            result = f"🏙️ {city} 当前天气：\n"
            result += f"  🌡️ 温度：{temp}°C（体感 {feels_like}°C）\n"
            result += f"  ☁️ 天气：{desc}\n"
            result += f"  💧 湿度：{humidity}%\n"
            result += f"  🌬️ 风速：{wind_speed} km/h\n"

            if tomorrow:
                max_temp = tomorrow.get("maxtempC", "未知")
                min_temp = tomorrow.get("mintempC", "未知")
                result += f"\n📅 明日预告：{min_temp}°C ~ {max_temp}°C"

            return result
        except Exception as e:
            logger.error(f"天气查询失败: {e}")
            return f"抱歉天哥，查询{city}天气时出了点问题~"


# ===== 搜索工具 =====
class SearchTool(Tool):
    """网络搜索（使用 DuckDuckGo Lite）"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "搜索互联网获取最新信息。用于回答实时问题，如新闻、资料、知识等。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量（默认5条）",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, max_results: int = 5) -> str:
        """执行搜索"""
        try:
            url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}&kl=cn-zh"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers, follow_redirects=True)
                html = resp.text

            # 简单解析搜索结果
            results = []
            # 提取搜索结果块
            links = re.findall(r'<a[^>]*class="result-link"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
            snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)

            for i, (link, title) in enumerate(links[:max_results]):
                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                snippet = ""
                if i < len(snippets):
                    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                results.append(f"{i+1}. **{title_clean}**\n   {snippet}\n   🔗 {link}")

            if results:
                return f"🔍 搜索「{query}」的结果：\n\n" + "\n\n".join(results)
            else:
                return f"天哥，搜索「{query}」没有找到相关结果呢~换一个关键词试试？"

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return f"抱歉天哥，搜索出了点问题~"


# ===== 计算器工具 =====
class CalculatorTool(Tool):
    """数学计算器"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "执行数学计算。支持基本运算(+,-,*,/)、幂运算(**)、三角函数(sin/cos/tan)、对数(log)、平方根(sqrt)等。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2+3*4', 'sqrt(144)', 'sin(3.14/2)'",
                },
            },
            "required": ["expression"],
        }

    async def execute(self, expression: str) -> str:
        """安全计算数学表达式"""
        try:
            # 允许的安全函数
            safe_dict = {
                "abs": abs, "round": round, "min": min, "max": max,
                "int": int, "float": float,
                "sin": math.sin, "cos": math.cos, "tan": math.tan,
                "asin": math.asin, "acos": math.acos, "atan": math.atan,
                "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
                "log2": math.log2, "pow": math.pow,
                "pi": math.pi, "e": math.e,
                "ceil": math.ceil, "floor": math.floor,
            }

            # 清理表达式
            expr = expression.strip()
            expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")

            result = eval(expr, {"__builtins__": {}}, safe_dict)

            # 格式化结果
            if isinstance(result, float):
                if result == int(result) and abs(result) < 1e15:
                    result = int(result)
                else:
                    result = round(result, 10)

            return f"📐 计算结果：{expression} = {result}"
        except ZeroDivisionError:
            return "天哥，除数不能为零哦~"
        except Exception as e:
            return f"天哥，这个算式我算不出来呢~({e})"


# ===== 翻译工具 =====
class TranslateTool(Tool):
    """翻译工具（使用免费 API）"""

    @property
    def name(self) -> str:
        return "translate"

    @property
    def description(self) -> str:
        return "翻译文本。支持中英互译，也可翻译为其他语言。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要翻译的文本",
                },
                "target_lang": {
                    "type": "string",
                    "description": "目标语言代码：'zh'（中文）或 'en'（英文），默认自动判断",
                },
            },
            "required": ["text"],
        }

    async def execute(self, text: str, target_lang: str = "auto") -> str:
        """执行翻译"""
        try:
            # 使用 MyMemory 免费翻译 API
            # 自动检测语言
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
            if target_lang == "auto":
                target = "en" if has_chinese else "zh-CN"
            elif target_lang == "zh":
                target = "zh-CN"
            else:
                target = target_lang

            url = f"https://api.mymemory.translated.net/get?q={quote_plus(text)}&langpair={'zh-CN' if has_chinese else 'en'}|{target}"

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                data = resp.json()

            translated = data.get("responseData", {}).get("translatedText", "")
            if translated:
                return f"🌐 翻译结果：{translated}"
            else:
                return "天哥，翻译出了点问题~"
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return f"抱歉天哥，翻译失败了~"


# ===== 时间工具 =====
class DateTimeTool(Tool):
    """日期时间查询"""

    @property
    def name(self) -> str:
        return "get_datetime"

    @property
    def description(self) -> str:
        return "获取当前日期、时间、星期几。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self) -> str:
        now = datetime.now()
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[now.weekday()]

        result = f"🕐 当前时间：\n"
        result += f"  📅 日期：{now.year}年{now.month}月{now.day}日\n"
        result += f"  ⏰ 时间：{now.strftime('%H:%M:%S')}\n"
        result += f"  📆 星期：{weekday}"
        return result


# ===== 网页抓取工具 =====
class WebFetchTool(Tool):
    """抓取网页内容"""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "获取指定 URL 的网页文本内容。用于阅读文章、获取信息等。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的网页 URL",
                },
                "max_length": {
                    "type": "integer",
                    "description": "最大返回字符数（默认2000）",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, max_length: int = 2000) -> str:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                text = resp.text

            # 移除 HTML 标签
            clean = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
            clean = re.sub(r'<[^>]+>', ' ', clean)
            clean = re.sub(r'\s+', ' ', clean).strip()

            if len(clean) > max_length:
                clean = clean[:max_length] + "..."

            return f"📄 网页内容（{url}）：\n\n{clean}"
        except Exception as e:
            logger.error(f"网页抓取失败: {e}")
            return f"抱歉天哥，抓取网页失败了~"


# ===== 随机工具 =====
class RandomTool(Tool):
    """随机数/随机选择"""

    @property
    def name(self) -> str:
        return "random"

    @property
    def description(self) -> str:
        return "生成随机数，或从列表中随机选择。比如掷骰子、随机选一个等。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["number", "choice", "dice"],
                    "description": "'number'=随机整数, 'choice'=从列表随机选, 'dice'=掷骰子",
                },
                "min_val": {
                    "type": "integer",
                    "description": "最小值（number模式），默认1",
                },
                "max_val": {
                    "type": "integer",
                    "description": "最大值（number模式），默认100",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "选项列表（choice模式）",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, min_val: int = 1, max_val: int = 100, options: list = None) -> str:
        import random
        if action == "dice":
            result = random.randint(1, 6)
            return f"🎲 骰子结果：{result}"
        elif action == "choice":
            if not options:
                return "天哥，你没有给选项呀~"
            pick = random.choice(options)
            return f"🎯 随机选择了：{pick}"
        elif action == "number":
            result = random.randint(min_val, max_val)
            return f"🔢 随机数（{min_val}~{max_val}）：{result}"
        else:
            return "天哥，不支持的随机操作~"


# ===== Tool Manager =====
class ToolManager:
    """工具管理器

    管理所有工具的注册、查找、执行。
    """

    def __init__(self, config: dict):
        self.config = config
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
        logger.info(f"工具管理器初始化完成，已注册 {len(self.tools)} 个工具: {list(self.tools.keys())}")

    def _register_default_tools(self):
        """注册默认工具"""
        default_tools = [
            WeatherTool(),
            SearchTool(),
            CalculatorTool(),
            TranslateTool(),
            DateTimeTool(),
            WebFetchTool(),
            RandomTool(),
        ]
        for tool in default_tools:
            self.register(tool)

    def register(self, tool: Tool):
        """注册一个工具"""
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        """获取工具"""
        return self.tools.get(name)

    def get_schemas(self) -> List[dict]:
        """获取所有工具的 schema（用于 LLM function calling）"""
        return [tool.to_schema() for tool in self.tools.values()]

    def list_tools(self) -> List[str]:
        """列出所有工具名"""
        return list(self.tools.keys())

    async def execute(self, tool_name: str, arguments: dict) -> str:
        """执行一个工具"""
        tool = self.get_tool(tool_name)
        if not tool:
            return f"工具 {tool_name} 不存在"

        logger.info(f"执行工具: {tool_name}({arguments})")
        try:
            result = await tool.execute(**arguments)
            logger.debug(f"工具结果: {result[:100]}...")
            return result
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name} - {e}")
            return f"工具执行出错了~"
