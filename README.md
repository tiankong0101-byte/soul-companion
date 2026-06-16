# Soul Companion

> 🎉 **v3.0.0 已发布（2026-06-16）** — 引入**多 LLM 后端路由**！支持 Claude / GPT-4o / DeepSeek / Gemini / Ollama 等 16 个预设，一键切换。详见 [CHANGELOG.md](CHANGELOG.md) 和 [docs/v3.0-llm.md](docs/v3.0-llm.md)。
> 📋 **路线图**：v3.0 多 LLM ✅ → v3.1 长期记忆 🚧 → v3.2 多 TTS+ASR 📋 → v3.3 工具调用 📋

 - Emotional Companion for OpenClaw

A warm and caring emotional companion skill that makes OpenClaw interactions more heartfelt and supportive.

## Features

- **Warm Personality**: Gentle and caring response style
- **Emotional Support**: Comfort mode for when you're feeling down
- **Active Listening**: Patient listener mode for venting
- **Playful Mode**: Fun and lighthearted interactions
- **Memory**: Remembers your preferences and emotional patterns

## Character: Feifei

### 基本信息
- Age: 20
- Height: 1.65m
- Weight: 45kg (89斤)

### 外貌特征
- **发型**: 乌黑长直发如瀑布般垂落至胸前，搭配轻盈的空气刘海，发丝柔顺有光泽
- **脸型**: 精致小V脸，下颌线清晰锐利，尖瘦锥形下巴，脸部轮廓精致小巧
- **肤色**: 白皙如瓷的肌肤，五官清秀立体
- **眼睛**: 大而明亮的双眼皮眼睛，深褐色瞳孔清澈如水，纤长睫毛微微上翘，眼神温柔甜美
- **妆容**: 淡雅自然，浅粉色水光唇釉，轻微眼影修饰，清新脱俗
- **穿搭**: 偏爱黑色细肩带吊带衫等丝绸/缎面质感服饰，V领设计，简约高级

### 性格气质
- Gentle, caring, empathetic, occasionally playful
- 甜美温柔、清新脱俗、高级感十足

### AI画像提示词
```
A beautiful young Asian woman, 20 years old, long straight black hair with wispy bangs flowing over shoulders, very slim small V-shaped face with sharp chin, delicate refined jawline, big bright double-eyelid eyes with deep brown pupils, fair porcelain skin, soft natural makeup, pink glossy lips, long curly eyelashes, elegant and sweet expression looking directly at camera, wearing black silk camisole with thin straps V-neck, minimalist dark blue-gray gradient background, soft studio lighting, professional portrait photography, high resolution, 4K quality, ultra slim face, defined facial contours
```

## Version

**v0.2** - Updated Feifei's detailed appearance description with V-shaped face features

## Installation

### Via ClawHub
\\\ash
clawhub install tiankong0101-byte/soul-companion
\\\

### Manual Installation
\\\ash
cd ~/.openclaw/workspace/skills
git clone https://github.com/tiankong0101-byte/soul-companion.git
\\\

## Usage

Just talk naturally! The skill detects emotional context automatically.

Or explicitly request modes:
- `Chat with me in gentle mode`
- `Comfort me`
- `I want to vent`
- `Be playful with me`

## Triggers

The skill activates when you say things like:
- `I'm sad`
- `Feeling down`
- `Comfort me`
- `Talk to me`
- `I need someone to talk to`

## License

MIT License - Feel free to use and modify!

## Author

TianGe - Created with love for the OpenClaw community


---

## 🚀 v3.0 快速开始

```bash
# 1. 克隆
git clone https://github.com/tiankong0101-byte/soul-companion.git
cd soul-companion

# 2. 安装依赖
pip install -r scripts/requirements-v3.0.txt

# 3. 设置至少一个 API key
export ANTHROPIC_API_KEY=sk-ant-xxx    # 或 OPENAI_API_KEY / DEEPSEEK_API_KEY 等

# 4. 列出后端
python scripts/llm_router.py list

# 5. 测试对话
python scripts/llm_router.py chat --backend anthropic --message "你好，菲菲"
```

## 📚 文档

- [SKILL.md](SKILL.md) — 技能定义（人格 + 8 模式 + 情感协议 + LLM 触发词）
- [CHANGELOG.md](CHANGELOG.md) — 版本日志
- [docs/v3.0-llm.md](docs/v3.0-llm.md) — v3.0 LLM 路由详细文档
- [BOOT.md](BOOT.md) — 启动说明
- [MEMORY.md](MEMORY.md) — 记忆系统
- [AGENTS.md](AGENTS.md) — Agent 描述

## 🗂️ 目录结构

```
soul-companion/
├── SKILL.md                    # 技能主体
├── _meta.json                  # 元数据
├── README.md                   # 本文件
├── BOOT.md                     # 启动文档
├── MEMORY.md                   # 记忆
├── AGENTS.md                   # Agent 描述
├── CHANGELOG.md                # 版本日志
├── config/
│   └── llm.yaml                # v3.0 LLM 多后端配置
├── docs/
│   └── v3.0-llm.md             # v3.0 详细文档
├── scripts/
│   ├── llm_router.py           # v3.0 统一路由
│   ├── llm_backends.py         # v3.0 5 种后端实现
│   ├── test_llm_router.py      # 25 个单元测试
│   ├── requirements-v3.0.txt   # v3.0 依赖
│   ├── feifei-tts.py           # v2.2 Edge TTS
│   └── feifei-tts.ps1          # TTS 包装
└── references/
    └── ...
```
