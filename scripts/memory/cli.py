#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  cli.py - 长期记忆 CLI（v3.1）
# ============================================================
#
#  用法：
#    # 结构化事实
#    python scripts/memory/cli.py fact add --category personal --key birthday --value 1990-05-15
#    python scripts/memory/cli.py fact list
#    python scripts/memory/cli.py fact list --category personal
#    python scripts/memory/cli.py fact get --category personal --key birthday
#    python scripts/memory/cli.py fact delete --id 1
#
#    # 情景记忆
#    python scripts/memory/cli.py episode add --role user --content "今天好累" --emotion sad
#    python scripts/memory/cli.py episode list --limit 10
#    python scripts/memory/cli.py episode search "和妈妈的关系"
#
#    # 检索上下文（注入 LLM）
#    python scripts/memory/cli.py context "今天妈又不理解我了"
#
#    # 维护
#    python scripts/memory/cli.py stats
#    python scripts/memory/cli.py cleanup
# ============================================================

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

# 强制 UTF-8 输出（解决 Windows GBK 编码问题）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml

# 允许从仓库根或 scripts/ 直接运行
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from memory import MemoryStore, MemoryRetriever  # noqa: E402
from memory.embedder import create_embedder  # noqa: E402


def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "config.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _default_db_path() -> Path:
    cfg = _load_config()
    db = cfg.get("paths", {}).get("db_file", "data/memory.db")
    if not os.path.isabs(db):
        db = str(ROOT / db)
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    return Path(db)


def _create_store() -> MemoryStore:
    cfg = _load_config()
    emb_cfg = cfg.get("embedding", {})
    emb = create_embedder(
        backend=emb_cfg.get("backend", "auto"),
        model=emb_cfg.get("model", "nomic-embed-text"),
        base_url=emb_cfg.get("base_url", "http://localhost:11434"),
        dim=int(emb_cfg.get("dim", 768)),
    )
    use_faiss = cfg.get("paths", {}).get("index_backend", "faiss") == "faiss"
    return MemoryStore(str(_default_db_path()), emb, use_faiss=use_faiss)


# ----------------- 子命令 -----------------

def cmd_fact_add(args, store: MemoryStore):
    eid = store.add_fact(
        category=args.category, key=args.key, value=args.value,
        confidence=args.confidence, source=args.source, importance=args.importance,
    )
    print(f"[OK] fact #{eid}  [{args.category}] {args.key} = {args.value}")


def cmd_fact_list(args, store: MemoryStore):
    facts = store.list_facts(category=args.category, min_importance=args.min_importance)
    if not facts:
        print("（无）")
        return
    print(f"{'ID':<5} {'Cat':<14} {'Key':<20} {'Value':<30} {'Imp':<5} {'Conf':<5} Updated")
    print("-" * 100)
    for f in facts:
        print(f"{f['id']:<5} {f['category']:<14} {f['key']:<20} {f['value'][:30]:<30} "
              f"{f['importance']:<5.2f} {f['confidence']:<5.2f} {f['updated_at']}")


def cmd_fact_get(args, store: MemoryStore):
    f = store.get_fact(args.category, args.key)
    if not f:
        print("[ERR] 未找到")
        return
    import json
    print(json.dumps(f, ensure_ascii=False, indent=2))


def cmd_fact_delete(args, store: MemoryStore):
    ok = store.delete_fact(args.id)
    print("[OK] 已删除" if ok else "[ERR] 未找到")


def cmd_episode_add(args, store: MemoryStore):
    tags = args.tags.split(",") if args.tags else None
    eid = store.add_episode(
        role=args.role, content=args.content, session_id=args.session,
        emotion=args.emotion, importance=args.importance, tags=tags,
    )
    print(f"[OK] episode #{eid} ({args.role}, importance={store.get_episode(eid)['importance']:.2f})")


def cmd_episode_list(args, store: MemoryStore):
    eps = store.list_episodes(limit=args.limit, emotion=args.emotion)
    if not eps:
        print("（无）")
        return
    for e in eps:
        emo = f"[{e['emotion']}]" if e.get("emotion") else ""
        print(f"  #{e['id']:<5} {e['role']:<10} {emo:<12} imp={e['importance']:.2f}  {e['content'][:80]}")


def cmd_episode_search(args, store: MemoryStore):
    rt = MemoryRetriever(store)
    hits = rt.search_episodes(args.query, top_k=args.top_k)
    if not hits:
        print("（无匹配）")
        return
    for h in hits:
        sim = h.get("similarity", 0)
        emo = f"[{h['emotion']}]" if h.get("emotion") else ""
        print(f"  #{h['id']:<5} sim={sim:.3f} {emo:<10} {h['role']}: {h['content'][:80]}")


def cmd_context(args, store: MemoryStore):
    rt = MemoryRetriever(store)
    ctx = rt.build_context(args.query, top_k_episodes=args.top_k, max_facts=args.max_facts)
    if not ctx:
        print("（无相关记忆）")
        return
    print("=" * 70)
    print(ctx)
    print("=" * 70)


def cmd_stats(_args, store: MemoryStore):
    s = store.stats()
    print("记忆统计：")
    for k, v in s.items():
        print(f"  {k}: {v}")


def cmd_cleanup(args, store: MemoryStore):
    cfg = _load_config().get("retention", {})
    n = store.cleanup(
        older_than_days=args.days or cfg.get("older_than_days", 90),
        importance_below=args.threshold or cfg.get("importance_below", 0.3),
    )
    print(f"[OK] 已清理 {n} 条低重要性 + 长时间未访问的 episodes")


# ----------------- 解析 -----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="feifei-memory", description="soul-companion v3.1 长期记忆 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # fact
    sp = sub.add_parser("fact", help="结构化事实管理")
    fact_sub = sp.add_subparsers(dest="sub", required=True)

    a = fact_sub.add_parser("add")
    a.add_argument("--category", "-c", required=True)
    a.add_argument("--key", "-k", required=True)
    a.add_argument("--value", "-v", required=True)
    a.add_argument("--confidence", type=float, default=1.0)
    a.add_argument("--source", default="user_explicit")
    a.add_argument("--importance", type=float, default=0.5)
    a.set_defaults(func=cmd_fact_add)

    a = fact_sub.add_parser("list")
    a.add_argument("--category", "-c", default=None)
    a.add_argument("--min-importance", type=float, default=0.0)
    a.set_defaults(func=cmd_fact_list)

    a = fact_sub.add_parser("get")
    a.add_argument("--category", "-c", required=True)
    a.add_argument("--key", "-k", required=True)
    a.set_defaults(func=cmd_fact_get)

    a = fact_sub.add_parser("delete")
    a.add_argument("--id", type=int, required=True)
    a.set_defaults(func=cmd_fact_delete)

    # episode
    sp = sub.add_parser("episode", help="情景记忆管理")
    ep_sub = sp.add_subparsers(dest="sub", required=True)

    a = ep_sub.add_parser("add")
    a.add_argument("--role", required=True, choices=["user", "assistant", "system"])
    a.add_argument("--content", required=True)
    a.add_argument("--session", default=None)
    a.add_argument("--emotion", default=None)
    a.add_argument("--importance", type=float, default=None)
    a.add_argument("--tags", default=None, help="逗号分隔")
    a.set_defaults(func=cmd_episode_add)

    a = ep_sub.add_parser("list")
    a.add_argument("--limit", type=int, default=20)
    a.add_argument("--emotion", default=None)
    a.set_defaults(func=cmd_episode_list)

    a = ep_sub.add_parser("search")
    a.add_argument("query")
    a.add_argument("--top-k", type=int, default=5)
    a.set_defaults(func=cmd_episode_search)

    # context
    sp = sub.add_parser("context")
    sp.add_argument("query", help="用户当前说的话")
    sp.add_argument("--top-k", type=int, default=3)
    sp.add_argument("--max-facts", type=int, default=15)
    sp.set_defaults(func=cmd_context)

    # 维护
    sp = sub.add_parser("stats")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("cleanup")
    sp.add_argument("--days", type=int, default=None)
    sp.add_argument("--threshold", type=float, default=None)
    sp.set_defaults(func=cmd_cleanup)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = _create_store()
    args.func(args, store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
