"""
Cognition Loop v2.1 - 认知循环（集成 Goal & Attention & World Input）

核心特性:
- OODA 循环 (Observe → Plan → Act → Reflect)
- EventBus v2 集成 (处理 pending 事件)
- GoalManager 集成 (当前目标上下文)
- Attention System (优先级排序)
- World Input (环境感知 - 时间、系统状态、网络)
- Trace 日志 (tick, goal, events, queue, mem, time)
- IDLE 状态检测
"""

import json
import time
import threading
import uuid
import psutil
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from bus.event_bus_v2 import get_event_bus, EventBus, EventConfig
from goals import GoalManager, GoalPriority, get_goal_manager
from attention import AttentionManager, get_attention_manager, AttentionConfig
from utils.structured_log import get_logger, LogContext

# v2.1: 导入 World Input
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')
try:
    from world_input import WorldInput
    WORLD_INPUT_AVAILABLE = True
except ImportError:
    WORLD_INPUT_AVAILABLE = False
    WorldInput = None

logger = get_logger()


def generate_tick_id() -> str:
    """生成 tick ID"""
    return str(uuid.uuid4())[:8]


class CognitionState(Enum):
    """认知状态"""
    IDLE = "idle"
    OBSERVING = "observing"
    PLANNING = "planning"
    ACTING = "acting"
    REFLECTING = "reflecting"


@dataclass
class ContextCache:
    """上下文缓存"""
    current_goal: Optional[Dict] = None
    active_tasks: List[Dict] = field(default_factory=list)
    recent_events: List[Dict] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    
    def update(self, events: List[Dict] = None, tasks: List[Dict] = None, goal: Dict = None):
        """更新缓存"""
        if events is not None:
            self.recent_events = events[-20:]
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


@dataclass
class Observation:
    """观察结果"""
    timestamp: float
    events: List[Dict]
    tasks: List[Dict]
    goal: Optional[Dict]
    environment: Dict[str, Any]
    queue_size: int = 0  # v2: 队列大小
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "events": self.events,
            "tasks": self.tasks,
            "goal": self.goal,
            "environment": self.environment,
            "queue_size": self.queue_size,
        }


class CognitionLoop:
    """
    认知循环 v2.0
    
    集成:
    - EventBus v2 (处理 pending 事件)
    - GoalManager (当前目标上下文)
    - Trace 日志 (7个字段)
    """
    
    def __init__(
        self,
        tick_interval: int = 30,
        idle_timeout: int = 300,
        enable_llm: bool = True,
        llm_threshold: int = 5,
        max_events_per_tick: int = 5,  # v2: 每轮处理事件数上限
    ):
        self.tick_interval = tick_interval
        self.idle_timeout = idle_timeout
        self.enable_llm = enable_llm
        self.llm_threshold = llm_threshold
        self.max_events_per_tick = max_events_per_tick
        
        # v2: 使用 EventBus v2
        self.event_bus: EventBus = get_event_bus()
        
        # v2: GoalManager
        self.goal_manager: GoalManager = get_goal_manager()
        
        # v2: AttentionManager
        self.attention: AttentionManager = get_attention_manager()
        
        # 初始化logger（必须在world_input之前）
        self.logger = get_logger()
        self.context_cache = ContextCache()
        
        # v2.1: World Input (环境感知)
        self.world_input = None
        if WORLD_INPUT_AVAILABLE:
            try:
                self.world_input = WorldInput()
                self.logger.info("World Input initialized", component="CognitionLoop")
            except Exception as e:
                self.logger.warning(f"Failed to initialize World Input: {e}", component="CognitionLoop")
        
        # === v3.3: 元认知模块集成 (虾虾 2026-05-01) ===
        self.reflection_module = None
        self.planning_module = None
        self.execution_module = None
        
        # 初始化 ReflectionModule（元认知核心）
        try:
            from reflection import ReflectionModule
            self.reflection_module = ReflectionModule(
                event_bus=self.event_bus,
                mimo_api_key=None,  # 使用默认
                logger=self.logger,
            )
            self.logger.info("ReflectionModule v2.0 integrated", component="CognitionLoop")
        except Exception as e:
            self.logger.warning(f"ReflectionModule init failed: {e}", component="CognitionLoop")
        
        # 初始化自省计数器
        self.last_introspection_tick = 0
        self.introspection_interval = 50  # 每50 tick自省一次
        
        # === v3.3 集成结束 ===
        
        self.state = CognitionState.IDLE
        self.tick_count = 0
        self.last_activity = time.time()
        self.last_plan_time = 0
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # 规则处理器
        self.rule_handlers: Dict[str, Callable] = {}
        self.llm_planner: Optional[Callable] = None
    
    def start(self):
        """启动认知循环"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        self.logger.info(
            "CognitionLoop v2.1 started (with World Input)",
            component="CognitionLoop",
            context={
                "tick_interval": self.tick_interval,
                "max_events": self.max_events_per_tick,
                "world_input": WORLD_INPUT_AVAILABLE and self.world_input is not None
            }
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
                self.logger.error(f"Cognition tick error: {e}", component="CognitionLoop")
            
            time.sleep(self.tick_interval)
    
    def tick(self):
        """
        单次认知 tick (v2.0 enhanced)
        
        流程:
        1. 生成 tick_id，记录开始时间
        2. 处理 EventBus pending 事件
        3. 获取当前 Goal
        4. Observe (缓存更新)
        5. Plan (如果需要)
        6. Act (发布规划事件)
        7. Trace 日志
        """
        self.tick_count += 1
        tick_id = generate_tick_id()
        start_time = time.time()
        
        # === 1. 处理 EventBus 事件 (v2 NEW) ===
        try:
            processed_count = self.event_bus.process_pending(max_events=self.max_events_per_tick)
        except Exception as e:
            self.logger.error(f"Event processing error: {e}", component="CognitionLoop")
            processed_count = 0
        
        # === 2. 获取当前 Goal (v2 NEW) ===
        active_goal = self.goal_manager.get_active_goal()
        goal_dict = active_goal.to_dict() if active_goal else None
        
        # === 3. IDLE 检测 ===
        if self._is_idle() and processed_count == 0:
            if self.state != CognitionState.IDLE:
                self.state = CognitionState.IDLE
                self.logger.debug("IDLE state, skipping planning", component="CognitionLoop")
            
            # 即使没有规划，也输出 Trace（显示 idle）
            self._trace_log(tick_id, active_goal, 0, 0, start_time, None)
            return
        
        with self._lock:
            self.state = CognitionState.OBSERVING
        
        # === 4. Observe ===
        observation = self._observe()
        observation.goal = goal_dict  # v2: 绑定当前 goal
        
        # === 5. 判断是否需要规划 ===
        if not self._needs_planning(observation):
            self._trace_log(tick_id, active_goal, processed_count, 0, start_time, observation)
            return
        
        with self._lock:
            self.state = CognitionState.PLANNING
        
        # === 6. Plan ===
        plan = self._plan(observation)
        tasks_created = 0
        
        if plan:
            with self._lock:
                self.state = CognitionState.ACTING
            
            tasks_created = self._act(plan, observation)
            
            # 如果有 active goal，关联任务
            if active_goal and tasks_created > 0:
                # 这里简化处理，实际应该在 Task 创建时关联
                pass
        
        # === 7. Trace 日志 (v2 NEW) ===
        self._trace_log(tick_id, active_goal, processed_count, tasks_created, start_time, observation)
        
        # === 8. Reflect (低频) ===
        if self.tick_count % 10 == 0:
            with self._lock:
                self.state = CognitionState.REFLECTING
            self._reflect(observation, plan)
        
        with self._lock:
            self.state = CognitionState.IDLE
    
    def _trace_log(self, tick_id: str, goal, events: int, tasks: int, start_time: float, observation: Observation = None):
        """
        输出 Trace 日志 (v2.1 enhanced with World Input)
        
        格式: tick goal events tasks queue mem time [world_info]
        """
        elapsed_ms = (time.time() - start_time) * 1000
        
        # 获取队列大小
        queue_size = self.event_bus.get_queue_size()
        
        # 获取内存使用
        try:
            memory_percent = psutil.virtual_memory().percent
        except:
            memory_percent = 0.0
        
        goal_id = goal.goal_id[:8] if goal else 'none'
        
        # v2.1: 添加 World Input 信息到日志
        world_info = ""
        if observation and observation.environment.get("world"):
            world = observation.environment["world"]
            time_ctx = world.get("time", {})
            if time_ctx.get("hour") is not None:
                world_info = f" hour={time_ctx['hour']:02d}:{time_ctx.get('minute', 0):02d}"
            alerts = world.get("alerts", [])
            if alerts:
                world_info += f" alerts={len(alerts)}"
        
        logger.info(
            f"[Trace] tick={tick_id} goal={goal_id} events={events} "
            f"tasks={tasks} queue={queue_size} mem={memory_percent:.0f}% "
            f"time={elapsed_ms:.1f}ms{world_info}",
            component="CognitionLoop",
            context={
                "tick_id": tick_id,
                "goal_id": goal.goal_id if goal else None,
                "events_processed": events,
                "tasks_created": tasks,
                "queue_size": queue_size,
                "memory_percent": memory_percent,
                "elapsed_ms": elapsed_ms,
                "world": observation.environment.get("world") if observation else None,
            }
        )
    
    def _is_idle(self) -> bool:
        """检查是否处于 IDLE 状态"""
        return (
            not self.context_cache.has_new_events(self.last_activity) and
            not self.context_cache.has_active_tasks() and
            not self.goal_manager.get_active_goal() and  # v2: 检查 GoalManager
            time.time() - self.last_activity > self.idle_timeout
        )
    
    def _observe(self) -> Observation:
        """
        观察阶段 (v2.1 enhanced + Attention System + World Input)
        
        1. v2.1: 收集 World Input (环境感知) - 先收集，可能触发新的需求
        2. 从 EventBus 获取待处理事件
        3. 使用 AttentionManager 过滤相关事件
        4. 更新 Task 缓存
        5. 更新 Goal 缓存
        """
        # 1. v2.1: 收集 World Input (环境感知)
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
                
                # 如果有时间相关的警报，记录日志
                time_ctx = world_context.get("time", {})
                if time_ctx.get("special_day"):
                    self.logger.info(
                        f"Special day: {time_ctx['special_day']}",
                        component="CognitionLoop"
                    )
                    
            except Exception as e:
                self.logger.debug(f"World Input collection failed: {e}", component="CognitionLoop")
        
        # 2. 从 EventBus 获取待处理事件 (v2: 使用 process_pending)
        try:
            processed_count = self.event_bus.process_pending(max_events=self.max_events_per_tick)
        except Exception as e:
            self.logger.error(f"Event processing error: {e}", component="CognitionLoop")
            processed_count = 0
        
        # 注意：v2 EventBus 使用 process_pending 直接处理事件，不需要手动获取
        # 这里我们创建一个空列表，因为事件已经被处理了
        pending_events = []
        
        # 3. 使用 AttentionManager 过滤（如果有待处理事件的话）
        attention_result = self.attention.get_relevant_events(pending_events)
        relevant_events = attention_result.events
        
        # 记录 Attention 统计
        if attention_result.total_scanned > 0:
            self.logger.debug(
                f"Attention: {attention_result.total_scanned} scanned, "
                f"{len(relevant_events)} relevant",
                component="CognitionLoop",
                context={"attention": attention_result.to_dict()}
            )
        
        # 4. 刷新 Task 缓存
        try:
            from tasks.task_system import TaskPersistence
            persistence = TaskPersistence()
            pending = persistence.get_pending_tasks()
            running = persistence.get_running_tasks()
            tasks = [t.to_dict() for t in pending + running]
        except Exception as e:
            self.logger.error(f"Failed to get tasks: {e}")
            tasks = []
        
        # 5. 刷新 Goal 缓存
        goal = self.goal_manager.get_active_goal()
        goal_dict = goal.to_dict() if goal else None
        
        # 更新缓存
        self.context_cache.update(events=relevant_events, tasks=tasks, goal=goal_dict)
        
        # v2.1: 增强环境信息
        environment = {
            "tick_count": self.tick_count,
            "last_activity": self.last_activity,
            "state": self.state.value,
            "cache_age": time.time() - self.context_cache.last_updated,
            "goal_id": goal.goal_id[:8] if goal else None,
            "attention": attention_result.to_dict(),
            "world": world_context,  # v2.1: 添加世界输入
            "events_processed": processed_count,  # v2: 添加处理的事件数
        }
        
        return Observation(
            timestamp=time.time(),
            events=relevant_events,
            tasks=tasks,
            goal=goal_dict,
            environment=environment,
            queue_size=self.event_bus.get_queue_size(),
        )
    
    def _needs_planning(self, observation: Observation) -> bool:
        """
        判断是否需要规划 (v2.1 enhanced with World Input)
        """
        # v2.1: 基于时间的触发
        world_data = observation.environment.get("world", {})
        time_ctx = world_data.get("time", {})
        
        # 检查是否是特殊时间点
        if time_ctx.get("special_day"):
            self.logger.info(
                f"Planning triggered by special day: {time_ctx['special_day']}",
                component="CognitionLoop"
            )
            return True
        
        # 检查系统警报
        alerts = world_data.get("alerts", [])
        if alerts:
            self.logger.info(
                f"Planning triggered by alerts: {len(alerts)} alert(s)",
                component="CognitionLoop"
            )
            return True
        
        # 有未处理的用户消息
        for event in observation.events:
            if event.get('type') == 'message.received':
                return True
        
        # 有失败的任务
        for task in observation.tasks:
            if task.get('status') == 'failed':
                return True
        
        # 长时间没有规划
        if time.time() - self.last_plan_time > 600:
            return True
        
        # 有目标但没有活跃任务（可能需要规划新任务）
        if observation.goal and not observation.tasks:
            # v2: 检查 Goal 是否有关联任务
            goal_id = observation.goal.get('goal_id')
            if goal_id:
                goal = self.goal_manager.get_goal(goal_id)
                if goal and not goal.related_task_ids:
                    return True
        
        return False
    
    def _plan(self, observation: Observation) -> Optional[Dict]:
        """规划阶段"""
        goal_desc = observation.goal.get('description') if observation.goal else None
        
        # 1. 规则匹配
        for trigger, handler in self.rule_handlers.items():
            if self._match_trigger(trigger, observation):
                plan = handler(observation)
                if plan:
                    self.logger.info(f"Rule-based plan: {trigger}", component="CognitionLoop")
                    return plan
        
        # 2. LLM 规划 (低频)
        if self.enable_llm and self.llm_planner and self.tick_count >= self.llm_threshold:
            try:
                plan = self.llm_planner(observation.to_dict())
                self.last_plan_time = time.time()
                return plan
            except Exception as e:
                self.logger.error(f"LLM planning failed: {e}", component="CognitionLoop")
        
        return None
    
    def _match_trigger(self, trigger: str, observation: Observation) -> bool:
        """匹配触发条件"""
        for event in observation.events:
            if event.get('type') == trigger:
                return True
        return False
    
    def _act(self, plan: Dict, observation: Observation) -> int:
        """
        执行阶段
        
        Returns:
            创建的任务数
        """
        self.logger.info(
            f"Executing plan: {plan.get('goal', 'unknown')}",
            component="CognitionLoop"
        )
        
        # 发布规划事件
        self.event_bus.publish_simple(
            "cognition.plan",
            {
                "plan_id": plan.get('plan_id'),
                "goal": plan.get('goal'),
                "steps": plan.get('steps'),
            }
        )
        
        self.last_activity = time.time()
        
        # 返回创建的任务数（简化处理）
        return len(plan.get('steps', []))
    
    def _reflect(self, observation: Observation, plan: Optional[Dict]):
        """
        反思阶段 v3.3 — 元认知集成
        
        1. 基础反思：发布事件到EventBus
        2. ReflectionModule深度反思（如果可用）
        3. 自省心跳检查（每50 tick）
        """
        self.logger.debug("Reflecting...", component="CognitionLoop")
        
        # 1. 基础反思：发布事件
        self.event_bus.publish_simple(
            "cognition.reflect",
            {
                "tick_count": self.tick_count,
                "observation": observation.to_dict()
            }
        )
        
        # 2. ReflectionModule 深度反思
        if self.reflection_module:
            try:
                # 构建tick_result对象
                class TickResult:
                    def __init__(self, tick_count, observation, plan, error=None):
                        self.tick_count = tick_count
                        self.observation = observation
                        self.plan = plan
                        self.error = error
                
                tick_result = TickResult(
                    tick_count=self.tick_count,
                    observation=observation,
                    plan=plan,
                )
                
                reflection_result = self.reflection_module.reflect(tick_result)
                
                if reflection_result.get("insights"):
                    insights = reflection_result["insights"]
                    self.logger.info(
                        f"Reflection insights: {len(insights)}",
                        component="CognitionLoop",
                        context={
                            "mood": reflection_result.get("mood"),
                            "insights_count": len(insights),
                        }
                    )
                    
                    # 如果有重要洞察，发布到EventBus
                    if len(insights) > 0:
                        self.event_bus.publish_simple(
                            "cognition.insight",
                            {
                                "tick_count": self.tick_count,
                                "insights": insights,
                                "mood": reflection_result.get("mood"),
                            }
                        )
                        
            except Exception as e:
                self.logger.warning(f"ReflectionModule failed: {e}", component="CognitionLoop")
        
        # 3. 自省心跳（每50 tick深度反思）
        if self.tick_count - self.last_introspection_tick >= self.introspection_interval:
            self._introspection(observation)
            self.last_introspection_tick = self.tick_count
    
    def _introspection(self, observation: Observation):
        """
        自省心跳 — 深度元认知反思
        
        每50 tick运行一次，检查：
        1. 自身状态（健康、目标进展）
        2. 系统性能（tick耗时、内存）
        3. 目标对齐（当前行动是否服务长期目标）
        4. 是否需要调整策略
        """
        self.logger.info(
            "=== 自省心跳 ===",
            component="CognitionLoop",
            context={"tick_count": self.tick_count}
        )
        
        # 1. 检查目标进展
        goal = self.goal_manager.get_active_goal()
        if goal:
            self.logger.info(
                f"目标进展检查: {goal.description[:50] if goal.description else 'none'}",
                component="CognitionLoop",
                context={
                    "goal_id": goal.goal_id,
                    "progress": getattr(goal, 'progress', 'unknown'),
                }
            )
        
        # 2. 系统健康检查
        try:
            import psutil
            memory = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.1)
            
            health_status = "healthy"
            if memory.percent > 90:
                health_status = "critical_memory"
            elif cpu > 80:
                health_status = "high_cpu"
            elif memory.percent > 70:
                health_status = "elevated_memory"
            
            self.logger.info(
                f"系统健康: {health_status}",
                component="CognitionLoop",
                context={
                    "memory_percent": memory.percent,
                    "cpu_percent": cpu,
                    "status": health_status,
                }
            )
            
        except Exception:
            pass
        
        # 3. 元认知日志
        self.logger.info(
            f"元认知状态: tick={self.tick_count}, state={self.state.value}, "
            f"last_activity={int(time.time() - self.last_activity)}s ago",
            component="CognitionLoop",
            context={
                "tick_count": self.tick_count,
                "state": self.state.value,
                "idle_seconds": int(time.time() - self.last_activity),
            }
        )
    
    def register_rule_handler(self, trigger: str, handler: Callable):
        """注册规则处理器"""
        self.rule_handlers[trigger] = handler
    
    def set_llm_planner(self, planner: Callable):
        """设置 LLM 规划器"""
        self.llm_planner = planner
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        active_goal = self.goal_manager.get_active_goal()
        
        return {
            "state": self.state.value,
            "tick_count": self.tick_count,
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
            "is_idle": self._is_idle(),
            "active_goal": active_goal.to_dict() if active_goal else None,
            "queue_size": self.event_bus.get_queue_size(),
            "goal_stats": self.goal_manager.get_statistics(),
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
