"""
Cognition Loop - 认知循环
核心特性:
- OODA 循环 (Observe → Plan → Act → Reflect)
- IDLE 状态检测 (无事件时跳过)
- LLM 低频触发 (rules优先)
- Context Cache (避免频繁Vector Search)
"""

import json
import time
import threading
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from bus.event_bus import get_event_bus, Event, EventType, listener
from utils.structured_log import get_logger, LogContext

logger = get_logger()


class CognitionState(Enum):
    """认知状态"""
    IDLE = "idle"           # 空闲
    OBSERVING = "observing" # 观察中
    PLANNING = "planning"   # 规划中
    ACTING = "acting"       # 执行中
    REFLECTING = "reflecting" # 反思中


@dataclass
class ContextCache:
    """
    上下文缓存
    
    避免每次cognition都查Vector DB
    """
    current_goal: Optional[Dict] = None
    active_tasks: List[Dict] = field(default_factory=list)
    recent_events: List[Dict] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    
    def update(self, events: List[Dict] = None, tasks: List[Dict] = None, goal: Dict = None):
        """更新缓存"""
        if events is not None:
            self.recent_events = events[-20:]  # 保留最近20个
        if tasks is not None:
            self.active_tasks = [t for t in tasks if t.get('status') in ['pending', 'running']]
        if goal is not None:
            self.current_goal = goal
        
        self.last_updated = time.time()
    
    def has_new_events(self, since: float) -> bool:
        """检查是否有新事件"""
        for event in self.recent_events:
            if event.get('timestamp', 0) > since:
                return True
        return False
    
    def has_active_tasks(self) -> bool:
        """检查是否有活跃任务"""
        return len(self.active_tasks) > 0
    
    def has_current_goal(self) -> bool:
        """检查是否有当前目标"""
        return self.current_goal is not None
    
    def is_stale(self, max_age: int = 30) -> bool:
        """检查缓存是否过期"""
        return time.time() - self.last_updated > max_age
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "current_goal": self.current_goal,
            "active_tasks": self.active_tasks,
            "recent_events_count": len(self.recent_events),
            "last_updated": self.last_updated
        }


@dataclass
class Observation:
    """观察结果"""
    timestamp: float
    events: List[Dict]
    tasks: List[Dict]
    goal: Optional[Dict]
    environment: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "events": self.events,
            "tasks": self.tasks,
            "goal": self.goal,
            "environment": self.environment
        }


@dataclass
class Plan:
    """规划结果"""
    plan_id: str
    goal: str
    steps: List[Dict]
    estimated_time: int  # 分钟
    created_at: float
    
    def to_dict(self) -> Dict:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": self.steps,
            "estimated_time": self.estimated_time,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat()
        }


class PlanCache:
    """
    规划缓存
    
    避免相同目标重复规划
    """
    
    def __init__(self, ttl: int = 3600):  # 默认1小时
        self.cache: Dict[str, Dict] = {}  # goal_hash -> {plan, timestamp}
        self.ttl = ttl
        self._lock = threading.Lock()
    
    def _hash_goal(self, goal: str) -> str:
        """生成目标哈希"""
        import hashlib
        return hashlib.md5(goal.encode()).hexdigest()[:16]
    
    def get(self, goal: str) -> Optional[Plan]:
        """获取缓存的规划"""
        goal_hash = self._hash_goal(goal)
        
        with self._lock:
            if goal_hash in self.cache:
                cached = self.cache[goal_hash]
                if time.time() - cached['timestamp'] < self.ttl:
                    logger.debug(f"Plan cache hit for: {goal[:50]}...")
                    return cached['plan']
                else:
                    # 过期，删除
                    del self.cache[goal_hash]
        
        return None
    
    def set(self, goal: str, plan: Plan):
        """缓存规划"""
        goal_hash = self._hash_goal(goal)
        
        with self._lock:
            self.cache[goal_hash] = {
                'plan': plan,
                'timestamp': time.time(),
                'goal': goal
            }
    
    def invalidate(self, goal_pattern: str = None):
        """使缓存失效"""
        with self._lock:
            if goal_pattern:
                # 删除匹配pattern的缓存
                to_delete = [
                    k for k, v in self.cache.items()
                    if goal_pattern in v.get('goal', '')
                ]
                for k in to_delete:
                    del self.cache[k]
            else:
                # 清空所有
                self.cache.clear()
    
    def cleanup(self):
        """清理过期缓存"""
        with self._lock:
            cutoff = time.time() - self.ttl
            to_delete = [
                k for k, v in self.cache.items()
                if v['timestamp'] < cutoff
            ]
            for k in to_delete:
                del self.cache[k]


class CognitionLoop:
    """
    认知循环
    
    实现 OODA 循环:
    Observe → Orient/Plan → Act → Reflect
    
    特性:
    - IDLE状态检测 (无事件时跳过tick)
    - LLM低频触发 (rules优先)
    - Plan缓存
    - Context Cache (避免Vector Search)
    """
    
    def __init__(
        self,
        tick_interval: int = 30,        # 30秒tick一次
        idle_timeout: int = 300,         # 5分钟无活动进入IDLE
        enable_llm: bool = True,
        llm_threshold: int = 5           # 5次tick后才可能触发LLM
    ):
        self.tick_interval = tick_interval
        self.idle_timeout = idle_timeout
        self.enable_llm = enable_llm
        self.llm_threshold = llm_threshold
        
        self.event_bus = get_event_bus()
        self.logger = get_logger()
        self.context_cache = ContextCache()
        self.plan_cache = PlanCache()
        
        self.state = CognitionState.IDLE
        self.tick_count = 0
        self.last_activity = time.time()
        self.last_plan_time = 0
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # 规则处理器 (高频，无需LLM)
        self.rule_handlers: Dict[str, Callable] = {}
        
        # LLM规划器 (低频)
        self.llm_planner: Optional[Callable] = None
        
        # 订阅事件
        self._subscribe_events()
    
    def _subscribe_events(self):
        """订阅事件更新缓存"""
        @listener(EventType.TASK_STARTED.value)
        def on_task_started(event):
            self._update_cache()
        
        @listener(EventType.TASK_FINISHED.value)
        def on_task_finished(event):
            self._update_cache()
        
        @listener(EventType.MESSAGE_RECEIVED.value)
        def on_message(event):
            self._update_cache()
            self.last_activity = time.time()
    
    def _update_cache(self):
        """更新上下文缓存"""
        # 从Task系统获取数据
        from tasks.task_system import TaskPersistence
        
        persistence = TaskPersistence()
        pending = persistence.get_pending_tasks()
        running = persistence.get_running_tasks()
        
        self.context_cache.update(
            tasks=[t.to_dict() for t in pending + running]
        )
    
    def register_rule_handler(self, trigger: str, handler: Callable):
        """注册规则处理器"""
        self.rule_handlers[trigger] = handler
    
    def set_llm_planner(self, planner: Callable):
        """设置LLM规划器"""
        self.llm_planner = planner
    
    def start(self):
        """启动认知循环"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        self.logger.info(
            "CognitionLoop started",
            component="CognitionLoop",
            context={"tick_interval": self.tick_interval}
        )
    
    def stop(self):
        """停止认知循环"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _loop(self):
        """主循环"""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                self.logger.error(
                    f"Cognition tick error: {e}",
                    component="CognitionLoop"
                )
            
            time.sleep(self.tick_interval)
    
    def tick(self):
        """
        单次认知tick
        
        流程:
        1. 检查IDLE状态 (无事件/任务/目标 → 跳过)
        2. Observe (读取Context Cache)
        3. 判断是否需要LLM (低频)
        4. Plan (LLM或规则)
        5. Act (发布事件)
        6. Reflect (可选)
        """
        self.tick_count += 1
        
        # === 1. IDLE检测 ===
        if self._is_idle():
            if self.state != CognitionState.IDLE:
                self.state = CognitionState.IDLE
                self.logger.debug(
                    "IDLE state, skipping tick",
                    component="CognitionLoop"
                )
            return
        
        with self._lock:
            self.state = CognitionState.OBSERVING
        
        # === 2. Observe ===
        observation = self._observe()
        
        self.logger.debug(
            f"Tick {self.tick_count}: {len(observation.events)} events, "
            f"{len(observation.tasks)} tasks",
            component="CognitionLoop",
            context=observation.to_dict()
        )
        
        # === 3. 判断是否需要规划 ===
        if not self._needs_planning(observation):
            return
        
        with self._lock:
            self.state = CognitionState.PLANNING
        
        # === 4. Plan ===
        plan = self._plan(observation)
        
        if not plan:
            return
        
        # === 5. Act ===
        with self._lock:
            self.state = CognitionState.ACTING
        
        self._act(plan, observation)
        
        # === 6. Reflect (可选，非每tick都做) ===
        if self.tick_count % 10 == 0:  # 每10次tick反思一次
            with self._lock:
                self.state = CognitionState.REFLECTING
            self._reflect(observation, plan)
        
        with self._lock:
            self.state = CognitionState.IDLE
    
    def _is_idle(self) -> bool:
        """
        检查是否处于IDLE状态
        
        条件:
        - 无新事件
        - 无活跃任务
        - 无当前目标
        - 5分钟无活动
        """
        return (
            not self.context_cache.has_new_events(self.last_activity) and
            not self.context_cache.has_active_tasks() and
            not self.context_cache.has_current_goal() and
            time.time() - self.last_activity > self.idle_timeout
        )
    
    def _observe(self) -> Observation:
        """
        观察阶段
        
        读取Context Cache (O(1)，无需Vector Search)
        """
        # 刷新缓存
        self._update_cache()
        
        # 获取最近事件 (从缓存)
        recent_events = self.context_cache.recent_events
        
        # 获取任务状态
        tasks = self.context_cache.active_tasks
        
        # 获取当前目标
        goal = self.context_cache.current_goal
        
        # 环境信息
        environment = {
            "tick_count": self.tick_count,
            "last_activity": self.last_activity,
            "state": self.state.value,
            "cache_age": time.time() - self.context_cache.last_updated
        }
        
        return Observation(
            timestamp=time.time(),
            events=recent_events,
            tasks=tasks,
            goal=goal,
            environment=environment
        )
    
    def _needs_planning(self, observation: Observation) -> bool:
        """
        判断是否需要规划
        
        触发条件:
        - 用户发送了新消息
        - 任务失败
        - 系统状态异常
        - 长时间没有规划 (>10分钟)
        """
        # 有未处理的用户消息
        for event in observation.events:
            if event.get('type') == EventType.MESSAGE_RECEIVED.value:
                return True
        
        # 有失败的任务
        for task in observation.tasks:
            if task.get('status') == 'failed':
                return True
        
        # 长时间没有规划
        if time.time() - self.last_plan_time > 600:  # 10分钟
            return True
        
        # 有目标但没有活跃任务
        if observation.goal and not observation.tasks:
            return True
        
        return False
    
    def _plan(self, observation: Observation) -> Optional[Plan]:
        """
        规划阶段
        
        优先使用规则，必要时调用LLM
        """
        goal = observation.goal.get('description') if observation.goal else None
        
        # 1. 检查Plan Cache
        if goal:
            cached_plan = self.plan_cache.get(goal)
            if cached_plan:
                return cached_plan
        
        # 2. 尝试规则匹配 (高频，无需LLM)
        for trigger, handler in self.rule_handlers.items():
            if self._match_trigger(trigger, observation):
                plan = handler(observation)
                if plan:
                    self.logger.info(
                        f"Rule-based plan generated: {trigger}",
                        component="CognitionLoop"
                    )
                    return plan
        
        # 3. 低频: 调用LLM规划
        if self.enable_llm and self.llm_planner:
            # 限制LLM调用频率
            if self.tick_count >= self.llm_threshold:
                plan = self._llm_plan(observation)
                if plan and goal:
                    self.plan_cache.set(goal, plan)
                return plan
        
        return None
    
    def _match_trigger(self, trigger: str, observation: Observation) -> bool:
        """匹配触发条件"""
        # 简单实现: 检查事件类型
        for event in observation.events:
            if event.get('type') == trigger:
                return True
        return False
    
    def _llm_plan(self, observation: Observation) -> Optional[Plan]:
        """调用LLM进行规划"""
        if not self.llm_planner:
            return None
        
        self.logger.info(
            "Calling LLM for planning",
            component="CognitionLoop"
        )
        
        try:
            plan = self.llm_planner(observation.to_dict())
            self.last_plan_time = time.time()
            return plan
        except Exception as e:
            self.logger.error(
                f"LLM planning failed: {e}",
                component="CognitionLoop"
            )
            return None
    
    def _act(self, plan: Plan, observation: Observation):
        """
        执行阶段
        
        发布事件到Bus，由Task Planner处理
        """
        self.logger.info(
            f"Executing plan: {plan.goal}",
            component="CognitionLoop",
            context=plan.to_dict()
        )
        
        # 发布规划事件
        self.event_bus.publish_simple(
            EventType.COGNITION_PLAN.value,
            {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "steps": plan.steps,
                "estimated_time": plan.estimated_time
            },
            trace_id=observation.goal.get('trace_id') if observation.goal else None
        )
        
        self.last_activity = time.time()
    
    def _reflect(self, observation: Observation, plan: Plan):
        """
        反思阶段
        
        评估执行效果，更新策略
        (非每tick都做)
        """
        self.logger.debug(
            "Reflecting on last actions",
            component="CognitionLoop"
        )
        
        # 发布反思事件
        self.event_bus.publish_simple(
            EventType.COGNITION_REFLECT.value,
            {
                "tick_count": self.tick_count,
                "last_plan": plan.to_dict() if plan else None,
                "observation": observation.to_dict()
            }
        )
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "state": self.state.value,
            "tick_count": self.tick_count,
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
            "last_plan_time": datetime.fromtimestamp(self.last_plan_time).isoformat() if self.last_plan_time else None,
            "is_idle": self._is_idle(),
            "cache": self.context_cache.to_dict()
        }


# 全局实例
_cognition_instance: Optional[CognitionLoop] = None


def get_cognition() -> CognitionLoop:
    """获取全局认知循环实例"""
    global _cognition_instance
    if _cognition_instance is None:
        _cognition_instance = CognitionLoop()
    return _cognition_instance


def set_cognition(cognition: CognitionLoop):
    """设置全局认知循环实例"""
    global _cognition_instance
    _cognition_instance = cognition