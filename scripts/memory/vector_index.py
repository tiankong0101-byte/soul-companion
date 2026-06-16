# ============================================================
#  vector_index.py - FAISS 向量索引（v3.1）
# ============================================================
#
#  持久化方案：
#    - SQLite 存 episode metadata
#    - FAISS 存向量（IndexFlatIP = 余弦相似度，前提向量已 L2 normalize）
#    - 双方通过自增 id 关联
#
#  简化方案（不依赖 faiss-cpu）：
#    - 如果未安装 faiss-cpu，自动降级到 numpy 实现（计算慢但可用）
# ============================================================

from __future__ import annotations

import os
import pickle
import sqlite3
import threading
from typing import List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

# 尝试导入 faiss，找不到就降级
try:
    import faiss  # type: ignore
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


class VectorIndex:
    """语义向量索引。"""

    def __init__(self, db_path: str, dim: int = 768, use_faiss: bool = True):
        self.db_path = db_path
        self.dim = dim
        self.use_faiss = bool(use_faiss and HAS_FAISS)
        self._lock = threading.RLock()

        # 内存中的向量缓存
        self._vectors: List[List[float]] = []  # 全部向量
        self._ids: List[int] = []              # 对应 id

        # 加载已有的
        self._load()

    # ---------------------- 持久化 ----------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load(self) -> None:
        """从 SQLite 加载已有 embedding（粗略：先不加载，启动后 lazy load）。"""
        if not os.path.exists(self.db_path):
            return
        try:
            conn = self._connect()
            cur = conn.execute(
                "SELECT id, embedding FROM episodes WHERE embedding IS NOT NULL ORDER BY id"
            )
            rows = cur.fetchall()
            conn.close()
            for r in rows:
                emb = pickle.loads(r["embedding"]) if r["embedding"] else None
                if emb and len(emb) == self.dim:
                    self._vectors.append(emb)
                    self._ids.append(r["id"])
        except Exception:
            pass

    def _save_one(self, eid: int, vector: List[float]) -> None:
        """把单条向量写回 SQLite。"""
        conn = self._connect()
        conn.execute(
            "UPDATE episodes SET embedding = ? WHERE id = ?",
            (pickle.dumps(vector), eid),
        )
        conn.commit()
        conn.close()

    # ---------------------- 增删查 ----------------------

    def add(self, eid: int, vector: List[float]) -> None:
        with self._lock:
            assert len(vector) == self.dim, f"向量维度 {len(vector)} != {self.dim}"
            self._vectors.append(vector)
            self._ids.append(eid)
            try:
                self._save_one(eid, vector)
            except Exception:
                pass  # SQLite 可能没准备好，容错

    def remove(self, eid: int) -> None:
        with self._lock:
            if eid in self._ids:
                i = self._ids.index(eid)
                self._ids.pop(i)
                self._vectors.pop(i)

    def search(self, query_vec: List[float], top_k: int = 5) -> List[Tuple[int, float]]:
        """返回 [(id, similarity), ...]，按相似度降序。"""
        with self._lock:
            if not self._ids:
                return []
            if self.use_faiss:
                return self._search_faiss(query_vec, top_k)
            return self._search_numpy(query_vec, top_k)

    # ---------------------- 后端实现 ----------------------

    def _search_numpy(self, q: List[float], k: int) -> List[Tuple[int, float]]:
        if np is None:
            raise RuntimeError("需要 numpy 才能运行向量搜索（pip install numpy）")
        M = np.asarray(self._vectors, dtype=np.float32)
        qv = np.asarray(q, dtype=np.float32)
        # L2 normalize
        M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
        qv /= (np.linalg.norm(qv) + 1e-9)
        sims = M @ qv  # 余弦相似度
        order = np.argsort(-sims)[:k]
        return [(self._ids[int(i)], float(sims[int(i)])) for i in order]

    def _search_faiss(self, q: List[float], k: int) -> List[Tuple[int, float]]:
        # 重建索引（小型场景足够）
        M = np.asarray(self._vectors, dtype=np.float32)
        # 余弦相似度：先 L2 normalize 再用内积
        faiss.normalize_L2(M)
        index = faiss.IndexFlatIP(M.shape[1])
        index.add(M)
        qv = np.asarray([q], dtype=np.float32)
        faiss.normalize_L2(qv)
        sims, idxs = index.search(qv, k)
        out = []
        for i, s in zip(idxs[0], sims[0]):
            if i < 0 or i >= len(self._ids):
                continue
            out.append((self._ids[int(i)], float(s)))
        return out

    # ---------------------- 元信息 ----------------------

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def backend(self) -> str:
        return "faiss" if self.use_faiss else "numpy"
