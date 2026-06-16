"""
Soul Companion v5.0 — Scheduler
日程提醒模块：创建/查询/删除提醒，定时通知

架构：
  - SQLite 持久化存储所有日程
  - 后台定时检查到期提醒
  - 支持一次性提醒和重复提醒
"""
import uuid
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

import sqlite3
from loguru import logger


class Scheduler:
    """日程提醒管理器

    功能：
    1. 创建日程提醒（一次性 / 每日 / 每周 / 每月）
    2. 查询所有日程
    3. 删除/修改日程
    4. 后台定时检查，到期自动提醒
    5. 自然语言解析时间（"明天下午3点"、"下周二"等）
    """

    def __init__(self, config: dict):
        self.config = config
        db_path = Path(config.get("_base_dir", ".")) / "data" / "scheduler.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._init_db()
        self._running = False
        self._check_interval = 30  # 每30秒检查一次

        # 回调函数列表（到期时触发）
        self._callbacks: List = []

        logger.info(f"日程管理器初始化完成 (db={self.db_path})")

    def _init_db(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                remind_at TEXT NOT NULL,
                repeat_type TEXT DEFAULT 'none',
                repeat_interval INTEGER DEFAULT 0,
                priority TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.commit()
        conn.close()

    def register_callback(self, callback):
        """注册到期回调"""
        self._callbacks.append(callback)

    # ===== CRUD 操作 =====

    async def create_reminder(
        self,
        title: str,
        remind_at: str = None,
        description: str = "",
        repeat_type: str = "none",
        priority: str = "normal",
        relative_time: str = None,
    ) -> Dict[str, Any]:
        """创建提醒

        Args:
            title: 提醒标题
            remind_at: 提醒时间（ISO 格式: "2026-06-17T15:00:00"）
            description: 描述
            repeat_type: none / daily / weekly / monthly
            priority: low / normal / high / urgent
            relative_time: 相对时间（自然语言，如"明天下午3点"、"2小时后"）
        """
        reminder_id = str(uuid.uuid4())[:8]

        # 解析相对时间
        if relative_time and not remind_at:
            remind_at = self._parse_relative_time(relative_time)

        if not remind_at:
            return {"error": "请指定提醒时间"}

        # 确保 remind_at 是 ISO 格式
        try:
            remind_dt = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
        except ValueError:
            return {"error": f"时间格式错误: {remind_at}"}

        now = datetime.now()
        if remind_dt < now:
            return {"error": "不能设置过去的时间哦~"}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reminders (id, title, description, remind_at, repeat_type, priority, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (reminder_id, title, description, remind_at, repeat_type, priority, now.isoformat()))
        conn.commit()
        conn.close()

        time_str = remind_dt.strftime("%m月%d日 %H:%M")
        repeat_str = {"none": "", "daily": "（每天）", "weekly": "（每周）", "monthly": "（每月）"}.get(repeat_type, "")

        logger.info(f"创建提醒: {title} @ {time_str}{repeat_str}")
        return {
            "id": reminder_id,
            "title": title,
            "remind_at": remind_at,
            "repeat_type": repeat_type,
            "message": f"好的天哥~我会在 {time_str}{repeat_str} 提醒你「{title}」哦~",
        }

    async def list_reminders(self, status: str = "pending") -> List[Dict[str, Any]]:
        """查询提醒列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reminders WHERE status = ? ORDER BY remind_at ASC",
            (status,),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    async def complete_reminder(self, reminder_id: str) -> Dict[str, Any]:
        """标记提醒为已完成"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # 如果是重复提醒，创建下一次
        cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return {"error": "提醒不存在"}

        repeat_type = row[4]  # repeat_type column
        remind_at = row[3]   # remind_at column

        if repeat_type != "none":
            # 计算下一次提醒时间
            next_dt = self._calc_next_repeat(remind_at, repeat_type)
            new_id = str(uuid.uuid4())[:8]
            cursor.execute("""
                INSERT INTO reminders (id, title, description, remind_at, repeat_type, priority, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (new_id, row[1], row[2], next_dt.isoformat(), repeat_type, row[5], now))

        # 标记当前完成
        cursor.execute(
            "UPDATE reminders SET status = 'completed', completed_at = ? WHERE id = ?",
            (now, reminder_id),
        )
        conn.commit()
        conn.close()

        return {"success": True, "title": row[1]}

    async def delete_reminder(self, reminder_id: str) -> Dict[str, Any]:
        """删除提醒"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            return {"success": True, "message": "提醒已删除~"}
        return {"error": "提醒不存在"}

    async def get_due_reminders(self) -> List[Dict[str, Any]]:
        """获取所有到期的提醒"""
        now = datetime.now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND remind_at <= ?",
            (now.isoformat(),),
        )
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    # ===== 后台检查 =====

    async def start_check_loop(self):
        """启动后台检查循环"""
        self._running = True
        logger.info("日程检查循环已启动")
        while self._running:
            try:
                due = await self.get_due_reminders()
                for reminder in due:
                    # 触发回调
                    for cb in self._callbacks:
                        try:
                            await cb(reminder)
                        except Exception as e:
                            logger.error(f"提醒回调失败: {e}")

                    # 标记完成（重复提醒会自动创建下一个）
                    await self.complete_reminder(reminder["id"])
                    logger.info(f"提醒已触发: {reminder['title']}")
            except Exception as e:
                logger.error(f"日程检查出错: {e}")

            await asyncio.sleep(self._check_interval)

    def stop(self):
        """停止检查循环"""
        self._running = False

    # ===== 自然语言时间解析 =====

    def _parse_relative_time(self, text: str) -> str:
        """解析相对时间（自然语言 → ISO 时间）"""
        now = datetime.now()
        text = text.strip().lower()

        # "X分钟后"
        m = __import__('re').search(r'(\d+)\s*分钟后', text)
        if m:
            return (now + timedelta(minutes=int(m.group(1)))).isoformat()

        # "X小时后"
        m = __import__('re').search(r'(\d+)\s*小时后', text)
        if m:
            return (now + timedelta(hours=int(m.group(1)))).isoformat()

        # "X天后"
        m = __import__('re').search(r'(\d+)\s*天后', text)
        if m:
            return (now + timedelta(days=int(m.group(1)))).isoformat()

        # "明天"
        if "明天" in text:
            target = now + timedelta(days=1)
            # 尝试提取时间
            time_m = __import__('re').search(r'(\d{1,2})\s*[:：点时]\s*(\d{0,2})', text)
            if time_m:
                hour = int(time_m.group(1))
                minute = int(time_m.group(2)) if time_m.group(2) else 0
                target = target.replace(hour=hour, minute=minute, second=0)
            else:
                target = target.replace(hour=9, minute=0, second=0)
            return target.isoformat()

        # "后天"
        if "后天" in text:
            target = now + timedelta(days=2)
            time_m = __import__('re').search(r'(\d{1,2})\s*[:：点时]\s*(\d{0,2})', text)
            if time_m:
                hour = int(time_m.group(1))
                minute = int(time_m.group(2)) if time_m.group(2) else 0
                target = target.replace(hour=hour, minute=minute, second=0)
            else:
                target = target.replace(hour=9, minute=0, second=0)
            return target.isoformat()

        # "下周X"
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        for char, wd in weekday_map.items():
            if f"下周{char}" in text or f"下{char}" in text:
                days_ahead = (wd - now.weekday()) % 7 + 7
                target = now + timedelta(days=days_ahead)
                time_m = __import__('re').search(r'(\d{1,2})\s*[:：点时]\s*(\d{0,2})', text)
                if time_m:
                    target = target.replace(hour=int(time_m.group(1)), minute=int(time_m.group(2) or 0), second=0)
                else:
                    target = target.replace(hour=9, minute=0, second=0)
                return target.isoformat()

        # "下个月X号"
        m = __import__('re').search(r'下个月?(\d{1,2})\s*[号日]', text)
        if m:
            day = int(m.group(1))
            if now.month == 12:
                target = now.replace(year=now.year + 1, month=1, day=day, hour=9, minute=0, second=0)
            else:
                target = now.replace(month=now.month + 1, day=day, hour=9, minute=0, second=0)
            return target.isoformat()

        # "X月X日/号"
        m = __import__('re').search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*[号日]?', text)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            year = now.year
            if month < now.month:
                year += 1
            target = datetime(year, month, day, 9, 0, 0)
            return target.isoformat()

        # 默认：1小时后
        return (now + timedelta(hours=1)).isoformat()

    def _calc_next_repeat(self, current_remind_at: str, repeat_type: str) -> datetime:
        """计算下一次重复提醒时间"""
        dt = datetime.fromisoformat(current_remind_at.replace("Z", "+00:00"))

        if repeat_type == "daily":
            return dt + timedelta(days=1)
        elif repeat_type == "weekly":
            return dt + timedelta(weeks=1)
        elif repeat_type == "monthly":
            month = dt.month + 1
            year = dt.year
            if month > 12:
                month = 1
                year += 1
            day = min(dt.day, 28)  # 安全处理
            return dt.replace(year=year, month=month, day=day)
        return dt

    def get_info(self) -> dict:
        """获取模块信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reminders WHERE status = 'pending'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM reminders WHERE status = 'completed'")
        completed = cursor.fetchone()[0]
        conn.close()

        return {
            "pending_count": pending,
            "completed_count": completed,
            "db_path": self.db_path,
        }
