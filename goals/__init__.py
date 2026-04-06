"""
Goals Module - 目标管理

核心组件:
- models: Goal, GoalStatus, GoalPriority 数据模型
- goal_store: SQLite 持久化
- goal_manager: 生命周期管理 + 自动完成

快速开始:
    from goals import GoalManager, GoalPriority
    
    gm = GoalManager()
    
    # 创建目标
    goal = gm.create_goal(
        description="完成 Aeon v3.1 架构设计",
        priority=GoalPriority.HIGH,
        context={"keywords": ["aeon", "architecture"]}
    )
    
    # 激活目标
    gm.activate_next_pending()
    
    # 关联任务
    gm.link_task(goal.goal_id, task_id)
    
    # 任务完成时自动检查
    gm.on_task_finished(task_id)
"""

from goals.models import Goal, GoalStatus, GoalPriority
from goals.goal_store import GoalStore
from goals.goal_manager import GoalManager, get_goal_manager, set_goal_manager

__all__ = [
    'Goal',
    'GoalStatus',
    'GoalPriority',
    'GoalStore',
    'GoalManager',
    'get_goal_manager',
    'set_goal_manager',
]
