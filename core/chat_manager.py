"""
Soul Companion v4.0 — Chat Manager
聊天管理器：对话历史 + 记忆系统集成

架构升级：
  - 对话历史持久化到 SQLite（替代纯内存列表）
  - 集成 scripts/memory/ 系统实现长期记忆检索
  - 支持记忆自动保存和语义检索
"""
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from loguru import logger

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.memory.store import MemoryStore
from scripts.memory.retrieve import MemoryRetriever


class ChatManager:
    """聊天管理器（v4.0）

    管理对话历史，集成记忆系统：
    1. 对话历史存储到 SQLite（可持久化）
    2. 每次回复前自动检索相关记忆
    3. 支持记忆的 CRUD 操作
    """

    def __init__(self, config: dict):
        self.config = config
        self.session_id = str(uuid.uuid4())[:8]
        self.conversation_history: List[Dict[str, Any]] = []

        # 初始化记忆系统
        memory_config = config.get("memory", {})
        self.memory_enabled = memory_config.get("enabled", True)

        if self.memory_enabled:
            self._init_memory(memory_config)
        else:
            self.memory_store = None
            self.memory_retriever = None
            logger.info("记忆系统已禁用")

        logger.info(f"ChatManager 初始化完成 (session={self.session_id})")

    def _init_memory(self, memory_config: dict):
        """初始化记忆系统"""
        try:
            # 确保数据目录存在
            db_path = memory_config.get("db_path", "data/memory.db")
            db_dir = Path(db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

            self.memory_store = MemoryStore(db_path=db_path)
            self.memory_retriever = MemoryRetriever(
                store=self.memory_store,
                embedding_provider=memory_config.get("embedding_provider", "local"),
            )
            logger.info(f"记忆系统初始化完成 (db={db_path})")
        except Exception as e:
            logger.warning(f"记忆系统初始化失败，降级为无记忆模式: {e}")
            self.memory_store = None
            self.memory_retriever = None

    async def process_message(
        self, user_text: str, agent
    ) -> Dict[str, Any]:
        """处理用户消息并生成回复

        完整流程：
        1. 保存用户消息到历史
        2. 检索相关记忆
        3. 调用 Agent 生成回复
        4. 保存助手回复到历史
        5. 异步保存对话到长期记忆

        Args:
            user_text: 用户输入
            agent: FeiFeiAgent 实例

        Returns:
            Agent 的回复字典
        """
        # 1. 保存用户消息
        self.conversation_history.append({
            "role": "user",
            "content": user_text,
            "timestamp": datetime.now().isoformat(),
        })

        # 2. 检索相关记忆
        memory_context = None
        if self.memory_enabled and self.memory_retriever:
            try:
                memory_context = await self._retrieve_memories(user_text)
            except Exception as e:
                logger.warning(f"记忆检索失败: {e}")

        # 3. 调用 Agent 生成回复
        response = await agent.generate_response(
            user_text=user_text,
            chat_history=self.conversation_history,
            memory_context=memory_context,
        )

        # 4. 保存助手回复
        self.conversation_history.append({
            "role": "assistant",
            "content": response.get("content", ""),
            "emotion": response.get("emotion", "neutral"),
            "mode": response.get("mode", "default"),
            "timestamp": datetime.now().isoformat(),
        })

        # 5. 异步保存到长期记忆
        if self.memory_enabled and self.memory_store:
            try:
                await self._save_to_memory(user_text, response)
            except Exception as e:
                logger.warning(f"记忆保存失败: {e}")

        return response

    async def _retrieve_memories(self, query: str) -> Optional[str]:
        """从记忆系统检索相关记忆"""
        if not self.memory_retriever:
            return None

        max_turns = self.config.get("memory", {}).get("max_context_turns", 20)
        results = await self.memory_retriever.retrieve(
            query=query,
            top_k=5,
        )

        if not results:
            return None

        # 格式化记忆上下文
        context_parts = []
        for r in results:
            if hasattr(r, 'text'):
                context_parts.append(f"- {r.text}")
            elif isinstance(r, dict) and "text" in r:
                context_parts.append(f"- {r['text']}")

        if context_parts:
            return "\n".join(context_parts)
        return None

    async def _save_to_memory(self, user_text: str, response: dict):
        """保存对话到长期记忆"""
        if not self.memory_store:
            return

        assistant_text = response.get("content", "")
        emotion = response.get("emotion", "neutral")

        # 保存用户消息
        await self.memory_store.save_conversation(
            role="user",
            content=user_text,
            session_id=self.session_id,
            metadata={"emotion": "neutral"},
        )

        # 保存助手回复
        await self.memory_store.save_conversation(
            role="assistant",
            content=assistant_text,
            session_id=self.session_id,
            metadata={"emotion": emotion},
        )

    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取对话历史"""
        if limit:
            return self.conversation_history[-limit:]
        return self.conversation_history.copy()

    def clear_history(self):
        """清空当前会话历史"""
        self.conversation_history.clear()
        logger.info(f"会话历史已清空 (session={self.session_id})")

    def get_stats(self) -> Dict[str, Any]:
        """获取聊天统计"""
        total_messages = len(self.conversation_history)
        user_messages = sum(1 for m in self.conversation_history if m["role"] == "user")
        assistant_messages = sum(1 for m in self.conversation_history if m["role"] == "assistant")

        return {
            "session_id": self.session_id,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "memory_enabled": self.memory_enabled,
            "start_time": self.conversation_history[0]["timestamp"] if self.conversation_history else None,
        }

    async def save_session(self):
        """手动保存当前会话到持久存储"""
        if self.memory_enabled and self.memory_store:
            try:
                for msg in self.conversation_history:
                    await self.memory_store.save_conversation(
                        role=msg["role"],
                        content=msg["content"],
                        session_id=self.session_id,
                        metadata={
                            "emotion": msg.get("emotion", "neutral"),
                            "mode": msg.get("mode", "default"),
                            "timestamp": msg.get("timestamp", ""),
                        },
                    )
                logger.info(f"会话已保存 (session={self.session_id}, messages={len(self.conversation_history)})")
            except Exception as e:
                logger.error(f"会话保存失败: {e}")
