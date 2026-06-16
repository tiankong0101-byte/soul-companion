# ============================================================
#  retrieve.py - 长期记忆检索（v3.1）
# ============================================================
#
#  检索策略：
#    1. 结构化事实：按 category 列出 → 用于 system prompt 注入
#    2. 语义相关：用 query 向量化 → FAISS top-k → 用于上下文补充
#    3. 时间相关：最近的 N 条 → 用于「你最近说过的」场景
#
#  输出：拼装成可直接喂给 LLM 的 system 片段
# ============================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .store import MemoryStore


class MemoryRetriever:
    def __init__(self, store: MemoryStore):
        self.store = store

    # ---------------------- 结构化事实 ----------------------

    def get_facts(self, category: Optional[str] = None,
                  min_importance: float = 0.3, limit: int = 20) -> List[Dict[str, Any]]:
        return self.store.list_facts(category=category, min_importance=min_importance, limit=limit)

    def format_facts_for_prompt(self, facts: Optional[List[Dict[str, Any]]] = None,
                                max_items: int = 20) -> str:
        if facts is None:
            facts = self.get_facts(limit=max_items)
        if not facts:
            return ""
        lines = ["## 你记得的关于用户的事实："]
        for f in facts[:max_items]:
            conf = "（推测）" if f["confidence"] < 1.0 else ""
            lines.append(f"- [{f['category']}] {f['key']}: {f['value']} {conf}".rstrip())
        return "\n".join(lines)

    # ---------------------- 语义搜索 ----------------------

    def search_episodes(self, query: str, top_k: int = 5,
                        min_similarity: float = 0.3) -> List[Dict[str, Any]]:
        """按语义相似度检索 episodes。"""
        if not query.strip():
            return []
        try:
            qvec = self.store.embedder.embed(query)
        except Exception as e:  # noqa: BLE001
            print(f"[memory.retrieve] embedding 失败：{e}", file=__import__("sys").stderr)
            return []
        hits = self.store.index.search(qvec, top_k=top_k)
        out = []
        for eid, sim in hits:
            if sim < min_similarity:
                continue
            ep = self.store.get_episode(eid)
            if ep:
                ep["similarity"] = round(sim, 4)
                out.append(ep)
                self.store.touch_episode(eid)
        return out

    def format_episodes_for_prompt(self, episodes: List[Dict[str, Any]]) -> str:
        if not episodes:
            return ""
        lines = ["## 相关的过往对话："]
        for e in episodes:
            sim = e.get("similarity", 0)
            emo = f" [{e['emotion']}]" if e.get("emotion") else ""
            lines.append(f"- ({sim:.2f}){emo} {e['role']}: {e['content'][:200]}")
        return "\n".join(lines)

    # ---------------------- 一站式 ----------------------

    def build_context(self, query: str, *,
                      include_facts: bool = True,
                      include_episodes: bool = True,
                      top_k_episodes: int = 3,
                      max_facts: int = 15) -> str:
        """生成可直接拼到 system prompt 的上下文块。"""
        blocks = []
        if include_facts:
            facts = self.get_facts(limit=max_facts)
            f = self.format_facts_for_prompt(facts)
            if f:
                blocks.append(f)
        if include_episodes and query:
            eps = self.search_episodes(query, top_k=top_k_episodes)
            e = self.format_episodes_for_prompt(eps)
            if e:
                blocks.append(e)
        return "\n\n".join(blocks)
