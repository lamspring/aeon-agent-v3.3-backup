"""
Goal Manager - 目标管理器

核心功能:
- Goal 生命周期管理 (create, activate, complete, fail)
- 原子激活 (保证只有一个 active goal)
- 自动完成检查 (所有任务完成后自动 complete)
- 启动恢复 (recover_on_startup)
- 与 Task 系统集成
"""

import time
import logging
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from goals.models import Goal, GoalStatus, GoalPriority
from goals.goal_store import GoalStore

logger = logging.getLogger(__name__)


class GoalManager:
    """
    目标管理器
    
    职责:
    1. Goal CRUD
    2. 状态流转 (原子操作保证)
    3. 自动完成检查
    4. 启动恢复
    5. 发布 Goal 相关事件
    """
    
    def __init__(
        self,
        store: Optional[GoalStore] = None,
        event_bus=None  # 可选，用于发布事件
    ):
        self.store = store or GoalStore()
        self.event_bus = event_bus
        
        # 状态变化回调
        self.on_goal_activated: Optional[Callable[[Goal], None]] = None
        self.on_goal_completed: Optional[Callable[[Goal], None]] = None
        self.on_goal_failed: Optional[Callable[[Goal], None]] = None
        
        logger.info("GoalManager initialized")
    
    # ==================== CRUD ====================
    
    def create_goal(
        self,
        description: str,
        priority: GoalPriority = GoalPriority.NORMAL,
        parent_goal_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        success_criteria: Optional[List[str]] = None,
        auto_activate: bool = False
    ) -> Goal:
        """
        创建目标
        
        Args:
            description: 目标描述
            priority: 优先级
            parent_goal_id: 父目标ID
            context: 上下文（⚠️ 必须包含 keywords）
            success_criteria: 成功标准
            auto_activate: 是否立即激活（如果没有其他active goal）
        
        Returns:
            创建的 Goal 对象
        
        Example:
            goal = goal_manager.create_goal(
                description="完成 Aeon v3.1 架构设计",
                priority=GoalPriority.HIGH,
                context={
                    "keywords": ["aeon", "v3.1", "architecture", "design"],
                    "notes": "基于朋朋的 review 反馈"
                },
                success_criteria=["文档完成", "代码实现", "测试通过"]
            )
        """
        # 确保中文有 keywords
        if context is None:
            context = {}
        
        if not description.isascii() and "keywords" not in context:
            logger.warning(
                f"Goal '{description[:30]}...' is Chinese but no keywords provided. "
                "Relevance calculation may not work correctly."
            )
        
        goal = Goal.create(
            description=description,
            priority=priority,
            parent_goal_id=parent_goal_id,
            context=context,
            success_criteria=success_criteria
        )
        
        self.store.save(goal)
        logger.info(f"Goal created: {goal.goal_id[:8]}... '{description[:40]}'")
        
        # 发布事件
        if self.event_bus:
            self.event_bus.publish_simple(
                "goal.created",
                {"goal_id": goal.goal_id, "description": description}
            )
        
        # 自动激活
        if auto_activate:
            self.activate_next_pending()
        
        return goal
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """获取目标"""
        return self.store.get_by_id(goal_id)
    
    def get_active_goal(self) -> Optional[Goal]:
        """获取当前活跃目标"""
        return self.store.get_active()
    
    def get_pending_goals(self, limit: int = 10) -> List[Goal]:
        """获取待处理目标"""
        return self.store.get_pending(limit)
    
    def list_goals(self) -> List[Goal]:
        """获取所有活跃和待处理目标"""
        return self.store.get_all_active_and_pending()
    
    def get_goal_by_task(self, task_id: str) -> Optional[Goal]:
        """通过任务ID查找目标"""
        return self.store.get_by_task_id(task_id)
    
    # ==================== 状态流转 ====================
    
    def activate_next_pending(self) -> Optional[Goal]:
        """
        原子激活下一个待处理目标
        
        使用 SQL 保证永远只有一个 active goal
        
        Returns:
            被激活的 Goal，如果没有则返回 None
        """
        # 检查是否已有 active goal
        active = self.store.get_active()
        if active:
            logger.debug(f"Already have active goal: {active.goal_id[:8]}...")
            return None
        
        # 原子激活（SQL保证只有一个active）
        from goals.goal_store import sqlite3
        
        with sqlite3.connect(self.store.db_path) as conn:
            cursor = conn.execute("""
                UPDATE goals
                SET status = 'active', activated_at = ?
                WHERE goal_id = (
                    SELECT goal_id FROM goals
                    WHERE status = 'pending'
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                )
                AND NOT EXISTS (
                    SELECT 1 FROM goals WHERE status = 'active'
                )
                RETURNING *
            """, (time.time(),))
            
            row = cursor.fetchone()
            conn.commit()
            
            if row:
                goal = Goal.from_db_row(row)
                logger.info(f"Goal activated: {goal.goal_id[:8]}... '{goal.description[:40]}'")
                
                # 发布事件
                if self.event_bus:
                    self.event_bus.publish_simple(
                        "goal.activated",
                        {"goal_id": goal.goal_id, "description": goal.description}
                    )
                
                # 回调
                if self.on_goal_activated:
                    self.on_goal_activated(goal)
                
                return goal
        
        return None
    
    def complete_goal(
        self,
        goal_id: str,
        result: Optional[Dict[str, Any]] = None,
        auto: bool = False
    ) -> bool:
        """
        完成目标
        
        Args:
            goal_id: 目标ID
            result: 结果数据
            auto: 是否自动完成
        
        Returns:
            是否成功
        """
        goal = self.store.get_by_id(goal_id)
        if not goal:
            logger.warning(f"Goal not found: {goal_id}")
            return False
        
        if not goal.complete(result=result, auto=auto):
            logger.warning(f"Cannot complete goal {goal_id}: status={goal.status}")
            return False
        
        self.store.save(goal)
        logger.info(f"Goal completed{' (auto)' if auto else ''}: {goal_id[:8]}...")
        
        # 发布事件
        if self.event_bus:
            self.event_bus.publish_simple(
                "goal.completed",
                {
                    "goal_id": goal.goal_id,
                    "description": goal.description,
                    "auto_completed": auto,
                    "result": result
                }
            )
        
        # 回调
        if self.on_goal_completed:
            self.on_goal_completed(goal)
        
        # v2: 发送完成通知
        try:
            import sys
            sys.path.insert(0, '/root/.openclaw/workspace/agent')
            from alert import get_alert_manager
            alert = get_alert_manager()
            alert.on_goal_completed(goal_id, goal.description, auto=auto)
        except Exception as e:
            logger.debug(f"Failed to send goal completion alert: {e}")
        
        # 自动激活下一个
        self.activate_next_pending()
        
        return True
    
    def fail_goal(
        self,
        goal_id: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        标记目标为失败
        
        Args:
            goal_id: 目标ID
            reason: 失败原因（如 "planning_failed", "unplannable"）
            details: 详细信息
        
        Returns:
            是否成功
        """
        goal = self.store.get_by_id(goal_id)
        if not goal:
            logger.warning(f"Goal not found: {goal_id}")
            return False
        
        if not goal.fail(reason, details):
            logger.warning(f"Cannot fail goal {goal_id}: status={goal.status}")
            return False
        
        self.store.save(goal)
        logger.info(f"Goal failed: {goal_id[:8]}... reason={reason}")
        
        # 发布事件
        if self.event_bus:
            self.event_bus.publish_simple(
                "goal.failed",
                {
                    "goal_id": goal.goal_id,
                    "description": goal.description,
                    "reason": reason,
                    "details": details
                }
            )
        
        # v2: 发送告警通知
        try:
            import sys
            sys.path.insert(0, '/root/.openclaw/workspace/agent')
            from alert import get_alert_manager
            alert = get_alert_manager()
            alert.on_goal_failed(goal_id, goal.description, reason)
        except Exception as e:
            logger.debug(f"Failed to send goal failure alert: {e}")
        
        # 回调
        if self.on_goal_failed:
            self.on_goal_failed(goal)
        
        # 自动激活下一个
        self.activate_next_pending()
        
        return True
    
    def pause_goal(self, goal_id: str) -> bool:
        """暂停目标"""
        goal = self.store.get_by_id(goal_id)
        if not goal or not goal.pause():
            return False
        
        self.store.save(goal)
        logger.info(f"Goal paused: {goal_id[:8]}...")
        return True
    
    def resume_goal(self, goal_id: str) -> bool:
        """恢复目标"""
        goal = self.store.get_by_id(goal_id)
        if not goal or not goal.resume():
            return False
        
        self.store.save(goal)
        logger.info(f"Goal resumed: {goal_id[:8]}...")
        
        # 如果有其他 active goal，需要先暂停它
        # （这里简化处理，实际应该原子操作）
        
        return True
    
    def cancel_goal(self, goal_id: str) -> bool:
        """取消目标"""
        goal = self.store.get_by_id(goal_id)
        if not goal or not goal.cancel():
            return False
        
        self.store.save(goal)
        logger.info(f"Goal cancelled: {goal_id[:8]}...")
        
        # 如果取消的是 active goal，激活下一个
        if goal.status == GoalStatus.ACTIVE.value:
            self.activate_next_pending()
        
        return True
    
    # ==================== 自动完成检查 ====================
    
    def check_and_complete(self, goal_id: str) -> bool:
        """
        检查目标是否应该自动完成
        
        保护条件:
        - 无关联任务 → 标记为失败 (planning_failed)
        - 所有任务完成 → 标记为完成
        - 部分任务失败 → 仍标记为完成 (记录失败数)
        
        Returns:
            True: 已完成或已失败
            False: 仍需等待
        """
        goal = self.store.get_by_id(goal_id)
        if not goal or goal.status != GoalStatus.ACTIVE.value:
            return False
        
        # 保护条件1: 无关联任务 = 规划失败
        if not goal.related_task_ids:
            self.fail_goal(
                goal_id,
                reason="planning_failed",
                details={"error": "No tasks generated after planning"}
            )
            return True
        
        # 获取关联任务（需要 Task 系统支持）
        try:
            from tasks.task_system import TaskPersistence
            task_store = TaskPersistence()
            tasks = task_store.get_by_ids(goal.related_task_ids)
        except Exception as e:
            logger.error(f"Failed to get tasks for goal {goal_id}: {e}")
            return False
        
        # 保护条件2: 任务列表为空 (可能被删除)
        if not tasks:
            self.fail_goal(
                goal_id,
                reason="tasks_missing",
                details={"error": "All related tasks deleted or missing"}
            )
            return True
        
        # 检查是否全部完成
        all_done = all(
            t.status in ["finished", "failed"]
            for t in tasks
        )
        
        if all_done:
            finished = sum(1 for t in tasks if t.status == "finished")
            failed = len(tasks) - finished
            
            self.complete_goal(
                goal_id,
                result={
                    "auto_completed": True,
                    "tasks_total": len(tasks),
                    "tasks_finished": finished,
                    "tasks_failed": failed,
                    "completion_rate": finished / len(tasks) if tasks else 0
                },
                auto=True
            )
            return True
        
        return False
    
    def on_task_finished(self, task_id: str):
        """
        任务完成时的回调
        
        检查关联目标是否应该自动完成
        """
        goal = self.store.get_by_task_id(task_id)
        if goal:
            self.check_and_complete(goal.goal_id)
    
    # ==================== 启动恢复 ====================
    
    def recover_on_startup(self) -> Dict[str, Any]:
        """
        启动时恢复 Goal 状态
        
        策略:
        - 如果有 active goal: 继续执行
        - 如果没有 active goal: 尝试激活 pending goal
        
        Returns:
            恢复结果信息
        """
        logger.info("Recovering goals on startup...")
        
        active = self.store.get_active()
        if active:
            logger.info(f"Resumed active goal: {active.goal_id[:8]}...")
            return {
                "status": "resumed",
                "goal_id": active.goal_id,
                "description": active.description
            }
        
        # 没有 active goal，尝试激活一个
        activated = self.activate_next_pending()
        if activated:
            return {
                "status": "activated",
                "goal_id": activated.goal_id,
                "description": activated.description
            }
        
        # 没有 pending goal
        return {"status": "no_goals"}
    
    # ==================== 工具方法 ====================
    
    def link_task(self, goal_id: str, task_id: str) -> bool:
        """关联任务到目标"""
        return self.store.link_task(goal_id, task_id)
    
    def unlink_task(self, goal_id: str, task_id: str) -> bool:
        """解除任务关联"""
        return self.store.unlink_task(goal_id, task_id)
    
    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息"""
        return self.store.count_by_status()
    
    def print_status(self):
        """打印当前状态（用于调试）"""
        stats = self.get_statistics()
        active = self.get_active_goal()
        pending = self.get_pending_goals(limit=5)
        
        print("\n=== Goal Manager Status ===")
        print(f"Statistics: {stats}")
        
        if active:
            print(f"\nActive: {active.goal_id[:8]}... '{active.description[:40]}'")
        else:
            print("\nActive: None")
        
        if pending:
            print(f"\nPending ({len(pending)}):")
            for g in pending:
                print(f"  - {g.goal_id[:8]}... [P{g.priority}] '{g.description[:40]}'")
        else:
            print("\nPending: None")
        
        print("===========================\n")


# 全局实例
_goal_manager_instance: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    """获取全局 GoalManager 实例"""
    global _goal_manager_instance
    if _goal_manager_instance is None:
        _goal_manager_instance = GoalManager()
    return _goal_manager_instance


def set_goal_manager(manager: GoalManager):
    """设置全局 GoalManager 实例"""
    global _goal_manager_instance
    _goal_manager_instance = manager
