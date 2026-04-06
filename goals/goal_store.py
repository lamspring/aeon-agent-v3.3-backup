"""
Goal Store - 目标持久化 (SQLite)

核心功能:
- SQLite 持久化
- CRUD 操作
- 查询接口
- 原子激活 (保证只有一个 active goal)
"""

import json
import sqlite3
import threading
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

from goals.models import Goal, GoalStatus, GoalPriority

logger = logging.getLogger(__name__)


class GoalStore:
    """
    目标存储
    
    数据库: /root/.openclaw/workspace/agent/db/goals.db
    表: goals
    """
    
    def __init__(self, db_path: str = "/root/.openclaw/workspace/agent/db/goals.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    parent_goal_id TEXT,
                    sub_goals TEXT,                 -- JSON array
                    context TEXT,                   -- JSON object (含 keywords)
                    success_criteria TEXT,          -- JSON array
                    created_at REAL,
                    activated_at REAL,
                    completed_at REAL,
                    related_task_ids TEXT,          -- JSON array
                    auto_completed INTEGER DEFAULT 0,
                    result TEXT,                    -- JSON object
                    failure_reason TEXT
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_goals_priority ON goals(priority)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_goals_created ON goals(created_at)")
            
            conn.commit()
        
        logger.info(f"GoalStore initialized: {self.db_path}")
    
    def _goal_to_row(self, goal: Goal) -> tuple:
        """Goal 转换为数据库行"""
        return (
            goal.goal_id,
            goal.description,
            goal.status,
            goal.priority,
            goal.parent_goal_id,
            json.dumps(goal.sub_goals) if goal.sub_goals else None,
            json.dumps(goal.context) if goal.context else None,
            json.dumps(goal.success_criteria) if goal.success_criteria else None,
            goal.created_at,
            goal.activated_at,
            goal.completed_at,
            json.dumps(goal.related_task_ids) if goal.related_task_ids else None,
            1 if goal.auto_completed else 0,
            json.dumps(goal.result) if goal.result else None,
            goal.failure_reason
        )
    
    def save(self, goal: Goal) -> str:
        """保存目标（插入或更新）"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO goals
                    (goal_id, description, status, priority, parent_goal_id,
                     sub_goals, context, success_criteria, created_at,
                     activated_at, completed_at, related_task_ids,
                     auto_completed, result, failure_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, self._goal_to_row(goal))
                conn.commit()
        
        return goal.goal_id
    
    def get_by_id(self, goal_id: str) -> Optional[Goal]:
        """通过ID获取目标"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM goals WHERE goal_id = ?",
                (goal_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return Goal.from_db_row(row)
            return None
    
    def get_by_status(self, status: GoalStatus, limit: int = 100) -> List[Goal]:
        """通过状态获取目标"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY priority, created_at LIMIT ?",
                (status.value, limit)
            )
            return [Goal.from_db_row(row) for row in cursor.fetchall()]
    
    def get_active(self) -> Optional[Goal]:
        """获取当前活跃目标（最多一个）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY activated_at DESC LIMIT 1",
                (GoalStatus.ACTIVE.value,)
            )
            row = cursor.fetchone()
            
            if row:
                return Goal.from_db_row(row)
            return None
    
    def get_pending(self, limit: int = 10) -> List[Goal]:
        """获取待处理目标（按优先级排序）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT * FROM goals 
                   WHERE status = ? 
                   ORDER BY priority ASC, created_at ASC 
                   LIMIT ?""",
                (GoalStatus.PENDING.value, limit)
            )
            return [Goal.from_db_row(row) for row in cursor.fetchall()]
    
    def get_all_active_and_pending(self) -> List[Goal]:
        """获取所有活跃和待处理目标"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT * FROM goals 
                   WHERE status IN (?, ?)
                   ORDER BY 
                     CASE status 
                       WHEN 'active' THEN 0 
                       ELSE 1 
                     END,
                     priority ASC,
                     created_at ASC""",
                (GoalStatus.ACTIVE.value, GoalStatus.PENDING.value)
            )
            return [Goal.from_db_row(row) for row in cursor.fetchall()]
    
    def get_by_task_id(self, task_id: str) -> Optional[Goal]:
        """通过任务ID查找关联的目标"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM goals WHERE related_task_ids LIKE ?",
                (f'%"{task_id}"%',)
            )
            row = cursor.fetchone()
            
            if row:
                return Goal.from_db_row(row)
            return None
    
    def get_recent_completed(self, limit: int = 10) -> List[Goal]:
        """获取最近完成的目标"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT * FROM goals 
                   WHERE status IN (?, ?)
                   ORDER BY completed_at DESC 
                   LIMIT ?""",
                (GoalStatus.COMPLETED.value, GoalStatus.FAILED.value, limit)
            )
            return [Goal.from_db_row(row) for row in cursor.fetchall()]
    
    def update_status(self, goal_id: str, status: GoalStatus, **kwargs) -> bool:
        """
        更新目标状态
        
        kwargs:
            - activated_at: float
            - completed_at: float
            - result: dict
            - failure_reason: str
            - auto_completed: bool
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # 构建更新字段
                fields = ["status = ?"]
                params = [status.value]
                
                if "activated_at" in kwargs:
                    fields.append("activated_at = ?")
                    params.append(kwargs["activated_at"])
                
                if "completed_at" in kwargs:
                    fields.append("completed_at = ?")
                    params.append(kwargs["completed_at"])
                
                if "result" in kwargs:
                    fields.append("result = ?")
                    params.append(json.dumps(kwargs["result"]))
                
                if "failure_reason" in kwargs:
                    fields.append("failure_reason = ?")
                    params.append(kwargs["failure_reason"])
                
                if "auto_completed" in kwargs:
                    fields.append("auto_completed = ?")
                    params.append(1 if kwargs["auto_completed"] else 0)
                
                params.append(goal_id)
                
                cursor = conn.execute(
                    f"UPDATE goals SET {', '.join(fields)} WHERE goal_id = ?",
                    params
                )
                conn.commit()
                
                return cursor.rowcount > 0
    
    def delete(self, goal_id: str) -> bool:
        """删除目标"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM goals WHERE goal_id = ?",
                    (goal_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
    
    def count_by_status(self) -> Dict[str, int]:
        """统计各状态的目标数量"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT status, COUNT(*) FROM goals GROUP BY status"
            )
            return {row[0]: row[1] for row in cursor.fetchall()}
    
    def link_task(self, goal_id: str, task_id: str) -> bool:
        """关联任务到目标"""
        goal = self.get_by_id(goal_id)
        if not goal:
            return False
        
        goal.link_task(task_id)
        self.save(goal)
        return True
    
    def unlink_task(self, goal_id: str, task_id: str) -> bool:
        """解除任务关联"""
        goal = self.get_by_id(goal_id)
        if not goal:
            return False
        
        goal.unlink_task(task_id)
        self.save(goal)
        return True
