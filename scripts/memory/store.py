# ============================================================
#  store.py - 长期记忆存储（v3.1）
# ============================================================
#
#  写入两类记忆：
#    1. fact  (结构化事实)
#    2. episode (情景记忆 + 向量)
#
#  自动评估 importance：
#    - fact：用户明确说 → 0.9；推断 → 0.5
#    - episode：情绪强度 + 长度 启发式
# ============================================================

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .embedder import BaseEmbedder
from .vector_index import VectorIndex


SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


class MemoryStore:
    """SQLite + FAISS 混合存储。"""

    def __init__(self, db_path: str, embedder: BaseEmbedder,
                 use_faiss: bool = True):
        self.db_path = db_path
        self.embedder = embedder
        self.index = VectorIndex(db_path, dim=embedder.dim, use_faiss=use_faiss)
        self._ensure_schema()

    # ---------------------- schema ----------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        """初始化数据库 schema（首次运行）。"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            schema = SCHEMA_PATH.read_text(encoding="utf-8")
            conn.executescript(schema)
            conn.commit()

    # ---------------------- facts ----------------------

    def add_fact(self, category: str, key: str, value: str,
                 confidence: float = 1.0, source: str = "user_explicit",
                 importance: float = 0.5) -> int:
        """写入或更新一条事实（同 category+key 会被覆盖）。"""
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO facts(category, key, value, confidence, source, importance)
                   VALUES(?, ?, ?, ?, ?, ?)
                   ON CONFLICT(category, key) DO UPDATE SET
                       value = excluded.value,
                       confidence = excluded.confidence,
                       source = excluded.source,
                       importance = MAX(facts.importance, excluded.importance)""",
                (category, key, value, confidence, source, importance),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def get_fact(self, category: str, key: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM facts WHERE category = ? AND key = ?",
                (category, key),
            ).fetchone()
            return dict(row) if row else None

    def list_facts(self, category: Optional[str] = None,
                   min_importance: float = 0.0,
                   limit: int = 100) -> List[Dict[str, Any]]:
        q = "SELECT * FROM facts WHERE importance >= ?"
        args: List[Any] = [min_importance]
        if category:
            q += " AND category = ?"
            args.append(category)
        q += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(q, args).fetchall()
            return [dict(r) for r in rows]

    def delete_fact(self, fact_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
            return cur.rowcount > 0

    # ---------------------- episodes ----------------------

    def add_episode(self, role: str, content: str,
                    session_id: Optional[str] = None,
                    emotion: Optional[str] = None,
                    importance: Optional[float] = None,
                    tags: Optional[List[str]] = None) -> int:
        """写入一条情景记忆（同时生成 embedding）。"""
        if not content.strip():
            raise ValueError("content 不能为空")

        # 启发式评估 importance
        if importance is None:
            importance = self._estimate_importance(content, emotion)

        tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO episodes(session_id, role, content, emotion, importance, tags)
                   VALUES(?, ?, ?, ?, ?, ?)""",
                (session_id, role, content, emotion, importance, tags_json),
            )
            eid = int(cur.lastrowid or 0)
            conn.commit()

        # 异步（或同步）生成 embedding 并加入索引
        try:
            vec = self.embedder.embed(content)
            self.index.add(eid, vec)
        except Exception as e:  # noqa: BLE001
            # embedding 失败也不影响 SQLite 写入
            print(f"[memory.store] 警告：embedding 失败（{e}），episode {eid} 仅存 SQLite", file=__import__("sys").stderr)
        return eid

    def get_episode(self, eid: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM episodes WHERE id = ?", (eid,)).fetchone()
            return dict(row) if row else None

    def list_episodes(self, limit: int = 50, emotion: Optional[str] = None,
                      min_importance: float = 0.0) -> List[Dict[str, Any]]:
        q = "SELECT * FROM episodes WHERE importance >= ?"
        args: List[Any] = [min_importance]
        if emotion:
            q += " AND emotion = ?"
            args.append(emotion)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(q, args).fetchall()
            return [dict(r) for r in rows]

    def delete_episode(self, eid: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM episodes WHERE id = ?", (eid,))
            conn.commit()
        self.index.remove(eid)
        return cur.rowcount > 0

    def touch_episode(self, eid: int) -> None:
        """更新 last_accessed 和 access_count（用于检索后热度统计）。"""
        with self._connect() as conn:
            conn.execute(
                """UPDATE episodes
                   SET last_accessed = datetime('now'),
                       access_count = access_count + 1
                   WHERE id = ?""",
                (eid,),
            )
            conn.commit()

    # ---------------------- importance ----------------------

    @staticmethod
    def _estimate_importance(content: str, emotion: Optional[str]) -> float:
        """启发式：情绪强度 + 关键词 + 长度。"""
        score = 0.5
        emo_weights = {
            "sad": 0.3, "anxious": 0.3, "angry": 0.3, "lonely": 0.3,
            "excited": 0.2, "grateful": 0.2,
        }
        if emotion and emotion in emo_weights:
            score += emo_weights[emotion]
        # 关键词
        important_keywords = [
            "生日", "去世", "离开", "分手", "结婚", "怀孕", "孩子", "癌症", "住院",
            "birthday", "died", "breakup", "married", "pregnant", "cancer",
            "不要", "永远", "承诺", "秘密", "我想", "我希望",
        ]
        c_lower = content.lower()
        for kw in important_keywords:
            if kw.lower() in c_lower:
                score += 0.15
                break
        # 长度
        if len(content) > 200:
            score += 0.1
        return min(score, 1.0)

    # ---------------------- cleanup ----------------------

    def cleanup(self, older_than_days: int = 90,
                importance_below: float = 0.3) -> int:
        """自动遗忘：删除重要性低 + 长时间没访问的 episodes。"""
        with self._connect() as conn:
            cur = conn.execute(
                """DELETE FROM episodes
                   WHERE importance < ?
                     AND (
                         last_accessed IS NULL
                         OR julianday('now') - julianday(last_accessed) > ?
                     )
                     AND julianday('now') - julianday(created_at) > ?""",
                (importance_below, older_than_days, older_than_days),
            )
            deleted = cur.rowcount
            conn.commit()
        return deleted

    def stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            facts_n = conn.execute("SELECT COUNT(*) AS c FROM facts").fetchone()["c"]
            ep_n = conn.execute("SELECT COUNT(*) AS c FROM episodes").fetchone()["c"]
            avg_imp = conn.execute("SELECT AVG(importance) AS a FROM episodes").fetchone()["a"] or 0
        return {
            "facts": facts_n,
            "episodes": ep_n,
            "index_size": len(self.index),
            "index_backend": self.index.backend,
            "avg_importance": round(float(avg_imp), 3),
            "db_path": self.db_path,
        }
