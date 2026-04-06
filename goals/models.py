"""
Goal Models - 目标数据模型

核心概念:
- Goal: 一个目标/意图
- GoalStatus: 目标状态机 (pending -> active -> completed/failed)
- GoalPriority: 优先级 (CRITICAL > HIGH > NORMAL > LOW)
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime


class GoalStatus(Enum):
    """目标状态"""
    PENDING = "pending"       # 等待开始
    ACTIVE = "active"         # 正在执行
    PAUSED = "paused"         # 暂停
    COMPLETED = "completed"   # 完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 取消


class GoalPriority(Enum):
    """目标优先级"""
    CRITICAL = 0    # 系统关键
    HIGH = 1        # 高优先级
    NORMAL = 2      # 普通
    LOW = 3         # 低优先级


@dataclass
class Goal:
    """
    目标对象
    
    Attributes:
        goal_id: 唯一标识
        description: 目标描述
        status: 当前状态
        priority: 优先级
        parent_goal_id: 父目标ID（支持层级）
        sub_goals: 子目标ID列表
        context: 上下文（含 keywords 用于 relevance 计算）
        success_criteria: 成功标准
        created_at: 创建时间
        activated_at: 激活时间
        completed_at: 完成时间
        related_task_ids: 关联任务ID列表
        auto_completed: 是否自动完成
        result: 完成/失败的结果数据
    """
    goal_id: str
    description: str
    status: str  # GoalStatus value
    priority: int  # GoalPriority value
    
    # 层级关系
    parent_goal_id: Optional[str] = None
    sub_goals: List[str] = field(default_factory=list)
    
    # 上下文（⚠️ 中文必须手动提供 keywords）
    context: Dict[str, Any] = field(default_factory=dict)
    success_criteria: List[str] = field(default_factory=list)
    
    # 时间戳
    created_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # 关联
    related_task_ids: List[str] = field(default_factory=list)
    auto_completed: bool = False
    result: Optional[Dict[str, Any]] = None
    
    # 失败原因
    failure_reason: Optional[str] = None
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保 sub_goals 是列表
        if self.sub_goals is None:
            self.sub_goals = []
        # 确保 related_task_ids 是列表
        if self.related_task_ids is None:
            self.related_task_ids = []
        # 确保 context 是字典
        if self.context is None:
            self.context = {}
        # 确保 success_criteria 是列表
        if self.success_criteria is None:
            self.success_criteria = []
    
    @classmethod
    def create(
        cls,
        description: str,
        priority: GoalPriority = GoalPriority.NORMAL,
        parent_goal_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        success_criteria: Optional[List[str]] = None,
        goal_id: Optional[str] = None
    ) -> 'Goal':
        """
        创建新目标
        
        Example:
            goal = Goal.create(
                description="完成 Aeon v3.1 架构设计",
                priority=GoalPriority.HIGH,
                context={
                    "keywords": ["aeon", "v3.1", "architecture", "design"],
                    "notes": "基于朋朋的 review 反馈"
                },
                success_criteria=["文档完成", "代码实现", "测试通过"]
            )
        """
        return cls(
            goal_id=goal_id or str(uuid.uuid4()),
            description=description,
            status=GoalStatus.PENDING.value,
            priority=priority.value,
            parent_goal_id=parent_goal_id,
            context=context or {},
            success_criteria=success_criteria or []
        )
    
    def get_keywords(self) -> Set[str]:
        """
        提取关键词用于 relevance 计算
        
        ⚠️ 重要: 中文必须手动提供 keywords，不能依赖自动分词
        "完成架构设计".split() -> ["完成架构设计"] (无效)
        
        使用方式:
            context={"keywords": ["word1", "word2"]}
        """
        keywords = set()
        
        # 优先使用手动提供的 keywords
        manual_keywords = self.context.get("keywords", [])
        if manual_keywords:
            keywords.update([k.lower() for k in manual_keywords])
        
        # 英文描述可以简单 split 作为备选
        if self.description.isascii():
            keywords.update(self.description.lower().split())
        
        return keywords
    
    def activate(self) -> bool:
        """激活目标"""
        if self.status != GoalStatus.PENDING.value:
            return False
        
        self.status = GoalStatus.ACTIVE.value
        self.activated_at = time.time()
        return True
    
    def pause(self) -> bool:
        """暂停目标"""
        if self.status != GoalStatus.ACTIVE.value:
            return False
        
        self.status = GoalStatus.PAUSED.value
        return True
    
    def resume(self) -> bool:
        """恢复目标"""
        if self.status != GoalStatus.PAUSED.value:
            return False
        
        self.status = GoalStatus.ACTIVE.value
        return True
    
    def complete(self, result: Optional[Dict[str, Any]] = None, auto: bool = False) -> bool:
        """完成目标"""
        if self.status not in [GoalStatus.ACTIVE.value, GoalStatus.PAUSED.value]:
            return False
        
        self.status = GoalStatus.COMPLETED.value
        self.completed_at = time.time()
        self.result = result or {}
        self.auto_completed = auto
        return True
    
    def fail(self, reason: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """标记为失败"""
        if self.status not in [GoalStatus.ACTIVE.value, GoalStatus.PAUSED.value, GoalStatus.PENDING.value]:
            return False
        
        self.status = GoalStatus.FAILED.value
        self.completed_at = time.time()
        self.failure_reason = reason
        self.result = {
            "failure_reason": reason,
            "details": details or {}
        }
        return True
    
    def cancel(self) -> bool:
        """取消目标"""
        if self.status not in [GoalStatus.PENDING.value, GoalStatus.PAUSED.value]:
            return False
        
        self.status = GoalStatus.CANCELLED.value
        self.completed_at = time.time()
        return True
    
    def link_task(self, task_id: str):
        """关联任务"""
        if task_id not in self.related_task_ids:
            self.related_task_ids.append(task_id)
    
    def unlink_task(self, task_id: str):
        """解除任务关联"""
        if task_id in self.related_task_ids:
            self.related_task_ids.remove(task_id)
    
    def add_sub_goal(self, goal_id: str):
        """添加子目标"""
        if goal_id not in self.sub_goals:
            self.sub_goals.append(goal_id)
    
    def remove_sub_goal(self, goal_id: str):
        """移除子目标"""
        if goal_id in self.sub_goals:
            self.sub_goals.remove(goal_id)
    
    def is_terminal(self) -> bool:
        """检查是否已结束"""
        return self.status in [
            GoalStatus.COMPLETED.value,
            GoalStatus.FAILED.value,
            GoalStatus.CANCELLED.value
        ]
    
    def get_duration(self) -> Optional[float]:
        """获取持续时间（秒）"""
        if not self.activated_at:
            return None
        
        end_time = self.completed_at or time.time()
        return end_time - self.activated_at
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "parent_goal_id": self.parent_goal_id,
            "sub_goals": self.sub_goals,
            "context": self.context,
            "success_criteria": self.success_criteria,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "completed_at": self.completed_at,
            "related_task_ids": self.related_task_ids,
            "auto_completed": self.auto_completed,
            "result": self.result,
            "failure_reason": self.failure_reason,
            "keywords": list(self.get_keywords()),  # 方便调试
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Goal':
        """从字典创建"""
        return cls(
            goal_id=d["goal_id"],
            description=d["description"],
            status=d["status"],
            priority=d["priority"],
            parent_goal_id=d.get("parent_goal_id"),
            sub_goals=d.get("sub_goals", []),
            context=d.get("context", {}),
            success_criteria=d.get("success_criteria", []),
            created_at=d.get("created_at", time.time()),
            activated_at=d.get("activated_at"),
            completed_at=d.get("completed_at"),
            related_task_ids=d.get("related_task_ids", []),
            auto_completed=d.get("auto_completed", False),
            result=d.get("result"),
            failure_reason=d.get("failure_reason")
        )
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'Goal':
        """从数据库行创建"""
        return cls(
            goal_id=row[0],
            description=row[1],
            status=row[2],
            priority=row[3],
            parent_goal_id=row[4],
            sub_goals=json.loads(row[5]) if row[5] else [],
            context=json.loads(row[6]) if row[6] else {},
            success_criteria=json.loads(row[7]) if row[7] else [],
            created_at=row[8] or time.time(),
            activated_at=row[9],
            completed_at=row[10],
            related_task_ids=json.loads(row[11]) if row[11] else [],
            auto_completed=bool(row[12]) if row[12] else False,
            result=json.loads(row[13]) if row[13] else None,
            failure_reason=row[14]
        )
    
    def __repr__(self) -> str:
        return f"Goal({self.goal_id[:8]}... {self.status} '{self.description[:30]}...')"
    
    def __hash__(self) -> int:
        return hash(self.goal_id)
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Goal):
            return False
        return self.goal_id == other.goal_id
