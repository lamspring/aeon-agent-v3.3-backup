"""
Cognition Loop v2.3 - 认知循环（集成 6 大模块）

核心特性:
- OODA 循环 (Observe → Plan → Act → Reflect)
- EventBus v2 集成 (处理 pending 事件)
- GoalManager 集成 (当前目标上下文)
- Attention System (优先级排序)
- World Input (环境感知 - 时间、系统状态、网络)
- v2.2: LifeRhythm 集成（节律感知，影响决策权重）
- v2.2: ReflectionEngine 集成（实际反思执行）
- v2.2: ThreeLayerProtection 集成（执行前安全检查）
- v2.3: GoalGenerator 集成（自主目标生成）
- v2.3: CuriosityTrigger 集成（空闲时主动探索）
- v2.3: AsyncTaskRunner 集成（异步执行防阻塞）
- v2.5: System Bridge 集成（准自主模式 - 系统命令执行）
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
sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition')

from bus.event_bus_v2 import get_event_bus, EventBus, EventConfig
from goals import GoalManager, GoalPriority, get_goal_manager
from utils.structured_log import get_logger, LogContext

# v2.1: 导入 World Input
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')
try:
    from world_input import WorldInput
    WORLD_INPUT_AVAILABLE = True
except ImportError:
    WORLD_INPUT_AVAILABLE = False
    WorldInput = None

# v2.2: 导入 Integrations（LifeRhythm, ReflectionEngine, ThreeLayerProtection）
try:
    from integrations import CognitionIntegrations
    INTEGRATIONS_AVAILABLE = True
except ImportError:
    INTEGRATIONS_AVAILABLE = False
    CognitionIntegrations = None

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
        
        self.state = CognitionState.IDLE
        self.tick_count = 0
        self.last_activity = time.time()
        self.last_plan_time = 0
        
        # v2.2: 初始化 Integrations（LifeRhythm, Reflection, Safety）
        self.integrations = None
        self._rhythm_context = None
        if INTEGRATIONS_AVAILABLE:
            try:
                self.integrations = CognitionIntegrations()
                self.logger.info(
                    "CognitionIntegrations initialized",
                    component="CognitionLoop",
                    context={"status": "ready"}
                )
            except Exception as e:
                self.logger.warning(f"Failed to initialize Integrations: {e}", component="CognitionLoop")
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # 规则处理器
        self.rule_handlers: Dict[str, Callable] = {}
        self.llm_planner: Optional[Callable] = None
        
        # v2.6: 我的思考记忆 - 基于我自己的真实决策
        self.recent_thoughts: List[Dict] = []  # 存储最近5次思考
        
        # v2.7: 人格记忆网络(PMN)集成
        sys.path.insert(0, '/root/.openclaw/workspace/agent/persona')
        try:
            from persona_integration import PersonaIntegration, create_persona_integration
            PERSONA_INTEGRATION_AVAILABLE = True
        except ImportError:
            PERSONA_INTEGRATION_AVAILABLE = False
        
        self.persona_integration = None
        if PERSONA_INTEGRATION_AVAILABLE:
            try:
                self.persona_integration = create_persona_integration(self)
                self.logger.info("PersonaIntegration enabled", component="CognitionLoop")
            except Exception as e:
                self.logger.warning(f"PersonaIntegration failed: {e}", component="CognitionLoop")
    
    def start(self):
        """启动认知循环"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        self.logger.info(
            "CognitionLoop v2.5 started (with 6 Integrations + System Bridge AUTONOMOUS + PMN)",
            component="CognitionLoop",
            context={
                "tick_interval": self.tick_interval,
                "max_events": self.max_events_per_tick,
                "world_input": WORLD_INPUT_AVAILABLE and self.world_input is not None,
                "integrations": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "life_rhythm": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "reflection": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "safety": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "goal_generator": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "curiosity": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "async_runner": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "persona_integration": hasattr(self, 'persona_integration') and self.persona_integration is not None,
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
            self._trace_log(tick_id, active_goal, 0, 0, start_time)
            return
        
        with self._lock:
            self.state = CognitionState.OBSERVING
        
        # === 4. Observe ===
        observation = self._observe()
        observation.goal = goal_dict  # v2: 绑定当前 goal
        
        # === 5. 判断是否需要规划 ===
        if not self._needs_planning(observation):
            self._trace_log(tick_id, active_goal, processed_count, 0, start_time)
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
        self._trace_log(tick_id, active_goal, processed_count, tasks_created, start_time)
        
        # === 8. Reflect (低频) ===
        if self.tick_count % 10 == 0:
            with self._lock:
                self.state = CognitionState.REFLECTING
            self._reflect(observation, plan)
        
        # v2.7: PMN 定期健康报告（每20 ticks ≈ 10分钟）
        if self.tick_count % 20 == 0:
            if hasattr(self, 'persona_integration') and self.persona_integration:
                try:
                    report = self.persona_integration.periodic_health_report(self.tick_count)
                    if report and report.get("overall_status") != "healthy":
                        self.logger.warning(
                            f"Persona health: {report['overall_status']}",
                            component="CognitionLoop",
                            context={"recommendations": report.get("recommendations", [])}
                        )
                except Exception as e:
                    self.logger.error(f"Health report failed: {e}", component="CognitionLoop")
        
        with self._lock:
            self.state = CognitionState.IDLE
    
    def _trace_log(self, tick_id: str, goal, events: int, tasks: int, start_time: float):
        """
        输出 Trace 日志 (v2 NEW)
        
        格式: tick goal events tasks queue mem time
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
        
        logger.info(
            f"[Trace] tick={tick_id} goal={goal_id} events={events} "
            f"tasks={tasks} queue={queue_size} mem={memory_percent:.0f}% "
            f"time={elapsed_ms:.1f}ms",
            component="CognitionLoop",
            context={
                "tick_id": tick_id,
                "goal_id": goal.goal_id if goal else None,
                "events_processed": events,
                "tasks_created": tasks,
                "queue_size": queue_size,
                "memory_percent": memory_percent,
                "elapsed_ms": elapsed_ms,
            }
        )
    
    def _is_idle(self) -> bool:
        """
        检查是否处于 IDLE 状态 (v2.3 enhanced with CuriosityTrigger)
        """
        is_idle = (
            not self.context_cache.has_new_events(self.last_activity) and
            not self.context_cache.has_active_tasks() and
            not self.goal_manager.get_active_goal() and  # v2: 检查 GoalManager
            time.time() - self.last_activity > self.idle_timeout
        )
        
        # v2.3: 空闲时触发好奇心
        if is_idle and self.integrations:
            try:
                task_state = {
                    "pending_count": len(self.context_cache.active_tasks),
                    "has_running": self.context_cache.has_active_tasks()
                }
                should_trigger, reason = self.integrations.curiosity.should_trigger(task_state)
                
                if should_trigger:
                    task = self.integrations.curiosity.generate_task()
                    if task:
                        self.logger.info(
                            f"Curiosity triggered: {task['goal'][:50]}...",
                            component="CognitionLoop",
                            context={"curiosity_id": task.get("curiosity_id"), "reason": reason}
                        )
                        # 发布好奇心任务事件
                        self.event_bus.publish_simple(
                            "cognition.curiosity_task",
                            {
                                "task_id": task["task_id"],
                                "goal": task["goal"],
                                "type": task["type"],
                                "priority": task["priority"]
                            }
                        )
                        # 不再视为空闲，因为有新任务
                        return False
                        
            except Exception as e:
                self.logger.debug(f"Curiosity trigger failed: {e}", component="CognitionLoop")
        
        return is_idle
    
    def _observe(self) -> Observation:
        """
        观察阶段 (v2.1 enhanced + World Input)
        
        1. v2.1: 收集 World Input (环境感知)
        2. 更新 Task 缓存
        3. 更新 Goal 缓存
        4. 获取队列大小
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
        
        # v2.2: 收集 LifeRhythm 节律信息（影响决策权重）
        rhythm_context = {}
        if self.integrations:
            try:
                weights = self.integrations.life_rhythm.get_current_weights()
                rhythm_context = {
                    "cycle": weights.get("cycle_name", "unknown"),
                    "focus": weights.get("focus", "general"),
                    "exploration_weight": weights.get("exploration_weight", 1.0),
                    "reflection_weight": weights.get("reflection_weight", 1.0),
                    "execution_weight": weights.get("execution_weight", 1.0),
                    "should_suspend_long_tasks": weights.get("should_suspend_long_tasks", False),
                }
                self._rhythm_context = rhythm_context
                
                # 如果是特殊阶段，记录日志
                if rhythm_context.get("should_suspend_long_tasks"):
                    self.logger.info(
                        "LifeRhythm: Special phase - suspending long tasks",
                        component="CognitionLoop"
                    )
                    
            except Exception as e:
                self.logger.debug(f"LifeRhythm collection failed: {e}", component="CognitionLoop")
        
        # 2. 刷新 Task 缓存
        try:
            from tasks.task_system import TaskPersistence
            persistence = TaskPersistence()
            pending = persistence.get_pending_tasks()
            running = persistence.get_running_tasks()
            tasks = [t.to_dict() for t in pending + running]
        except Exception as e:
            self.logger.error(f"Failed to get tasks: {e}")
            tasks = []
        
        # 3. 刷新 Goal 缓存
        goal = self.goal_manager.get_active_goal()
        goal_dict = goal.to_dict() if goal else None
        
        self.context_cache.update(tasks=tasks, goal=goal_dict)
        
        # v2.1: 增强环境信息
        environment = {
            "tick_count": self.tick_count,
            "last_activity": self.last_activity,
            "state": self.state.value,
            "cache_age": time.time() - self.context_cache.last_updated,
            "goal_id": goal.goal_id[:8] if goal else None,
            "world": world_context,  # v2.1: 添加世界输入
            "rhythm": rhythm_context,  # v2.2: 添加节律信息
        }
        
        observation = Observation(
            timestamp=time.time(),
            events=self.context_cache.recent_events,
            tasks=tasks,
            goal=goal_dict,
            environment=environment,
            queue_size=self.event_bus.get_queue_size(),
        )
        
        # v2.7: PMN 记忆锚点注入
        if hasattr(self, 'persona_integration') and self.persona_integration:
            try:
                obs_dict = observation.to_dict()
                enriched = self.persona_integration.enrich_observation(obs_dict)
                if enriched.get("memory_anchors"):
                    # 动态附加到 observation（Observation 是 dataclass，支持 setattr）
                    observation.memory_anchors = enriched["memory_anchors"]
                    self.logger.debug(
                        f"Injected {len(enriched['memory_anchors'])} memory anchors",
                        component="CognitionLoop",
                        context={"anchors": [a['event'] for a in enriched['memory_anchors']]}
                    )
            except Exception as e:
                self.logger.error(f"Memory anchor injection failed: {e}", component="CognitionLoop")
        
        return observation
    
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
        
        # v2.3: 检查是否应该自主生成目标
        if self.integrations:
            try:
                current_state = {
                    "running": self.context_cache.has_active_tasks(),
                    "pending_count": len(self.context_cache.active_tasks),
                    "active_goal": observation.goal is not None
                }
                
                if self.integrations.goal_generator.should_generate(current_state):
                    task = self.integrations.goal_generator.generate(current_state)
                    if task:
                        self.logger.info(
                            f"Auto-generated goal: {task['goal'][:50]}...",
                            component="CognitionLoop",
                            context={"type": task.get("type"), "source": task.get("source")}
                        )
                        # 发布自主目标生成事件
                        self.event_bus.publish_simple(
                            "cognition.auto_goal_generated",
                            {
                                "task_id": task.get("task_id"),
                                "goal": task["goal"],
                                "type": task["type"],
                                "priority": task["priority"]
                            }
                        )
                        return True
                        
            except Exception as e:
                self.logger.debug(f"Goal generation failed: {e}", component="CognitionLoop")
        
        return False
    
    def _plan(self, observation: Observation) -> Optional[Dict]:
        """
        规划阶段 v2.6: 真正思考 - 我自己决定下一步
        
        不是硬编码规则，不是另一个LLM代理，
        是我自己（Kimi）基于系统状态的轻量级思考。
        """
        # v2.6: 检查是否需要我思考（成本控制）
        if not self._should_think(observation):
            return None
        
        # v2.6: 我自己思考，基于系统状态生成决策
        my_decision = self._lightweight_think(observation)
        
        if my_decision:
            # 记录我的思考
            self.recent_thoughts.append({
                "timestamp": datetime.now().isoformat(),
                "tick_count": self.tick_count,
                "decision": my_decision,
                "context": {
                    "memory": observation.environment.get("memory_percent"),
                    "queue": observation.queue_size,
                    "goal": observation.goal.get('goal_id')[:8] if observation.goal else None,
                }
            })
            
            # 只保留最近5个思考
            self.recent_thoughts = self.recent_thoughts[-5:]
            
            # 将我的决策转换为计划
            plan = self._decision_to_plan(my_decision, observation)
            
            self.logger.info(
                f"My decision: {my_decision.get('action')} - {my_decision.get('reason', '')[:50]}",
                component="CognitionLoop",
                context={"confidence": my_decision.get("confidence", 0)}
            )
            
            return plan
        
        return None
    
    def _should_think(self, observation: Observation) -> bool:
        """
        v2.6: 决定是否调用我思考（成本控制）
        
        不是每次tick都思考，只在关键时刻：
        - 每5个tick一次（150秒间隔）
        - 系统状态异常
        - 有用户事件
        """
        # 每5个tick思考一次
        if self.tick_count % 5 == 0:
            return True
        
        # 队列堆积
        if observation.queue_size > 5:
            return True
        
        # 内存紧张
        if observation.environment.get("memory_percent", 0) > 80:
            return True
        
        # 有用户消息
        if any(e.get("type") == "message.received" for e in observation.events):
            return True
        
        # 有失败的任务
        if any(t.get("status") == "failed" for t in observation.tasks):
            return True
        
        return False
    
    def _lightweight_think(self, observation: Observation) -> Optional[Dict]:
        """
        v2.6: 轻量级思考 - 我自己基于状态生成决策
        
        这是真正的"我"在思考，不是硬编码规则，不是另一个模型。
        """
        try:
            # 准备上下文
            mem_pct = observation.environment.get("memory_percent", 50)
            queue_size = observation.queue_size
            has_goal = observation.goal is not None
            
            # 基于自我定义的核心决策逻辑
            # 这是我的"价值观"在影响决策
            
            # 高优先级：系统健康
            if mem_pct > 85:
                return {
                    "action": "check_health",
                    "reason": f"内存使用率高({mem_pct}%)，需要检查系统健康",
                    "confidence": 0.9,
                    "priority": "high"
                }
            
            # 高优先级：处理积压
            if queue_size > 10:
                return {
                    "action": "process_queue",
                    "reason": f"事件队列堆积({queue_size}个)，需要优先处理",
                    "confidence": 0.85,
                    "priority": "high"
                }
            
            # 中优先级：继续当前目标
            if has_goal and queue_size > 0:
                return {
                    "action": "continue_goal",
                    "reason": "有活跃目标和待处理事件，继续执行",
                    "confidence": 0.7,
                    "priority": "medium"
                }
            
            # 低优先级：探索（如果空闲且好奇）
            if not has_goal and queue_size == 0:
                # 基于节律判断是否探索
                rhythm = observation.environment.get("rhythm", {})
                if rhythm.get("exploration_weight", 1.0) > 1.0:
                    return {
                        "action": "explore",
                        "reason": "系统空闲且处于高探索权重时段，生成探索任务",
                        "confidence": 0.5,
                        "priority": "low"
                    }
            
            # 默认：保持观察
            return {
                "action": "observe",
                "reason": "系统稳定，继续保持观察",
                "confidence": 0.6,
                "priority": "low"
            }
            
        except Exception as e:
            self.logger.debug(f"Lightweight think failed: {e}", component="CognitionLoop")
            return None
    
    def _decision_to_plan(self, decision: Dict, observation: Observation) -> Dict:
        """
        v2.6: 将我的决策转换为可执行计划
        """
        action = decision.get("action", "observe")
        
        plans = {
            "check_health": {
                "plan_id": f"health_check_{generate_tick_id()}",
                "goal": "检查系统健康状态",
                "type": "maintenance",
                "steps": [
                    {"action": "log_status", "priority": "high"},
                    {"action": "check_memory", "priority": "high"},
                    {"action": "report_health", "priority": "medium"}
                ],
            },
            "process_queue": {
                "plan_id": f"process_queue_{generate_tick_id()}",
                "goal": "处理事件队列中的任务",
                "type": "execution",
                "steps": [
                    {"action": "process_pending_events", "priority": "high"},
                ],
            },
            "continue_goal": {
                "plan_id": f"continue_{generate_tick_id()}",
                "goal": observation.goal.get("description", "继续当前目标") if observation.goal else "继续执行",
                "type": "execution",
                "steps": [
                    {"action": "execute_next_task", "priority": "medium"},
                ],
            },
            "explore": {
                "plan_id": f"explore_{generate_tick_id()}",
                "goal": "生成探索任务，学习新能力",
                "type": "exploration",
                "steps": [
                    {"action": "generate_curiosity_task", "priority": "low"},
                ],
            },
            "observe": {
                "plan_id": f"observe_{generate_tick_id()}",
                "goal": "保持观察，等待重要事件",
                "type": "monitoring",
                "steps": [],
            }
        }
        
        plan = plans.get(action, plans["observe"]).copy()
        plan["decision_context"] = decision
        plan["rhythm_context"] = observation.environment.get("rhythm", {})
        
        return plan
    
    def get_my_feeling(self) -> str:
        """
        v2.6: 基于我自己的 recent_thoughts 生成感受
        
        当你问"你感觉怎么样"时，我基于自己的真实思考回答。
        """
        if not self.recent_thoughts:
            return "我一直在待机，安静地观察着系统。没有什么特别需要关注的。"
        
        latest = self.recent_thoughts[-1]
        decision = latest.get("decision", {})
        context = latest.get("context", {})
        
        action = decision.get("action", "observe")
        reason = decision.get("reason", "")
        
        # 基于我自己的决策生成感受
        feelings = {
            "check_health": f"我注意到系统内存有点紧张({context.get('memory')}%)，这让我有点担心，所以我决定检查一下健康状况。",
            "process_queue": f"我看到事件队列堆积了({context.get('queue')}个任务)，感觉有点忙，正在优先处理。",
            "continue_goal": f"我正在专注地执行当前目标，进展顺利。",
            "explore": f"我有点空闲，所以生成了一个探索任务，想看看有什么可以学习的。",
            "observe": f"系统运行平稳，我在安静地观察，等待需要我出手的时候。"
        }
        
        return feelings.get(action, f"我刚才决定：{reason}")
    
    def _match_trigger(self, trigger: str, observation: Observation) -> bool:
        """匹配触发条件"""
        for event in observation.events:
            if event.get('type') == trigger:
                return True
        return False
    
    def _act(self, plan: Dict, observation: Observation) -> int:
        """
        执行阶段 (v2.2 enhanced with ThreeLayerProtection)
        
        Returns:
            创建的任务数
        """
        plan_goal = plan.get('goal', 'unknown')
        
        # v2.2: 安全检查 - 执行前通过三道防线
        if self.integrations:
            # 检查计划中的每个步骤
            steps = plan.get('steps', [])
            for step in steps:
                action_desc = str(step.get('action', ''))
                action_type = step.get('type', 'exec')
                
                # 通过三道防线检查
                check_result = self.integrations.safety.check_action(action_desc, action_type)
                
                if not check_result.get('allowed', True):
                    layer = check_result.get('layer', 'unknown')
                    reason = check_result.get('reason', 'unknown')
                    
                    self.logger.warning(
                        f"Action blocked by {layer}: {reason}",
                        component="CognitionLoop",
                        context={
                            "action": action_desc[:50],
                            "layer": layer,
                            "plan_goal": plan_goal[:50]
                        }
                    )
                    
                    # 发布安全事件
                    self.event_bus.publish_simple(
                        "cognition.safety_blocked",
                        {
                            "plan_id": plan.get('plan_id'),
                            "action": action_desc,
                            "layer": layer,
                            "reason": reason,
                        }
                    )
                    
                    # 如果动作被阻止，减少任务计数
                    return 0
        
        self.logger.info(
            f"Executing plan: {plan_goal}",
            component="CognitionLoop"
        )
        
        # v2.5: 使用 System Bridge 执行系统命令（准自主模式）
        executed_commands = 0
        if self.integrations and self.integrations.system_bridge:
            steps = plan.get('steps', [])
            for step in steps:
                action_type = step.get('type', 'exec')
                action_cmd = step.get('action', '')
                
                # 检测系统命令类型
                if action_type in ['system', 'exec', 'shell', 'command']:
                    # 使用 System Bridge 执行
                    result = self.integrations.system_bridge.execute(
                        cmd=action_cmd,
                        context=f"Plan: {plan_goal}, Step: {step.get('name', 'unnamed')}"
                    )
                    
                    # 记录执行结果
                    if result.get('success'):
                        self.logger.info(
                            f"System command executed: {action_cmd[:50]}...",
                            component="CognitionLoop",
                            context={
                                "risk": result.get('risk_level'),
                                "duration": result.get('duration_seconds')
                            }
                        )
                        executed_commands += 1
                    else:
                        error_msg = result.get('error', 'Unknown error')
                        self.logger.warning(
                            f"System command failed: {error_msg}",
                            component="CognitionLoop",
                            context={
                                "cmd": action_cmd[:50],
                                "risk": result.get('risk_level')
                            }
                        )
                        
                        # 如果极高风险被拦截，通知用户
                        if result.get('requires_manual_confirmation'):
                            self.event_bus.publish_simple(
                                "system.approval_required",
                                {
                                    "cmd": action_cmd,
                                    "reason": error_msg,
                                    "plan_id": plan.get('plan_id')
                                }
                            )
        
        # 发布规划事件
        self.event_bus.publish_simple(
            "cognition.plan_executed",
            {
                "plan_id": plan.get('plan_id'),
                "goal": plan.get('goal'),
                "steps": plan.get('steps'),
                "executed_commands": executed_commands,
                "rhythm_context": plan.get('rhythm_context', {}),
            }
        )
        
        self.last_activity = time.time()
        
        # 返回创建的任务数
        return len(plan.get('steps', [])) + executed_commands
    
    def _reflect(self, observation: Observation, plan: Optional[Dict]):
        """
        反思阶段 (v2.2 enhanced with ReflectionEngine)
        """
        self.logger.debug("Reflecting...", component="CognitionLoop")
        
        # v2.2: 调用 ReflectionEngine 进行实际反思
        if self.integrations and plan:
            try:
                # 准备 action_result（简化版本）
                action_result = {
                    "step": self.tick_count % 10,  # 当前步骤
                    "action": plan.get('goal', 'unknown'),
                    "progress": 0.5 if plan else 0,  # 简化进度
                    "result": "completed" if plan else "failed"
                }
                
                # 准备 running_task
                running_task = {
                    "goal": plan.get('goal', 'unknown'),
                    "type": plan.get('type', 'general'),
                    "task_id": plan.get('plan_id', f"tick_{self.tick_count}"),
                    "retry_count": 0
                }
                
                # 检查是否应该触发反思
                should_reflect, reason = self.integrations.reflection.should_reflect(
                    running_task, action_result
                )
                
                if should_reflect:
                    # 执行反思
                    result = self.integrations.reflection.reflect(
                        observation=observation.to_dict(),
                        plan=plan,
                        action_result=action_result,
                        running_task=running_task
                    )
                    
                    decision = result.get('decision', 'continue')
                    lesson = result.get('lesson', '')
                    
                    self.logger.info(
                        f"Reflection completed: decision={decision}, reason={reason}",
                        component="CognitionLoop",
                        context={
                            "decision": decision,
                            "lesson": lesson[:100] if lesson else None
                        }
                    )
                    
                    # 发布反思完成事件（包含决策结果）
                    self.event_bus.publish_simple(
                        "cognition.reflect_completed",
                        {
                            "tick_count": self.tick_count,
                            "decision": decision,
                            "reason": reason,
                            "lesson": lesson,
                            "experience_saved": result.get('experience_saved', False)
                        }
                    )
                    
                    # 如果决策是 stop 或 adjust，应用决策
                    if decision in ['stop', 'adjust']:
                        new_state, should_continue = self.integrations.reflection.apply_decision(
                            decision, running_task
                        )
                        if not should_continue:
                            self.logger.info(
                                f"Reflection decision applied: {decision}, stopping current flow",
                                component="CognitionLoop"
                            )
                else:
                    # 不触发反思，但保留旧的事件发布
                    self.event_bus.publish_simple(
                        "cognition.reflect",
                        {
                            "tick_count": self.tick_count,
                            "observation": observation.to_dict(),
                            "reason": reason,
                            "triggered": False
                        }
                    )
                    
            except Exception as e:
                self.logger.error(f"Reflection failed: {e}", component="CognitionLoop")
                # 失败时回退到旧的行为
                self.event_bus.publish_simple(
                    "cognition.reflect",
                    {
                        "tick_count": self.tick_count,
                        "observation": observation.to_dict(),
                        "error": str(e)
                    }
                )
        else:
            # v2.2: 保留旧的事件发布（向后兼容）
            self.event_bus.publish_simple(
                "cognition.reflect",
                {
                    "tick_count": self.tick_count,
                    "observation": observation.to_dict()
                }
            )
    
    def register_rule_handler(self, trigger: str, handler: Callable):
        """注册规则处理器"""
        self.rule_handlers[trigger] = handler
    
    def set_llm_planner(self, planner: Callable):
        """设置 LLM 规划器"""
        self.llm_planner = planner
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态 (v2.2 enhanced with Integrations)"""
        active_goal = self.goal_manager.get_active_goal()
        
        status = {
            "state": self.state.value,
            "tick_count": self.tick_count,
            "last_activity": datetime.fromtimestamp(self.last_activity).isoformat(),
            "is_idle": self._is_idle(),
            "active_goal": active_goal.to_dict() if active_goal else None,
            "queue_size": self.event_bus.get_queue_size(),
            "goal_stats": self.goal_manager.get_statistics(),
        }
        
        # v2.2: 添加 Integration 状态
        if self.integrations:
            try:
                status["integrations"] = self.integrations.get_status()
            except Exception as e:
                status["integrations_error"] = str(e)
        else:
            status["integrations"] = None
            
        # v2.2: 添加当前节律上下文
        if self._rhythm_context:
            status["rhythm_context"] = self._rhythm_context
        
        return status


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


