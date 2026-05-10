"""
OrchestratorModule - OODA 循环编排器 v2.0 (从 cognition_loop.py 迁移)

职责：
- 协调 Perception/Planning/Execution/Reflection 4个模块
- 管理 tick 生命周期和状态机
- 处理异常和超时
- Trace 日志记录

状态机：
    idle -> perceiving -> planning -> executing -> reflecting -> idle

作者：虾虾
日期：2026-04-30
"""

import time
import threading
import psutil
from enum import Enum, auto
from typing import Dict, Optional, Any
from dataclasses import dataclass, field


class CognitionState(Enum):
    """认知循环状态"""
    IDLE = auto()
    PERCEIVING = auto()
    PLANNING = auto()
    EXECUTING = auto()
    REFLECTING = auto()
    ERROR = auto()


@dataclass
class TickResult:
    """单次 tick 的结果"""
    tick_count: int
    state: CognitionState
    elapsed_ms: float
    observation: Optional[Any] = None
    plan: Optional[Dict] = None
    execution_result: Optional[Dict] = None
    reflection: Optional[Dict] = None
    error: Optional[str] = None


class OrchestratorModule:
    """
    OODA 循环编排器 v2.0
    
    从 cognition_loop.py 的 CognitionLoop.tick() 迁移而来。
    连接 4 个独立模块完成一次完整循环。
    """
    
    def __init__(self,
                 perception_module=None,
                 planning_module=None,
                 execution_module=None,
                 reflection_module=None,
                 event_bus=None,
                 goal_manager=None,
                 performance_monitor=None,
                 logger=None,
                 tick_interval: int = 30,
                 max_events_per_tick: int = 5):
        
        self.perception = perception_module
        self.planning = planning_module
        self.execution = execution_module
        self.reflection = reflection_module
        self.event_bus = event_bus
        self.goal_manager = goal_manager
        self.performance_monitor = performance_monitor
        self.logger = logger
        
        self.tick_interval = tick_interval
        self.max_events_per_tick = max_events_per_tick
        
        self.state = CognitionState.IDLE
        self.tick_count = 0
        self._lock = threading.Lock()
        self._last_tick_time = 0
        self._running = False
        self._thread = None
    
    def tick(self) -> TickResult:
        """
        执行一次完整的 OODA 循环
        
        流程：
        1. PERCEIVING: 感知环境 (PerceptionModule)
        2. PLANNING: 判断是否需要规划，生成计划 (PlanningModule)
        3. EXECUTING: 执行步骤 (ExecutionModule)
        4. REFLECTING: 反思结果 (ReflectionModule)
        5. Trace 日志
        """
        start_time = time.time()
        self.tick_count += 1
        
        with self._lock:
            self.state = CognitionState.PERCEIVING
        
        result = TickResult(
            tick_count=self.tick_count,
            state=self.state,
            elapsed_ms=0
        )
        
        try:
            # === 1. PERCEIVING ===
            observation = self._do_perception()
            result.observation = observation
            
            # IDLE 检测：如果空闲且无事件，跳过规划
            if self._is_idle(observation):
                if self.state != CognitionState.IDLE:
                    with self._lock:
                        self.state = CognitionState.IDLE
                self._trace_log(result, start_time)
                return result
            
            # === 2. PLANNING ===
            with self._lock:
                self.state = CognitionState.PLANNING
            
            needs_plan = self._do_needs_planning(observation)
            if not needs_plan:
                self._trace_log(result, start_time)
                return result
            
            active_goal = None
            if self.goal_manager:
                try:
                    active_goal = self.goal_manager.get_active_goal()
                except:
                    pass
            
            plan = self._do_planning(observation, active_goal)
            result.plan = plan
            
            # === 3. EXECUTING ===
            if plan:
                with self._lock:
                    self.state = CognitionState.EXECUTING
                
                execution_result = self._do_execution(plan)
                result.execution_result = execution_result
            
            # === 4. REFLECTING ===
            if self.tick_count % 10 == 0:
                with self._lock:
                    self.state = CognitionState.REFLECTING
                
                reflection = self._do_reflection(result)
                result.reflection = reflection
            
        except Exception as e:
            result.error = str(e)
            with self._lock:
                self.state = CognitionState.ERROR
        
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            result.elapsed_ms = elapsed_ms
            
            with self._lock:
                if self.state != CognitionState.ERROR:
                    self.state = CognitionState.IDLE
            
            # Trace 日志
            self._trace_log(result, start_time)
            
            # 性能记录
            if self.performance_monitor:
                try:
                    queue_size = 0
                    events_processed = 0
                    if observation and hasattr(observation, 'queue_size'):
                        queue_size = observation.queue_size
                    if observation and hasattr(observation, 'environment'):
                        env = observation.environment
                        events_processed = env.get('events_processed', 0)
                    
                    self.performance_monitor.record(
                        tick_id=f"tick_{self.tick_count}",
                        tick_count=self.tick_count,
                        events_processed=events_processed,
                        queue_size=queue_size,
                        goal_count=1 if active_goal else 0
                    )
                except:
                    pass
        
        return result
    
    def _do_perception(self):
        """执行感知阶段"""
        if not self.perception:
            # 返回空 observation
            return None
        
        return self.perception.observe(self.tick_count)
    
    def _do_needs_planning(self, observation):
        """判断是否需要规划"""
        if not self.planning:
            return False
        
        return self.planning.needs_planning(observation)
    
    def _do_planning(self, observation, active_goal):
        """执行规划阶段"""
        if not self.planning:
            return None
        
        return self.planning.plan(observation, active_goal)
    
    def _do_execution(self, plan):
        """执行执行阶段"""
        if not self.execution:
            return {"error": "ExecutionModule not available"}
        
        return self.execution.execute_plan(plan)
    
    def _do_reflection(self, tick_result):
        """执行反思阶段"""
        if not self.reflection:
            return {"error": "ReflectionModule not available"}
        
        return self.reflection.reflect(tick_result)
    
    def _is_idle(self, observation):
        """检查是否 IDLE"""
        if not observation:
            return True
        
        # 检查是否有用户事件
        env = observation.environment if hasattr(observation, 'environment') else {}
        events_processed = env.get('events_processed', 0)
        
        # 检查是否有活跃目标
        has_goal = observation.goal is not None if hasattr(observation, 'goal') else False
        
        # 检查是否有待处理任务
        has_tasks = False
        if hasattr(observation, 'tasks') and observation.tasks:
            for task in observation.tasks:
                if task.get('status') in ['pending', 'running']:
                    has_tasks = True
                    break
        
        # 空闲条件：无事件、无目标、无任务
        return events_processed == 0 and not has_goal and not has_tasks
    
    def _trace_log(self, tick_result, start_time):
        """Trace 日志 (从 cognition_loop._trace_log 迁移)"""
        elapsed_ms = (time.time() - start_time) * 1000
        
        try:
            memory_percent = psutil.virtual_memory().percent
        except:
            memory_percent = 0.0
        
        queue_size = 0
        if tick_result.observation and hasattr(tick_result.observation, 'queue_size'):
            queue_size = tick_result.observation.queue_size
        
        events_processed = 0
        if tick_result.observation and hasattr(tick_result.observation, 'environment'):
            env = tick_result.observation.environment
            events_processed = env.get('events_processed', 0)
        
        goal_id = 'none'
        if tick_result.observation and hasattr(tick_result.observation, 'goal') and tick_result.observation.goal:
            goal_id = tick_result.observation.goal.get('goal_id', 'none')[:8]
        
        tasks_created = 0
        if tick_result.execution_result:
            tasks_created = tick_result.execution_result.get('executed_steps', 0)
        
        if self.logger:
            self.logger.info(
                f"[Trace] tick={tick_result.tick_count} goal={goal_id} "
                f"events={events_processed} tasks={tasks_created} "
                f"queue={queue_size} mem={memory_percent:.0f}% "
                f"time={elapsed_ms:.1f}ms",
                component="Orchestrator",
            )
    
    def get_status(self) -> Dict:
        """获取编排器状态"""
        return {
            "tick_count": self.tick_count,
            "state": self.state.name,
            "modules": {
                "perception": self.perception is not None,
                "planning": self.planning is not None,
                "execution": self.execution is not None,
                "reflection": self.reflection is not None,
            }
        }
    
    def start(self) -> None:
        """启动编排器（常驻进程模式）"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        if self.logger:
            self.logger.info(
                "OrchestratorModule v2.0 started",
                component="Orchestrator",
                context={
                    "tick_interval": self.tick_interval,
                    "max_events": self.max_events_per_tick,
                }
            )
    
    def stop(self) -> None:
        """停止编排器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _loop(self):
        """主循环"""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Orchestrator tick error: {e}", component="Orchestrator")
            
            time.sleep(self.tick_interval)


# ============== 快速测试 ==============
if __name__ == "__main__":
    orch = OrchestratorModule()
    print("=== OrchestratorModule v2.0 ===")
    print(f"Status: {orch.get_status()}")
    
    # 测试空 tick
    result = orch.tick()
    print(f"Tick result: state={result.state.name}, elapsed={result.elapsed_ms:.1f}ms")
    print("✅ OrchestratorModule skeleton ready")
