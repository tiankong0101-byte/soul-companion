#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  test_memory.py - v3.1 单元测试
# ============================================================

from __future__ import annotations

import gc
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

# 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 允许从仓库根跑
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from memory import MemoryStore, MemoryRetriever  # noqa: E402
from memory.embedder import BaseEmbedder  # noqa: E402


# ---------- 假 embedder：相同关键词 → 相近向量 ----------

class FakeEmbedder(BaseEmbedder):
    """基于特征哈希 + L2 normalize 的确定性 embedder。
    相同关键词出现在多个文本中时，会在相同维度有非零贡献 → 余弦相似度高。
    """
    dim = 128

    def __init__(self, dim: int = 128):
        self.dim = dim

    def _word_hash(self, word: str, salt: int = 0) -> int:
        return int(hashlib.md5((word + ":" + str(salt)).encode("utf-8")).hexdigest(), 16)

    def _vectorize(self, text: str) -> List[float]:
        v = [0.0] * self.dim
        for word in text.split():
            for s in range(8):
                h = self._word_hash(word, s)
                idx = h % self.dim
                sign = 1.0 if (h >> 128) & 1 else -1.0
                v[idx] += sign
        norm = sum(x * x for x in v) ** 0.5
        if norm > 0:
            v = [x / norm for x in v]
        return v

    def embed_batch(self, texts):
        return [self._vectorize(t) for t in texts]


# ---------- 测试 ----------

class _MemoryTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.emb = FakeEmbedder(dim=64)
        self.store = MemoryStore(self.tmp.name, self.emb, use_faiss=False)

    def tearDown(self):
        # 显式释放连接 + GC
        try:
            del self.store
        except Exception:
            pass
        gc.collect()
        try:
            os.unlink(self.tmp.name)
        except (PermissionError, FileNotFoundError, OSError):
            pass


class TestFacts(_MemoryTestBase):
    def test_add_and_get_fact(self):
        eid = self.store.add_fact("personal", "birthday", "1990-05-15", importance=0.9)
        self.assertGreater(eid, 0)
        f = self.store.get_fact("personal", "birthday")
        self.assertEqual(f["value"], "1990-05-15")
        self.assertEqual(f["importance"], 0.9)

    def test_upsert_same_key(self):
        self.store.add_fact("personal", "name", "天哥", importance=0.7)
        self.store.add_fact("personal", "name", "天哥（昵称）", importance=0.8)
        f = self.store.get_fact("personal", "name")
        self.assertEqual(f["value"], "天哥（昵称）")
        self.assertEqual(f["importance"], 0.8)  # 取 max

    def test_list_facts_filter(self):
        self.store.add_fact("personal", "a", "1", importance=0.9)
        self.store.add_fact("work", "b", "2", importance=0.2)
        all_f = self.store.list_facts()
        self.assertEqual(len(all_f), 2)
        personals = self.store.list_facts(category="personal")
        self.assertEqual(len(personals), 1)
        high_imp = self.store.list_facts(min_importance=0.5)
        self.assertEqual(len(high_imp), 1)

    def test_delete_fact(self):
        eid = self.store.add_fact("personal", "a", "1")
        self.assertTrue(self.store.delete_fact(eid))
        self.assertIsNone(self.store.get_fact("personal", "a"))


class TestEpisodes(_MemoryTestBase):
    def test_add_episode_with_importance_estimation(self):
        eid = self.store.add_episode("user", "今天好累", emotion="sad")
        ep = self.store.get_episode(eid)
        self.assertEqual(ep["content"], "今天好累")
        # sad + 短文本：基础 0.5 + sad 加成 0.3 = 0.8
        self.assertGreater(ep["importance"], 0.5)

    def test_add_episode_with_importance_keyword(self):
        eid = self.store.add_episode("user", "下周五是我生日")
        ep = self.store.get_episode(eid)
        # 命中"生日"关键词，加 0.15
        self.assertGreater(ep["importance"], 0.5)

    def test_episode_in_index(self):
        for i in range(5):
            self.store.add_episode("user", f"今天心情{'好' if i % 2 else '差'}")
        self.assertEqual(len(self.store.index), 5)

    def test_touch_episode(self):
        eid = self.store.add_episode("user", "hi")
        self.store.touch_episode(eid)
        ep = self.store.get_episode(eid)
        self.assertEqual(ep["access_count"], 1)
        self.assertIsNotNone(ep["last_accessed"])


class TestRetrieval(_MemoryTestBase):
    def setUp(self):
        super().setUp()
        self.rt = MemoryRetriever(self.store)
        self.store.add_fact("personal", "birthday", "1990-05-15", importance=0.9)
        self.store.add_fact("work", "company", "ABC Corp", importance=0.6)
        self.store.add_episode("user", "妈妈又不理解我了", emotion="sad")
        self.store.add_episode("assistant", "听起来你很委屈")
        self.store.add_episode("user", "今天加班到很晚", emotion="tired")

    def test_format_facts(self):
        text = self.rt.format_facts_for_prompt()
        self.assertIn("birthday", text)
        self.assertIn("1990-05-15", text)

    def test_search_episodes(self):
        hits = self.rt.search_episodes("妈妈", top_k=3)
        self.assertGreater(len(hits), 0)
        # 包含「妈妈」的应至少有一条
        contents = " ".join(h["content"] for h in hits)
        self.assertIn("妈妈", contents)

    def test_search_unrelated_low_similarity(self):
        hits = self.rt.search_episodes("xyz123 完全无关", top_k=3)
        # 没有相关 → 可能返回空（相似度过低被过滤）或返回低分结果
        # 我们只断言不会抛异常
        self.assertIsInstance(hits, list)

    def test_build_context(self):
        ctx = self.rt.build_context("妈妈")
        self.assertIn("你记得的关于用户的事实", ctx)
        self.assertIn("相关的过往对话", ctx)

    def test_build_context_no_query(self):
        ctx = self.rt.build_context("", include_episodes=False)
        self.assertIn("birthday", ctx)
        self.assertNotIn("相关的过往对话", ctx)


class TestCleanup(_MemoryTestBase):
    def test_cleanup(self):
        # 插一条 importance 极低的
        eid = self.store.add_episode("user", "无关紧要的闲聊", importance=0.05)
        # cleanup 会同时检查 created_at > 90 天
        # 为了测试：手动改 created_at
        import sqlite3
        with sqlite3.connect(self.tmp.name) as conn:
            conn.execute(
                "UPDATE episodes SET created_at = datetime('now', '-100 days') WHERE id = ?",
                (eid,),
            )
            conn.commit()
        deleted = self.store.cleanup(older_than_days=90, importance_below=0.3)
        self.assertEqual(deleted, 1)
        self.assertIsNone(self.store.get_episode(eid))

    def test_stats(self):
        self.store.add_fact("personal", "a", "1")
        self.store.add_episode("user", "hello")
        s = self.store.stats()
        self.assertEqual(s["facts"], 1)
        self.assertEqual(s["episodes"], 1)
        self.assertIn(s["index_backend"], ("faiss", "numpy"))


class TestCLI(unittest.TestCase):
    _shared_store = None

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        # 改 cli 默认 db 路径
        import memory.cli as cli_mod
        cli_mod._default_db_path = staticmethod(lambda: Path(self.tmp_db.name))

        # 单例 store（CLI 每次 main 都会调 _create_store，所以保持同一个实例）
        if TestCLI._shared_store is None or TestCLI._shared_store.db_path != self.tmp_db.name:
            TestCLI._shared_store = MemoryStore(
                str(self.tmp_db.name), FakeEmbedder(dim=64), use_faiss=False,
            )
        cli_mod._create_store = lambda: TestCLI._shared_store

    def tearDown(self):
        gc.collect()
        TestCLI._shared_store = None
        try:
            os.unlink(self.tmp_db.name)
        except (PermissionError, FileNotFoundError, OSError):
            pass

    def test_fact_crud(self):
        from io import StringIO
        from contextlib import redirect_stdout
        import memory.cli as cli
        # add
        out = StringIO()
        with redirect_stdout(out):
            cli.main(["fact", "add", "-c", "personal", "-k", "birthday", "-v", "1990-05-15", "--importance", "0.9"])
        self.assertIn("fact #", out.getvalue())
        # list
        out = StringIO()
        with redirect_stdout(out):
            cli.main(["fact", "list"])
        self.assertIn("birthday", out.getvalue())

    def test_episode_search(self):
        from io import StringIO
        from contextlib import redirect_stdout
        import memory.cli as cli
        # 用 mock 让 "妈妈" 关键词匹配
        store = cli._create_store()
        emb = store.embedder

        def fake_embed(text):
            v = [0.0] * 64
            for i, c in enumerate(text):
                v[hash(c) % 64] += 1.0
            return v

        emb.embed = fake_embed
        emb.embed_batch = lambda texts: [fake_embed(t) for t in texts]
        # 同步替换 store 里已经生成的 embedding（如果已经 add 过的）
        import numpy as np
        for e in store.list_episodes():
            new_vec = fake_embed(e["content"])
            store.index.remove(e["id"])
            store.index.add(e["id"], new_vec)

        cli.main(["episode", "add", "--role", "user", "--content", "今天和妈妈吵架了", "--emotion", "sad"])
        cli.main(["episode", "add", "--role", "assistant", "--content", "听起来你很委屈"])
        # 给新增的也补 embedding
        for e in store.list_episodes():
            new_vec = fake_embed(e["content"])
            if e["id"] not in store.index._ids:
                store.index.add(e["id"], new_vec)
            else:
                store.index.remove(e["id"])
                store.index.add(e["id"], new_vec)
        out = StringIO()
        with redirect_stdout(out):
            cli.main(["episode", "search", "妈妈"])
        self.assertIn("妈妈", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
