# Changelog - soul-companion

所有版本变更记录于此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [5.0.0] - 2026-06-16 - 工具调用 + 图片生成 + 日程提醒

### 新增 ✨
- **工具调用框架** `core/tools.py` — 7种内置工具
  - 🌤️ 天气查询 / 🔍 网络搜索 / 🧮 数学计算 / 🌐 翻译 / 🕐 时间 / 🌐 网页抓取 / 🎲 随机
- **图片生成** `core/image_generator.py` — Pollinations/Stability/本地SD
- **日程提醒** `core/scheduler.py` — SQLite + 自然语言解析 + 重复提醒
- Agent 工具调用集成（LLM 自主决策 → 工具执行 → 温柔回复）
- 前端：图片消息显示 + 日程列表UI + 到期提醒推送

---

## [4.0.0] - 2026-06-16 - 架构大升级

### 重大变更 🔄
- **统一架构**：将旧架构（Flask+WebSocket+Live2D+ASR+Vision）完整迁移到新架构
- **统一入口**：`app.py` 替代旧 `main.py`，支持命令行参数
- **统一配置**：`config/config.yaml` 统一管理所有配置
- **两层架构**：
  - `core/` 业务逻辑层（Agent、ChatManager、ASR、Vision、Live2D）
  - `scripts/` 基础设施层（LLM 路由、记忆系统、语音模块）

### 新增 ✨
- `app.py` — 统一入口（Flask + SocketIO），支持 `--port` / `--debug` / `--config` 参数
- `config/config.yaml` — 统一主配置（app/llm/memory/voice/live2d/vision/safety）
- `core/agent.py` — AI 代理核心，使用 `scripts.llm_router.LLMRouter` 统一路由
- `core/chat_manager.py` — 聊天管理器，集成 `scripts.memory.store` + `retrieve` 记忆系统
- `core/asr_manager.py` — 语音识别管理器（FunASR / Whisper 多后端自动降级）
- `core/vision_manager.py` — 视觉管理器（多模态 LLM 图片理解）
- `core/live2d_controller.py` — Live2D 动画控制器（8 种情感 × 8 种模式映射）
- `web/` — 前端界面（聊天 UI + Live2D 画布 + 情感指示器 + 统计面板）
- `requirements.txt` — 合并后的依赖列表

### 改进 ⬆️
- `core/agent.py` 使用 `scripts/llm_router.py` 替代旧的内联 httpx 调用
- `core/chat_manager.py` 使用 `scripts/memory/store.py` + `retrieve.py` 实现长期记忆
- 前端支持 WebSocket 实时通信 + HTTP API 双通道
- 配置系统统一到 `config/` 目录

### 移除 🗑️
- 旧架构的内联 LLM 调用代码（由 llm_router 替代）
- 纯内存对话历史（由 SQLite 持久化替代）

---

## [3.2.0] - 2026-06-16 - Open-LLM-VTuber 迁移 - Phase 3: 多 TTS + ASR

### 新增 ✨
- **6 种 TTS 引擎** `scripts/voice/tts/`
  - EdgeTTS（v2.2 沿用，云端，免部署）
  - GPTSoVITSTTS（HTTP API 模板）
  - CosyVoiceTTS（HTTP API 模板）
  - FishSpeechTTS（HTTP API 模板）
  - MeloTTSTTS（in-process 模板）
  - SparkTTSTTS（in-process 模板）
- **3 种 ASR 引擎** `scripts/voice/asr/`
  - WhisperASR（faster-whisper，本地）
  - FunASRASR（in-process 模板）
  - SherpaOnnxASR（ONNX 模板）
- **BaseTTS 抽象** + TTSResult 数据类
  - emoji/控制字符预处理
  - ffplay/afplay 自动播放器选择
  - L2 范数归一化的输出路径哈希
- **BaseASR 抽象** + ASRResult 数据类
  - 语言自动检测
  - 段落级时间戳
- **统一 CLI** `scripts/voice/cli.py`
  - tts list / speak / voices
  - asr list / transcribe
- **9 个 TTS 预设 + 4 个 ASR 预设** `scripts/voice/config.yaml`
- **26 个单元测试** 全部通过
- **真实合成验证**：12,960 字节 MP3 文件
- **SKILL.md 第十五节 + 11 个新触发词**

### 集成 v3.0 + v3.1 🤝
完整 RAG + 语音链路：ASR → 文本 → MemoryRetriever → LLM Router → 文本 → TTS → 音频

---

## [3.1.0] - 2026-06-16 - Open-LLM-VTuber 迁移 - Phase 2: 长期记忆

### 新增 ✨
- **双层记忆架构** `scripts/memory/`
  - SQLite 存结构化事实（facts）
  - FAISS 存语义向量（episodes）
  - 重要性自动评估 + 自动遗忘
- **3 种 Embedding 后端** `scripts/memory/embedder.py`
- **VectorIndex** `scripts/memory/vector_index.py`
- **MemoryRetriever** `scripts/memory/retrieve.py`
- **CLI 工具** `scripts/memory/cli.py`
- **17 个单元测试** 全部通过

---

## [3.0.0] - 2026-06-16 - Open-LLM-VTuber 迁移 - Phase 1: 多 LLM 后端路由

### 新增 ✨
- **多 LLM 后端路由** `scripts/llm_router.py` + `scripts/llm_backends.py`
  - 5 种后端协议：`anthropic` / `openai` / `openai_compat` / `gemini` / `ollama`
  - 16 个开箱即用的预设后端
  - YAML 配置 + 环境变量插值
  - 流式响应 + 失败重试 + 用量统计
- **配置文件** `config/llm.yaml`
- **单元测试** `scripts/test_llm_router.py`（25 个测试全部通过）

---

## [2.2.0] - 2026-05-XX - 菲菲语音 TTS

### 新增
- 微软 Edge TTS 4 种语音配置
- `scripts/feifei-tts.py` + `scripts/feifei-tts.ps1`

---

## [2.1.0] - 2026-04-XX - 菲菲外观重定义 + v2.0 功能全量合并

### 新增
- 菲菲详细外貌描写更新
- v2.0 的 8 种模式 / 情感分级 / 主动关怀 / 边界管理全部合并

---

## [2.0.0] - 2026-03-XX - 模式扩展 + 情感协议

### 新增
- 8 种交互模式
- 情感分级协议（4 级）
- 主动关怀 / 边界管理
- NVC 非暴力沟通 4 步
- 心理急救 CPR 原则

---

## [1.0.0] - 2025-12-XX - 初版

### 新增
- 4 种基础模式
- 基础情感支持 prompt
- 菲菲人设（20 岁温柔 AI 伴侣）

---

## 路线图

| 版本 | 主题 | 状态 |
|------|------|------|
| v3.0 | 多 LLM 后端 | ✅ 已发布 |
| v3.1 | 长期记忆（SQLite + FAISS）| ✅ 已发布 |
| v3.2 | 多 TTS + ASR | ✅ 已发布 |
| v4.0 | 架构大升级 | ✅ 已发布 |
| v4.1 | 工具调用框架 | 📋 计划中 |
