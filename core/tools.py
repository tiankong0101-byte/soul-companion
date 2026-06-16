"""
Soul Companion v5.1 — Tool Calling Framework
工具调用框架：天气 / 搜索(AnySearch) / 计算 / 网页抓取 / 翻译 / URL摘要 / 每日简报 / 音乐生成

v5.1 新增：
  - SearchTool 升级为 AnySearch API（替代 DuckDuckGo 爬虫，更可靠）
  - UrlSummaryTool：网页智能摘要提取
  - DailyBriefingTool：每日简报（天气+日程+新闻汇总）
  - MusicGenerateTool：AI 音乐生成（集成 ai-music-muse）
"""
import re
import os
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
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict:
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        ...

    def to_schema(self) -> dict:
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


# ===== 搜索工具（v5.1 升级：AnySearch API） =====
class SearchTool(Tool):
    """网络搜索（使用 AnySearch API，替代 DuckDuckGo 爬虫）

    v5.1: 接入 AnySearch API，搜索更稳定、结果更丰富。
    支持多引擎聚合（Google/Bing/Baidu），无需 API Key 也可用（有速率限制）。
    """

    ANYSEARCH_API = "https://api.anysearch.com/v1/search"

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "搜索互联网获取最新信息。用于回答实时问题，如新闻、资料、知识等。支持中英文搜索。"

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
        try:
            # 尝试 AnySearch API
            api_key = os.environ.get("ANYSEARCH_API_KEY", "")
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "query": query,
                "max_results": max_results,
            }

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    self.ANYSEARCH_API,
                    json=payload,
                    headers=headers,
                )
                data = resp.json()

            results = data.get("results", [])
            if not results:
                # 回退到 DuckDuckGo Lite
                return await self._fallback_ddg(query, max_results)

            output = f"🔍 搜索「{query}」的结果：\n\n"
            for i, item in enumerate(results[:max_results]):
                title = item.get("title", "未知")
                url = item.get("url", "")
                snippet = item.get("snippet", item.get("description", ""))
                output += f"{i+1}. **{title}**\n   {snippet}\n   🔗 {url}\n\n"

            return output.strip()

        except Exception as e:
            logger.warning(f"AnySearch API 失败，回退到 DuckDuckGo: {e}")
            return await self._fallback_ddg(query, max_results)

    async def _fallback_ddg(self, query: str, max_results: int) -> str:
        """回退方案：DuckDuckGo Lite 爬虫"""
        try:
            url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}&kl=cn-zh"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers, follow_redirects=True)
                html = resp.text

            results = []
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
            logger.error(f"搜索完全失败: {e}")
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
        try:
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
            expr = expression.strip()
            expr = expr.replace("×", "*").replace("÷", "/").replace("^", "**")
            result = eval(expr, {"__builtins__": {}}, safe_dict)
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
        try:
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
                "min_val": {"type": "integer", "description": "最小值（number模式），默认1"},
                "max_val": {"type": "integer", "description": "最大值（number模式），默认100"},
                "options": {"type": "array", "items": {"type": "string"}, "description": "选项列表（choice模式）"},
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


# ===== v5.1 新增：URL 智能摘要工具 =====
class UrlSummaryTool(Tool):
    """网页智能摘要 — 提取 URL 核心内容并生成精简摘要"""

    @property
    def name(self) -> str:
        return "url_summary"

    @property
    def description(self) -> str:
        return "智能提取指定 URL 的核心内容并生成精简摘要。适合快速了解一篇文章、新闻或页面的主要信息。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要提取摘要的 URL",
                },
                "max_length": {
                    "type": "integer",
                    "description": "摘要最大长度（字符数），默认500",
                },
            },
            "required": ["url"],
        }

    async def execute(self, url: str, max_length: int = 500) -> str:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                html = resp.text

            # 提取标题
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "未知标题"

            # 提取 meta description
            desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', html, re.IGNORECASE)
            if not desc_match:
                desc_match = re.search(r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
            meta_desc = desc_match.group(1).strip() if desc_match else ""

            # 提取正文
            text = html
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL)
            text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL)
            text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL)
            text = re.sub(r'<aside[^>]*>.*?</aside>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            # 智能截取：尝试找到文章主体（跳过导航等前导文字）
            paragraphs = [p.strip() for p in text.split('  ') if len(p.strip()) > 30]
            body = ' '.join(paragraphs[:10])

            # 组合摘要
            summary_parts = [f"📌 **{title}**"]
            if meta_desc:
                summary_parts.append(f"\n{meta_desc}")
            if body:
                body_extract = body[:max_length]
                if len(body) > max_length:
                    body_extract += "..."
                summary_parts.append(f"\n{body_extract}")

            return f"📋 URL 摘要（{url}）：\n\n" + "\n".join(summary_parts)

        except Exception as e:
            logger.error(f"URL 摘要提取失败: {e}")
            return f"抱歉天哥，提取这个网址的内容失败了~"


# ===== v5.1 新增：每日简报工具 =====
class DailyBriefingTool(Tool):
    """每日简报 — 一键汇总天气 + 日程 + 新闻"""

    @property
    def name(self) -> str:
        return "daily_briefing"

    @property
    def description(self) -> str:
        return "生成今日简报，包含天气预报、日程安排和新闻热点。适合早起或开始工作时快速了解今天的情况。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "天气查询的城市名（默认'北京'）",
                },
            },
            "required": [],
        }

    async def execute(self, city: str = "北京") -> str:
        try:
            now = datetime.now()
            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[now.weekday()]

            parts = []
            parts.append(f"📋 天哥的每日简报 — {now.year}年{now.month}月{now.day}日 {weekday}")
            parts.append("=" * 40)

            # 1. 天气
            parts.append("\n🌤️ 今日天气")
            try:
                url = f"https://wttr.in/{quote_plus(city)}?format=j1&lang=zh"
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url, headers={"Accept-Language": "zh-CN"})
                    data = resp.json()
                current = data.get("current_condition", [{}])[0]
                temp = current.get("temp_C", "?")
                desc_list = current.get("lang_zh", current.get("weatherDesc", [{}]))
                desc = desc_list[0].get("value", "?") if desc_list else "?"
                humidity = current.get("humidity", "?")
                parts.append(f"  {city}: {desc} {temp}°C，湿度 {humidity}%")

                forecast = data.get("weather", [])
                if forecast:
                    today_fc = forecast[0]
                    parts.append(f"  今日温度：{today_fc.get('mintempC', '?')}°C ~ {today_fc.get('maxtempC', '?')}°C")
                if len(forecast) > 1:
                    tmr = forecast[1]
                    parts.append(f"  明日预告：{tmr.get('mintempC', '?')}°C ~ {tmr.get('maxtempC', '?')}°C")
            except Exception as e:
                parts.append(f"  天气获取失败: {e}")

            # 2. 日程（如果 scheduler 注入了）
            parts.append("\n📅 今日日程")
            parts.append("  （日程数据需要启动服务后自动获取）")

            # 3. 新闻热点
            parts.append("\n📰 新闻热点")
            try:
                api_key = os.environ.get("ANYSEARCH_API_KEY", "")
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        SearchTool.ANYSEARCH_API,
                        json={"query": "今日新闻热点", "max_results": 5},
                        headers=headers,
                    )
                    data = resp.json()

                results = data.get("results", [])
                if results:
                    for i, item in enumerate(results[:5]):
                        title = item.get("title", "?")
                        parts.append(f"  {i+1}. {title}")
                else:
                    parts.append("  暂无新闻数据")
            except Exception:
                parts.append("  新闻获取失败（网络问题）")

            # 4. 温馨提示
            parts.append("\n💡 温馨提示")
            hour = now.hour
            if hour < 8:
                parts.append("  天哥起得真早~记得吃早餐哦！")
            elif hour < 12:
                parts.append("  上午好！今天也要加油哦~")
            elif hour < 14:
                parts.append("  中午了，该吃午饭休息一下~")
            elif hour < 18:
                parts.append("  下午茶时间，喝杯水放松一下~")
            elif hour < 22:
                parts.append("  晚上好~今天辛苦了！")
            else:
                parts.append("  夜深了，早点休息哦~注意身体！")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"每日简报生成失败: {e}")
            return f"抱歉天哥，简报生成出了点问题~"


# ===== v5.1 新增：AI 音乐生成工具 =====
class MusicGenerateTool(Tool):
    """AI 音乐生成 — 根据描述生成音乐"""

    MUSIC_API = "https://api.ai-music-muse.com/v1/generate"

    @property
    def name(self) -> str:
        return "music_generate"

    @property
    def description(self) -> str:
        return "根据文字描述生成AI音乐。可以指定风格（流行、古典、摇滚、电子、爵士等）和情绪。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "音乐描述，如'一首温柔的钢琴曲，适合夜晚放松'",
                },
                "style": {
                    "type": "string",
                    "description": "音乐风格：pop/classical/rock/electronic/jazz/ambient/lofi，默认 auto",
                },
                "duration": {
                    "type": "integer",
                    "description": "音乐时长（秒），默认30",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, prompt: str, style: str = "auto", duration: int = 30) -> str:
        try:
            api_key = os.environ.get("AI_MUSIC_MUSE_KEY", "")
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "prompt": prompt,
                "style": style,
                "duration": min(duration, 120),
            }

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(self.MUSIC_API, json=payload, headers=headers)
                data = resp.json()

            if data.get("status") == "success" or data.get("audio_url"):
                audio_url = data.get("audio_url", "")
                duration_actual = data.get("duration", duration)
                style_detected = data.get("style", style)

                result = f"🎵 AI 音乐生成完成！\n"
                result += f"  📝 描述：{prompt}\n"
                result += f"  🎭 风格：{style_detected}\n"
                result += f"  ⏱️ 时长：{duration_actual}秒\n"
                if audio_url:
                    result += f"  🔗 音频：{audio_url}\n"
                return result
            else:
                error_msg = data.get("error", "未知错误")
                return f"天哥，音乐生成失败了~({error_msg})"

        except httpx.ConnectError:
            return "天哥，音乐生成服务暂时不可用呢~可能需要配置 API Key 才能用哦。你可以搜索一下相关的免费音乐生成工具~"
        except Exception as e:
            logger.error(f"音乐生成失败: {e}")
            return f"抱歉天哥，音乐生成出了点问题~"


# ===== Tool Manager =====
class ToolManager:
    """工具管理器

    管理所有工具的注册、查找、执行。
    v5.1: 新增 url_summary、daily_briefing、music_generate 三个工具（共10个）
    """

    def __init__(self, config: dict):
        self.config = config
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
        logger.info(f"工具管理器初始化完成，已注册 {len(self.tools)} 个工具: {list(self.tools.keys())}")

    def _register_default_tools(self):
        """注册默认工具（v5.1: 10 个工具）"""
        default_tools = [
            WeatherTool(),
            SearchTool(),
            CalculatorTool(),
            TranslateTool(),
            DateTimeTool(),
            WebFetchTool(),
            RandomTool(),
            UrlSummaryTool(),       # v5.1 新增
            DailyBriefingTool(),    # v5.1 新增
            MusicGenerateTool(),    # v5.1 新增
        ]
        for tool in default_tools:
            self.register(tool)

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)

    def get_schemas(self) -> List[dict]:
        return [tool.to_schema() for tool in self.tools.values()]

    def list_tools(self) -> List[str]:
        return list(self.tools.keys())

    async def execute(self, tool_name: str, arguments: dict) -> str:
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
