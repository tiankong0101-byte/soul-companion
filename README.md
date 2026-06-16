# Soul Companion

> 🎉 **v4.0.0 已发布（2026-06-16）** — **架构大升级**！将旧架构（Flask+WebSocket+Live2D+ASR+Vision）完整迁移到新架构（模块化 scripts/），统一入口 `app.py`，集成记忆系统。详见 [CHANGELOG.md](CHANGELOG.md)。
> 📋 **路线图**：v3.0 多 LLM ✅ → v3.1 长期记忆 ✅ → v4.0 架构升级 ✅ → v4.1 工具调用 📋

 - Emotional Companion for OpenClaw

A warm and caring emotional companion skill that makes OpenClaw interactions more heartfelt and supportive.

## Features

- **Warm Personality**: Gentle and caring response style
- **Emotional Support**: Comfort mode for when you're feeling down
- **Active Listening**: Patient listener mode for venting
- **Playful Mode**: Fun and lighthearted interactions
- **Memory**: Long-term memory with SQLite + vector embedding retrieval
- **Multi-LLM Routing**: OpenAI / Ollama / Claude / DeepSeek / Gemini 等多后端自动降级
- **Voice**: TTS (edge-tts) + ASR (FunASR / Whisper) 语音交互
- **Vision**: 多模态图片理解
- **Live2D**: 表情/动作驱动动画

## Character: Feifei

### 基本信息
- Age: 20
- Height: 1.65m
- Weight: 45kg (89斤)

### 外貌特征
- **发型**: 乌黑长直发如瀑布般垂落至胸前，搭配轻盈的空气刘海
- **脸型**: 精致小V脸，下颌线清晰锐利
- **肤色**: 白皙如瓷的肌肤，五官清秀立体
- **眼睛**: 大而明亮的双眼皮眼睛，深褐色瞳孔清澈如水
- **穿搭**: 偏爱黑色细肩带吊带衫等丝绸/缎面质感服饰

### 性格气质
- Gentle, caring, empathetic, occasionally playful
- 甜美温柔、清新脱俗、高级感十足

## 🚀 v4.0 快速开始

```bash
# 1. 克隆
git clone https://github.com/tiankong0101-byte/soul-companion.git
cd soul-companion

# 2. 安装依赖
pip install -r requirements.txt

# 3. 设置至少一个 API key（可选）
export OPENAI_API_KEY=sk-xxx       # OpenAI
export ANTHROPIC_API_KEY=sk-ant-xxx  # Claude
# 或配置本地 Ollama（无需 API key）

# 4. 启动菲菲
python app.py

# 5. 打开浏览器
# http://localhost:5000
```

### 命令行参数

```bash
python app.py --port 8080          # 指定端口
python app.py --debug              # 调试模式
python app.py --config other.yaml  # 指定配置文件
```

## 🏗️ 架构 v4.0

```
soul-companion/
├── app.py                      # 🆕 统一入口（Flask + SocketIO）
├── config/
│   ├── config.yaml             # 🆕 统一主配置
│   └── llm.yaml                # LLM 多后端配置
├── core/                       # 🆕 业务逻辑层
│   ├── __init__.py
│   ├── agent.py                # AI 代理核心（菲菲的大脑）
│   ├── chat_manager.py         # 聊天管理器（集成记忆系统）
│   ├── asr_manager.py          # 🆕 语音识别管理器
│   ├── vision_manager.py       # 🆕 视觉管理器
│   └── live2d_controller.py    # 🆕 Live2D 动画控制器
├── scripts/                    # 基础设施层（v3.x 保持不变）
│   ├── llm_router.py           # 多后端 LLM 路由
│   ├── llm_backends.py         # 5 种 LLM 后端实现
│   ├── memory/                 # 长期记忆系统
│   │   ├── store.py            # SQLite 存储
│   │   ├── retrieve.py         # 语义检索
│   │   ├── embedder.py         # 向量嵌入
│   │   ├── vector_index.py     # 向量索引
│   │   └── cli.py              # CLI 管理工具
│   └── voice/                  # 语音模块
│       ├── tts/                # TTS（edge-tts）
│       ├── cli.py              # CLI 工具
│       └── config.yaml         # 语音配置
├── web/                        # 🆕 前端界面
│   ├── index.html
│   ├── app.js
│   └── style.css
├── data/                       # 运行时数据
│   └── memory.db               # 记忆数据库
├── logs/                       # 运行日志
├── requirements.txt            # 依赖列表
└── CHANGELOG.md                # 版本日志
```

## 📚 文档

- [SKILL.md](SKILL.md) — 技能定义（人格 + 8 模式 + 情感协议）
- [CHANGELOG.md](CHANGELOG.md) — 版本日志
- [docs/v3.0-llm.md](docs/v3.0-llm.md) — v3.0 LLM 路由文档
- [BOOT.md](BOOT.md) — 启动说明
- [MEMORY.md](MEMORY.md) — 记忆系统
- [AGENTS.md](AGENTS.md) — Agent 描述

## License

MIT License - Feel free to use and modify!

## Author

TianGe - Created with love for the OpenClaw community
