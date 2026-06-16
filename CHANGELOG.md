# Changelog - soul-companion

所有版本变更记录于此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
