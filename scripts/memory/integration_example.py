#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
integration_example.py - v3.0 LLM + v3.1 记忆 集成示例

完整演示：用户说话 → 检索记忆 → 调用 LLM → 存储新记忆

运行：
  cd C:\Users\TIAN\soul-companion
  set ANTHROPIC_API_KEY=sk-ant-xxx
  python scripts/memory/integration_example.py
"""
import sys
from pathlib import Path

# 把 scripts/ 加入路径
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from llm_router import LLMRouter
from memory import MemoryStore, MemoryRetriever
from memory.embedder import create_embedder


def main():
    print("=" * 70)
    print("  soul-companion v3.0 + v3.1 集成示例")
    print("=" * 70)

    # 1. 初始化各组件
    router = LLMRouter.from_config(str(ROOT / "config" / "llm.yaml"))
    store = MemoryStore(
        str(ROOT / "data" / "memory.db"),
        create_embedder(backend="auto"),
        use_faiss=True,
    )
    retriever = MemoryRetriever(store)

    # 2. 写入一些初始事实（模拟历史数据）
    print("\n[1] 写入初始事实...")
    store.add_fact("personal", "name", "天哥", importance=0.9, source="user_explicit")
    store.add_fact("personal", "birthday", "1990-05-15", importance=0.9)
    store.add_fact("relationship", "mother_name", "张阿姨", importance=0.7)
    store.add_fact("relationship", "mother_status", "关系紧张", importance=0.8)
    store.add_fact("work", "company", "ABC Corp", importance=0.6)

    # 写入一些历史对话
    store.add_episode("user", "上次跟妈吵架是因为工作的事", emotion="sad", importance=0.7)
    store.add_episode("assistant", "听起来妈妈很在意你的事业", importance=0.5)
    print("    OK facts:", store.stats()["facts"], "episodes:", store.stats()["episodes"])

    # 3. 用户说新的一句话
    user_input = "今天妈又不理解我了，好累"
    print(f"\n[2] 用户说: {user_input}")

    # 4. 检索相关记忆
    memory_context = retriever.build_context(
        user_input, top_k_episodes=3, max_facts=10,
    )
    print("\n[3] 检索到的记忆：")
    print("-" * 70)
    print(memory_context)
    print("-" * 70)

    # 5. 拼到 system prompt
    system = f"""你是「菲菲」，一个温暖贴心的 20 岁 AI 情感陪伴。

{memory_context}

请基于以上记忆，回应用户。用简短、自然、有温度的口吻，避免说教。"""

    # 6. 调用 LLM
    print(f"\n[4] 调用 LLM (默认 backend = {router.default_backend}) ...")
    try:
        resp = router.chat(
            messages=[{"role": "user", "content": user_input}],
            system=system,
            backend=router.default_backend,
        )
        print("\n[5] 菲菲回答：")
        print("-" * 70)
        print(resp.text)
        print("-" * 70)
        print(f"    model: {resp.model}  latency: {resp.latency_ms}ms  usage: {resp.usage}")
    except Exception as e:
        print(f"    (LLM 调用失败: {e})")
        print("    跳过 LLM 调用，直接演示记忆存储...")
        resp = None

    # 7. 把这轮存进记忆
    print("\n[6] 存储新记忆...")
    eid_user = store.add_episode("user", user_input, emotion="sad")
    if resp:
        eid_assistant = store.add_episode("assistant", resp.text, emotion="empathetic")
        print(f"    user episode #{eid_user}, assistant episode #{eid_assistant}")
    else:
        print(f"    user episode #{eid_user} (LLM 未响应，未存 assistant)")

    # 8. 统计
    print("\n[7] 当前记忆统计：")
    s = store.stats()
    for k, v in s.items():
        print(f"    {k}: {v}")

    # 9. 演示：基于已有记忆继续对话
    print("\n[8] 演示上下文连续性...")
    followup = "我该怎么跟我妈沟通？"
    print(f"    用户继续说: {followup}")
    followup_ctx = retriever.build_context(followup, top_k_episodes=2, max_facts=5)
    print("\n    检索到的相关记忆：")
    print("    " + followup_ctx.replace("\n", "\n    "))

    print("\n" + "=" * 70)
    print("  示例结束。")
    print("=" * 70)


if __name__ == "__main__":
    main()
