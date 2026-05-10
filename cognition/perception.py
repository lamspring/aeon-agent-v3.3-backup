"""
PerceptionModule - 感知模块 v2.0 (从 cognition_loop.py 迁移)

职责：
- 读取环境信息（时间、系统状态、用户输入）
- 检测外部事件（消息、文件变化、系统告警）
- 维护对话上下文（WorldInput + EventBus + Attention + Task/Goal 缓存）

作者：虾虾
日期：2026-04-30
"""

import time
import psutil
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field


@dataclass
class Observation:
    """观察结果 (从 cognition_loop.py 迁移)"""
    timestamp: float
    events: List[Dict]
    tasks: List[Dict]
    goal: Optional[Dict]
    environment: Dict[str, Any]
    queue_size: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "events": self.events,
            "tasks": self.tasks,
            "goal": self.goal,
            "environment": self.environment,
            "queue_size": self.queue_size,
        }


@dataclass
class ContextCache:
    """上下文缓存 (从 cognition_loop.py 迁移)"""
    current_goal: Optional[Dict] = None
    active_tasks: List[Dict] = field(default_factory=list)
    recent_events: List[Dict] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    
    def update(self, events: List[Dict] = None, tasks: List[Dict] = None, goal: Dict = None):
        if events is not None:
            self.recent_events = events[-20:]
        if tasks is not None:
            self.active_tasks = [t for t in tasks if t.get('status') in ['pending', 'running']]
        if goal is not None:
            self.current_goal = goal
        self.last_updated = time.time()
    
    def has_new_events(self, since: float) -> bool:
        for event in self.recent_events:
            if event.get('timestamp', 0) > since:
                return True
        return False
    
    def has_active_tasks(self) -> bool:
        return len(self.active_tasks) > 0
    
    def is_stale(self, max_age: int = 30) -> bool:
        return time.time() - self.last_updated > max_age


class PerceptionModule:
    """
    感知模块 v2.0
    
    从 cognition_loop.py 的 _observe() 方法迁移而来。
    负责收集系统内外的所有输入信息。
    """
    
    def __init__(self,
                 event_bus=None,
                 goal_manager=None,
                 attention_manager=None,
                 world_input=None,
                 logger=None,
                 max_events_per_tick: int = 5):
        
        self.event_bus = event_bus
        self.goal_manager = goal_manager
        self.attention = attention_manager
        self.world_input = world_input
        self.logger = logger
        self.max_events_per_tick = max_events_per_tick
        
        self.context_cache = ContextCache()
        self.last_activity = time.time()
    
    def observe(self, tick_count: int) -> Observation:
        """
        观察阶段 (从 cognition_loop._observe 迁移)
        
        1. 收集 World Input (环境感知)
        2. 从 EventBus 获取待处理事件
        3. 使用 AttentionManager 过滤相关事件
        4. 更新 Task 缓存
        5. 更新 Goal 缓存
        """
        # 1. 收集 World Input
        world_context = {}
        if self.world_input:
            try:
                env_data = self.world_input.collect()
                world_context = {
                    "time": env_data.get("time", {}),
                    "system": env_data.get("system", {}),
                    "network": env_data.get("network", {}),
                    "alerts": env_data.get("alerts", []),
                }
                time_ctx = world_context.get("time", {})
                if time_ctx.get("special_day") and self.logger:
                    self.logger.info(f"Special day: {time_ctx['special_day']}")
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"World Input collection failed: {e}")
        
        # 2. 处理 EventBus 事件
        events_processed = 0
        try:
            if self.event_bus:
                events_processed = self.event_bus.process_pending(max_events=self.max_events_per_tick)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Event processing error: {e}")
            events_processed = 0
        
        pending_events = []
        
        # 3. 使用 AttentionManager 过滤
        attention_result = None
        relevant_events = []
        if self.attention:
            try:
                attention_result = self.attention.get_relevant_events(pending_events)
                relevant_events = attention_result.events
                if attention_result.total_scanned > 0 and self.logger:
                    self.logger.debug(
                        f"Attention: {attention_result.total_scanned} scanned, "
                        f"{len(relevant_events)} relevant"
                    )
            except:
                pass
        
        # 4. 刷新 Task 缓存
        tasks = []
        try:
            from tasks.task_system import TaskPersistence
            persistence = TaskPersistence()
            pending = persistence.get_pending_tasks()
            running = persistence.get_running_tasks()
            tasks = [t.to_dict() for t in pending + running]
        except:
            tasks = []
        
        # 5. 刷新 Goal 缓存
        goal = None
        goal_dict = None
        if self.goal_manager:
            try:
                goal = self.goal_manager.get_active_goal()
                goal_dict = goal.to_dict() if goal else None
            except:
                pass
        
        # 更新缓存
        self.context_cache.update(events=relevant_events, tasks=tasks, goal=goal_dict)
        
        # 构建环境信息
        environment = {
            "tick_count": tick_count,
            "last_activity": self.last_activity,
            "cache_age": time.time() - self.context_cache.last_updated,
            "goal_id": goal.goal_id[:8] if goal else None,
            "world": world_context,
            "events_processed": events_processed,
            "attention": attention_result.to_dict() if attention_result else {},
        }
        
        queue_size = 0
        if self.event_bus:
            try:
                queue_size = self.event_bus.get_queue_size()
            except:
                pass
        
        return Observation(
            timestamp=time.time(),
            events=relevant_events,
            tasks=tasks,
            goal=goal_dict,
            environment=environment,
            queue_size=queue_size,
        )
    
    def get_user_context(self) -> Dict:
        """获取用户上下文"""
        return {
            "has_active_tasks": self.context_cache.has_active_tasks(),
            "current_goal": self.context_cache.current_goal,
            "cache_age": time.time() - self.context_cache.last_updated,
        }
    
    def check_health(self) -> bool:
        """检查感知模块健康状态"""
        return self.event_bus is not None
    
    def get_environment_summary(self) -> Dict:
        """获取环境摘要（用于 Trace 日志）"""
        try:
            memory_percent = psutil.virtual_memory().percent
        except:
            memory_percent = 0.0
        
        return {
            "memory_percent": memory_percent,
            "cache_age": time.time() - self.context_cache.last_updated,
        }
    
    def get_user_context(self) -> Dict:
        """获取用户上下文（话题、情绪）"""
        if not self.dialogue_reader:
            return {}
        
        try:
            return self.dialogue_reader.get_user_context()
        except:
            return {}
    
    def check_health(self) -> bool:
        """检查感知模块健康状态"""
        # 检查关键依赖是否可用
        checks = [
            self.event_bus is not None,
            self.dialogue_reader is not None,
        ]
        return all(checks)
    
    def _get_time_of_day(self) -> str:
        """获取当前时间段"""
        import datetime
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 22:
            return "evening"
        else:
            return "night"
    
    def _get_weekday(self) -> str:
        """获取星期几"""
        import datetime
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return weekdays[datetime.datetime.now().weekday()]


# ============== 快速测试 ==============
if __name__ == "__main__":
    pm = PerceptionModule()
    obs = pm.observe(tick_count=1)
    print("=== PerceptionModule v1.0 ===")
    print(f"Observed: {obs['tick_count']}, time: {obs['environment']['time_of_day']}")
    print(f"Health: {pm.check_health()}")
    print("✅ PerceptionModule skeleton ready")
