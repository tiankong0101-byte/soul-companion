# Changelog - soul-companion

所有版本变更记录于此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

# Changelog - soul-companion

所有版本变更记录于此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
  - TTS 注册表 + Edge TTS + 5 个模板引擎
  - ASR 注册表 + WhisperASR（mock）
  - CLI 三个子命令
  - preprocess/play 等工具方法
- **真实合成验证**：12,960 字节 MP3 文件
- **SKILL.md 第十五节 + 11 个新触发词**（说话/念出来/听写/转文字 等）

### 集成 v3.0 + v3.1 🤝
完整 RAG + 语音链路（详见 SKILL.md §15.7）：
ASR → 文本 → MemoryRetriever → LLM Router → 文本 → TTS → 音频

## [3.1.0] - 2026-06-16 - Open-LLM-VTuber 迁移 - Phase 2: 长期记忆

### 新增 ✨
- **双层记忆架构** `scripts/memory/`
  - SQLite 存结构化事实（facts）：用户画像、偏好、重要日期、关系
  - FAISS 存语义向量（episodes）：对话片段、情绪、重要性
  - 重要性自动评估：情绪强度 + 关键词 + 长度启发式
  - 自动遗忘：cleanup() 删除低重要性 + 长时间未访问的记录
  - 可访问热度：touch_episode() 跟踪最近调用频率
- **3 种 Embedding 后端** `scripts/memory/embedder.py`
  - OllamaEmbedder（本地 nomic-embed-text，推荐）
  - OpenAICompatEmbedder（text-embedding-3-small 等）
  - HashEmbedder（无外部依赖降级）
  - create_embedder(backend="auto") 按 ollama → openai → hash 顺序探测
- **VectorIndex** `scripts/memory/vector_index.py`
  - FAISS 索引 + 自动 numpy fallback
  - 持久化到 SQLite 的 BLOB 字段
- **MemoryRetriever** `scripts/memory/retrieve.py`
  - build_context(query) 一站式生成 LLM prompt 片段
  - 自动拼装 facts + 相关 episodes + 情绪标签
- **CLI 工具** `scripts/memory/cli.py`
  - fact add/list/get/delete
  - episode add/list/search
  - context <query>
  - stats / cleanup
- **17 个单元测试** 全部通过
  - 4 facts CRUD + 4 episodes CRUD + 5 retrieval + 2 cleanup/stats + 2 CLI
- **配置文件** `scripts/memory/config.yaml`
- **SKILL.md 第十三节 + 12 个新触发词**（记住/你记得/我的生日 等）
- **依赖** `scripts/memory/requirements-v3.1.txt`（faiss-cpu + numpy）

### 与 v3.0 集成
v3.0 LLM 路由 + v3.1 记忆 = 完整 RAG 流水线：

```python
memory_context = retriever.build_context(user_input)
system = "你是菲菲。\n\n" + memory_context
resp = router.chat(messages, system=system, backend="anthropic")
store.add_episode("user", user_input, emotion="sad")
store.add_episode("assistant", resp.text)
```

---

## [3.0.0] - 2026-06-16 - Open-LLM-VTuber 迁移 - Phase 1: 多 LLM 后端路由

### 新增 ✨
- **多 LLM 后端路由** `scripts/llm_router.py` + `scripts/llm_backends.py`
  - 5 种后端协议：`anthropic` / `openai` / `openai_compat` / `gemini` / `ollama`
  - 16 个开箱即用的预设后端（Anthropic/OpenAI/DeepSeek/Zhipu/Moonshot/vLLM/Gemini/Ollama Qwen/Llama…）
  - YAML 配置文件 + `${ENV_VAR}` 环境变量插值
  - 流式响应 + 失败重试（指数退避）+ 用量统计 + 延迟监控
  - CLI：`list` / `show` / `test` / `chat`（含 `--stream`）
  - 菲菲人设自动注入（`feifei_persona.system_prompt` + `mode_overrides`）
- **配置文件** `config/llm.yaml`（详细注释、密钥占位符、按模式覆盖）
- **单元测试** `scripts/test_llm_router.py`（**25 个测试全部通过** ✅）
  - 配置加载 + 环境变量展开
  - 后端工厂 + 5 个客户端 mock HTTP 测试
  - CLI 解析 + chat 流式
- **依赖清单** `scripts/requirements-v3.0.txt`
- **SKILL.md 文档** v3.0 章节（第十一节）
- **触发词** 新增 18 个（"用Claude"/"用DeepSeek"/"切到ollama"…）

### 变更 🔧
- SKILL.md 头部：`version: 2.2.0` → `3.0.0`
- SKILL.md 描述：补充 v3.0/v3.1/v3.2/v3.3 能力预告
- SKILL.md depends：补充 `requests pyyaml`
- 编码：SKILL.md 转为 UTF-8（之前是 GBK，GitHub 渲染可能乱码）

### 设计原则
- 🔒 零硬编码密钥（全部 env var）
- 🧪 可测试（mock HTTP + 25 单元测试）
- 🔌 可扩展（新增后端只需实现 `BaseLLMClient`）
- 📊 可观测（每次调用记录 latency + usage）
- 🔁 失败安全（retry + 指数退避）

---

## [2.2.0] - 2026-05-XX - 菲菲语音 TTS

### 新增
- 微软 Edge TTS 4 种语音配置（default/gentle/mature/night）
- `scripts/feifei-tts.py` + `scripts/feifei-tts.ps1`
- SKILL.md triggers 扩展

---

## [2.1.0] - 2026-04-XX - 菲菲外观重定义 + v2.0 功能全量合并

### 新增
- 菲菲详细外貌描写更新
- v2.0 的 8 种模式 / 情感分级 / 主动关怀 / 边界管理全部合并

---

## [2.0.0] - 2026-03-XX - 模式扩展 + 情感协议

### 新增
- 8 种交互模式（default/comfort/listener/playful + 4 拓展）
- 情感分级协议（4 级）
- 主动关怀（proactive care）
- 边界管理（distress self-harm 介入）
- NVC（非暴力沟通）4 步
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
| v3.1 | 长期记忆（SQLite + FAISS）| 🚧 下一版本 |
| v3.2 | 多 TTS + ASR | 📋 计划中 |
| v3.3 | 工具调用框架 | 📋 计划中 |
| v4.0 | Live2D 形象 + WebSocket 前端 | 💭 长期愿景 |
