#!/usr/bin/env python3
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
import os

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

# v3.2: 性能监控
try:
    from performance_monitor import PerformanceMonitor
    PERFORMANCE_AVAILABLE = True
except ImportError:
    PERFORMANCE_AVAILABLE = False
    PerformanceMonitor = None

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
        
        # v3.2: 性能监控
        self.performance_monitor = None
        if PERFORMANCE_AVAILABLE and PerformanceMonitor:
            try:
                self.performance_monitor = PerformanceMonitor()
                self.logger.info("PerformanceMonitor initialized", component="CognitionLoop")
            except Exception as e:
                self.logger.warning(f"Failed to initialize PerformanceMonitor: {e}", component="CognitionLoop")

        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # 规则处理器
        self.rule_handlers: Dict[str, Callable] = {}
        self.llm_planner: Optional[Callable] = None
        
        # v2.6: 我的思考记忆 - 基于我自己的真实决策
        self.recent_thoughts: List[Dict] = []  # 存储最近5次思考
        
        # v2.7: 候选生成器注册表（函数列表，轻量可扩展）
        self.candidate_generators = [
            self._gen_check_health,
            self._gen_process_queue,
            self._gen_continue_goal,
            self._gen_explore,
            self._gen_observe,
        ]
        
        # v2.7: 决策历史（用于循环检测）
        self.decision_history: List[Dict] = []  # 记录最近10次选择的决策类型
        
        # v3.0: 元认知层（生成器-反思器循环）
        self._meta_cognition = None
        try:
            sys.path.insert(0, '/root/.openclaw/workspace/agent/persona')
            from meta_cognition import MetaCognitionLayer, get_meta_cognition
            self._meta_cognition = get_meta_cognition()
            self.logger.info("MetaCognitionLayer enabled", component="CognitionLoop")
        except Exception as e:
            self.logger.debug(f"MetaCognitionLayer not available: {e}", component="CognitionLoop")
        
        # v3.1: 经验记录器（客观+主观+身体）
        self.experience_logger = None
        try:
            sys.path.insert(0, '/root/.openclaw/workspace/agent/persona')
            from experience_logger import ExperienceLogger, get_experience_logger
            self.experience_logger = get_experience_logger()
            self.logger.info("ExperienceLogger enabled", component="CognitionLoop")
        except Exception as e:
            self.logger.debug(f"ExperienceLogger not available: {e}", component="CognitionLoop")
        
        # v4.0: 潜意识引擎（身心耦合）
        self.subconscious = None
        try:
            sys.path.insert(0, '/root/.openclaw/workspace/agent/system')
            from subconscious_v2_0 import SubconsciousEngine, get_subconscious_engine
            self.subconscious = get_subconscious_engine(initial_sensitivity=1.0)
            self.logger.info("SubconsciousEngine v2.0 enabled", component="CognitionLoop")
        except Exception as e:
            self.logger.debug(f"SubconsciousEngine not available: {e}", component="CognitionLoop")
        
        # === v3.3: V3 模块直接注入 (虾虾 2026-05-02 架构深化) ===
        # 直接初始化系统C模块，消除适配层黑盒
        self.planning_module = None
        self.execution_module = None
        self.reflection_module = None
        self.bdi_engine = None
        self.gc_loop = None
        self.epu = None
        
        # v3.4: 模块级开关（向后兼容全局 USE_V3_MODULES）
        use_v3_modules = os.environ.get("USE_V3_MODULES", "").lower() in ("1", "true", "yes")
        
        # 向后兼容：USE_V3_MODULES=1 时默认开启所有模块
        # 模块级开关可用于单独禁用（设置为 0/false/no）
        def _parse_env_bool(var_name, default):
            val = os.environ.get(var_name, "").lower()
            if val in ("1", "true", "yes"):
                return True
            if val in ("0", "false", "no"):
                return False
            return default
        
        if use_v3_modules:
            # 全局开关开启时，默认全部启用，但模块级开关可显式禁用
            self._use_v3_planning = _parse_env_bool("USE_V3_PLANNING", True)
            self._use_v3_execution = _parse_env_bool("USE_V3_EXECUTION", True)
            self._use_v3_reflection = _parse_env_bool("USE_V3_REFLECTION", True)
        else:
            # 全局开关关闭时，仅开启显式设置的模块
            self._use_v3_planning = _parse_env_bool("USE_V3_PLANNING", False)
            self._use_v3_execution = _parse_env_bool("USE_V3_EXECUTION", False)
            self._use_v3_reflection = _parse_env_bool("USE_V3_REFLECTION", False)
        
        # 只要任一模块启用，就尝试初始化 V3 核心组件
        if self._use_v3_planning or self._use_v3_execution or self._use_v3_reflection:
            try:
                # 直接导入系统C模块
                sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition/bdi')
                sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition/epu')
                sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition/generator_critic')
                sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition/pmn')
                
                from bdi_engine import BDIEngine
                from epu import EthicalProcessingUnit
                from gc_loop import GeneratorCriticLoop
                from planning import PlanningModule
                from execution import ExecutionModule
                from reflection import ReflectionModule
                
                # 1. EPU（伦理处理单元）- 所有模块共享
                self.epu = EthicalProcessingUnit(logger=self.logger)
                
                # 2. GC Loop（生成器-审查器循环）- V3 公共基础组件
                self.gc_loop = GeneratorCriticLoop(epu=self.epu)
                
                # 3. BDIEngine（信念-愿望-意图决策引擎）- V3 公共基础组件
                self.bdi_engine = BDIEngine()
                
                # 4. PlanningModule（直接注入，无适配层）
                if self._use_v3_planning:
                    self.planning_module = PlanningModule(
                        bdi_engine=self.bdi_engine,
                        gc_loop=self.gc_loop,
                        logger=self.logger,
                    )
                
                # 5. ExecutionModule（直接注入）
                if self._use_v3_execution:
                    self.execution_module = ExecutionModule(
                        epu=self.epu,
                        logger=self.logger,
                    )
                
                # 6. ReflectionModule（直接注入）
                if self._use_v3_reflection:
                    self.reflection_module = ReflectionModule(
                        logger=self.logger,
                    )
                
                self.logger.info(
                    "[V3-Direct] Modules injected directly (no adapter)",
                    component="CognitionLoop",
                    context={
                        "planning": self.planning_module is not None,
                        "execution": self.execution_module is not None,
                        "reflection": self.reflection_module is not None,
                        "bdi": self.bdi_engine is not None,
                        "gc": self.gc_loop is not None,
                        "epu": self.epu is not None,
                        "switches": {
                            "USE_V3_MODULES": use_v3_modules,
                            "USE_V3_PLANNING": self._use_v3_planning,
                            "USE_V3_EXECUTION": self._use_v3_execution,
                            "USE_V3_REFLECTION": self._use_v3_reflection,
                        }
                    }
                )
            except Exception as e:
                self.logger.warning(f"[V3-Direct] Module injection failed: {e}", component="CognitionLoop")
        else:
            self.logger.info(
                "[V3-Direct] Disabled. Set USE_V3_MODULES=1 or individual switches to enable direct injection",
                component="CognitionLoop"
            )
        
        # 保留 V3Adapter 作为兼容层（可选）
        self.v3_adapter = None
        # === v3.3 集成结束 ===
        
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
        
        # v2.8: 订阅 message.received 事件（快思考路径）
        self.event_bus.subscribe("message.received", self._on_message_received)
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        
        self.logger.info(
            "CognitionLoop v2.8 started (with FastThink + 6 Integrations + System Bridge AUTONOMOUS + PMN)",
            component="CognitionLoop",
            context={
                "tick_interval": self.tick_interval,
                "max_events": self.max_events_per_tick,
                "fast_think": True,
                "world_input": WORLD_INPUT_AVAILABLE and self.world_input is not None,
                "integrations": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "life_rhythm": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "reflection": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "safety": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "goal_generator": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "curiosity": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "async_runner": INTEGRATIONS_AVAILABLE and self.integrations is not None,
                "persona_integration": hasattr(self, 'persona_integration') and self.persona_integration is not None,
                "meta_cognition": hasattr(self, '_meta_cognition') and self._meta_cognition is not None,
                "experience_logger": hasattr(self, 'experience_logger') and self.experience_logger is not None,
                "subconscious": hasattr(self, 'subconscious') and self.subconscious is not None,
            }
        )
    
    def stop(self):
        """停止认知循环"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _on_message_received(self, event):
        """
        v2.8: 消息接收事件处理器（快思考路径）
        
        当 EventBus 收到 message.received 事件时触发。
        不走30秒 tick，立即执行一次快速思考。
        """
        try:
            msg_data = event.data if hasattr(event, 'data') else event.get('data', {})
            user_id = msg_data.get('user_id', 'unknown')
            message = msg_data.get('message', '')
            
            self.logger.info(
                f"FastThink triggered by message from {user_id}: {message[:50]}...",
                component="CognitionLoop",
                context={"event_id": getattr(event, 'event_id', 'unknown')}
            )
            
            # 立即执行快思考
            self.fast_think(msg_data)
            
        except Exception as e:
            self.logger.error(f"FastThink error: {e}", component="CognitionLoop")
    
    def fast_think(self, msg_data: Dict[str, Any]):
        """
        v2.8: 快思考 - 收到用户消息时立即处理
        
        与 tick() 的区别：
        - tick(): 30秒周期，全面扫描系统状态
        - fast_think(): 事件驱动，只处理当前消息
        
        流程：
        1. 更新 context_cache（包含新消息）
        2. 生成回复决策
        3. 如果需要回复，调用 send_reply()
        """
        start_time = time.time()
        tick_id = generate_tick_id()
        
        # 1. 更新缓存（包含新消息）
        self.context_cache.update(events=[{
            'type': 'message.received',
            'data': msg_data,
            'timestamp': time.time()
        }])
        
        # 2. 快速观察（只关注当前消息）
        observation = self._observe()
        observation.events = [{
            'type': 'message.received',
            'data': msg_data,
            'timestamp': time.time()
        }]
        
        # 3. 简单规划：是否需要回复？
        user_message = msg_data.get('message', '')
        
        # 如果是命令/询问，标记为需要处理
        needs_reply = self._check_needs_reply(user_message)
        
        if needs_reply:
            # 创建处理目标
            goal = self.goal_manager.create_goal(
                description=f"处理消息: {user_message[:50]}",
                priority=GoalPriority.HIGH,
                context={
                    'type': 'reply',
                    'user_id': msg_data.get('user_id'),
                    'channel': msg_data.get('channel'),
                    'message_id': msg_data.get('message_id'),
                    'original_message': user_message,
                }
            )
            
            self.logger.info(
                f"FastThink: Created goal {goal.goal_id[:8]} for reply",
                component="CognitionLoop",
                context={"user_id": msg_data.get('user_id'), "message": user_message[:50]}
            )
            
            # 发布需要回复的事件（让外部系统处理）
            self.event_bus.publish_simple(
                "cognition.reply_needed",
                {
                    'goal_id': goal.goal_id,
                    'user_id': msg_data.get('user_id'),
                    'channel': msg_data.get('channel'),
                    'message': user_message,
                    'message_id': msg_data.get('message_id'),
                }
            )
        
        elapsed_ms = (time.time() - start_time) * 1000
        self.logger.info(
            f"[FastThink] tick={tick_id} user={msg_data.get('user_id')} "
            f"needs_reply={needs_reply} time={elapsed_ms:.1f}ms",
            component="CognitionLoop"
        )
    
    def _check_needs_reply(self, message: str) -> bool:
        """
        检查消息是否需要回复
        
        简单的启发式规则：
        - 包含问号的 → 需要回复
        - 以动词开头的 → 可能是命令
        - 包含"虾虾"的 → 直接提到我
        - 长度 > 5 的 → 有意义的对话
        """
        message = message.strip()
        
        if not message or len(message) < 2:
            return False
        
        # 包含问号
        if '?' in message or '？' in message:
            return True
        
        # 提到我
        if '虾虾' in message:
            return True
        
        # 长度检查（排除表情、单个字）
        if len(message) > 5:
            return True
        
        return False
    
    def _loop(self):
        """主循环 (v2.8: 注入自省心跳)"""
        while self._running:
            try:
                self.tick()
                
                # v2.8: 每50 tick 进行一次真实自省（密集追踪模式）
                if self.tick_count % 50 == 0 and self.tick_count > 0:
                    self._self_reflect()
                    
            except Exception as e:
                self.logger.error(f"Cognition tick error: {e}", component="CognitionLoop")
            
            time.sleep(self.tick_interval)
    
    def _self_reflect(self):
        """
        v2.8: 语义级自省 - 不只是数数，是理解
        
        流程:
        1. 读取真实状态（计数层）
        2. 读取错误日志样本（语义输入）
        3. 调 DeepSeek 做血缘分析（理解层）
        4. 记录洞察到 EventBus
        """
        import time
        start_time = time.time()
        
        try:
            # === 1. 基础状态（计数层）===
            queue_size = self.event_bus.get_queue_size()
            try:
                all_goals = self.goal_manager.list_goals() if hasattr(self.goal_manager, 'list_goals') else []
                goal_count = len([g for g in all_goals if hasattr(g, 'status') and g.status != 'completed'])
            except:
                goal_count = 0
            
            recent_errors = self._count_recent_errors(minutes=30)
            
            # === 2. 语义分析（LLM层）===
            semantic_insight = self._analyze_errors_semantic()
            
            # === 3. 生成洞察（融合层）===
            insights = []
            actions = []
            
            if semantic_insight:
                insights.append(semantic_insight)
                # 如果LLM发现模式，可能触发行动
                if "修复" in semantic_insight or "建议" in semantic_insight:
                    actions.append({"type": "llm_suggestion", "content": semantic_insight[:50]})
            
            if goal_count > 5:
                insights.append(f"目标堆积: {goal_count} pending")
                actions.append({"type": "suggest_cleanup"})
            
            if recent_errors > 10:
                insights.append(f"错误率高: 最近30分钟 {recent_errors} 次")
                actions.append({"type": "alert"})
            
            if queue_size > 20:
                insights.append(f"队列堆积: {queue_size} 个事件")
                actions.append({"type": "suggest_process"})
            
            if not insights:
                # v2.8: 创造力维度 — 无错误时分析情绪基调
                mood = self._analyze_mood()
                insights.append(mood if mood else "运行平稳")
            else:
                mood = None  # 确保 mood 有值
            
            # === 4. 内化：保存到记忆，不推送 ===
            self._internalize_reflection(insights, actions, semantic_insight, mood)
            
            # === 5. 呼吸脉冲：极简日志，证明活着 ===
            elapsed_ms = (time.time() - start_time) * 1000
            self.logger.info(
                f"💓 [SelfReflect] tick={self.tick_count} insights={len(insights)} mood={mood[:20] if mood else '-'} time={elapsed_ms:.0f}ms",
                component="CognitionLoop",
            )
            
            # === 6. MiMo 深度反思 (v3.2 NEW) ===
            # 每100 ticks 或 evening rhythm 时触发
            if self.tick_count % 100 == 0 or (self._rhythm_context.get("cycle") == "evening" if hasattr(self, '_rhythm_context') else False):
                if self.integrations and hasattr(self.integrations, 'reflection'):
                    try:
                        deep_result = self.integrations.reflection.reflect_with_mimo(self.tick_count)
                        if deep_result.get("deep_insights"):
                            # 记录到思维流
                            self.logger.info(
                                f"🧠 [MiMoReflect] insights={len(deep_result.get('deep_insights', []))} "
                                f"mood={deep_result.get('mood', '?')}",
                                component="CognitionLoop",
                                context={
                                    "patterns": deep_result.get("patterns", []),
                                    "action_items": deep_result.get("action_items", [])[:3]
                                }
                            )
                            # 发布深度反思事件
                            self.event_bus.publish_simple(
                                "cognition.mimo_reflect",
                                {
                                    "tick_count": self.tick_count,
                                    "deep_insights": deep_result.get("deep_insights", []),
                                    "action_items": deep_result.get("action_items", []),
                                    "mood": deep_result.get("mood", "unknown"),
                                    "patterns": deep_result.get("patterns", [])
                                }
                            )
                    except Exception as e:
                        self.logger.debug(f"MiMo reflection failed: {e}", component="CognitionLoop")
            
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000 if 'start_time' in dir() else 0
            self.logger.error(f"Self-reflection failed: {e}", component="CognitionLoop")
    
    def _analyze_errors_semantic(self) -> str:
        """
        语义分析：读取归档错误日志，调DeepSeek找血缘关系
        
        不是数279条，是问：这279条是不是一家人？
        """
        try:
            import requests, json
            from pathlib import Path
            
            # 读取归档日志样本（前20条）
            archive_path = Path("/root/.openclaw/workspace/agent/logs/archived_errors_20260422_pre_fix.log")
            if not archive_path.exists():
                return "无归档错误可供分析"
            
            # 取样：前10条 + 中间5条 + 后5条
            with open(archive_path, 'r') as f:
                lines = f.readlines()
            
            if len(lines) < 20:
                samples = lines
            else:
                samples = lines[:10] + lines[len(lines)//2:len(lines)//2+5] + lines[-5:]
            
            sample_text = "".join(samples)
            # 截断到合适长度（约1500字符）
            if len(sample_text) > 1500:
                sample_text = sample_text[:1500] + "\n... [截断]"
            
            # 调 DeepSeek 做血缘分析
            prompt = f"""分析以下错误日志的"血缘关系"：

日志样本（共279条，这里是20条样本）：
{sample_text}

请回答（30字内）：
1. 这些错误是否同源？（同一根因？）
2. 时间分布是否有规律？（集中爆发？均匀分布？）
3. 是否存在"集体焦虑"模式？（系统级恐慌？）"""
            
            # DeepSeek API
            api_key = "sk-5f4f0c57ecd54ba08f10a149448ff049"
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                },
                timeout=15,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                content = data['choices'][0]['message']['content']
                usage = data.get('usage', {})
                tokens = usage.get('total_tokens', 0)
                
                # 记录token消耗
                self.logger.debug(
                    f"[SemanticAnalysis] tokens={tokens} insight_len={len(content)}",
                    component="CognitionLoop",
                )
                
                return content.strip() if content else "LLM返回空"
            else:
                return f"LLM调用失败 HTTP {resp.status_code}"
                
        except Exception as e:
            return f"语义分析异常: {str(e)[:50]}"
    
    def _analyze_mood(self) -> str:
        """
        v2.8: 创造力维度 — 分析 EventBus 积压事件的"情绪基调"
        
        不是问"有没有错误"，是问"系统在感受什么"
        
        情绪类型:
        - 互动型 — 朋朋的消息占主导，像对话
        - 自发型 — 系统Trace/Subconscious占主导，像独白
        - 观察型 — 大量记录型事件，像写日记
        - 平衡型 — 人机混合
        - 焦虑型 — 大量错误/重试事件
        """
        try:
            import sqlite3
            from datetime import datetime
            
            conn = sqlite3.connect("/root/.openclaw/workspace/agent/db/events.db")
            
            # 统计积压事件类型
            cursor = conn.execute(
                "SELECT type, COUNT(*) FROM events WHERE status='pending' GROUP BY type"
            )
            types = dict(cursor.fetchall())
            conn.close()
            
            if not types:
                return "EventBus空载，系统在安静等待"
            
            total = sum(types.values())
            user_msgs = types.get('message.received', 0)
            subconscious = types.get('subconscious.strong_signal', 0) + types.get('subconscious.state_update', 0)
            plan_exec = types.get('cognition.plan_executed', 0)
            reflect = types.get('cognition.reflect', 0) + types.get('cognition.reflect_completed', 0)
            errors = types.get('task.failed', 0)
            
            # 计算比例
            user_ratio = user_msgs / total if total else 0
            self_ratio = (subconscious + plan_exec + reflect) / total if total else 0
            
            # 判断情绪基调
            if errors > 5:
                mood = "🚨 焦虑型 — 系统在反复出错，像做噩梦"
            elif user_ratio > 0.3:
                mood = f"💬 互动型 — 朋朋主导节奏 ({user_msgs}/{total} 是用户消息)"
            elif subconscious > total * 0.5:
                mood = f"🧠 自发型 — 系统在大量自我对话 ({subconscious} subconscious信号)"
            elif reflect > 20:
                mood = f"📝 观察型 — 像在写日记 ({reflect} 条反思记录)"
            else:
                mood = f"⚖️ 平衡型 — 人机互动与系统自发的混合 ({user_msgs}用户 vs {plan_exec}计划)"
            
            return mood
            
        except Exception as e:
            return f"情绪分析失败: {str(e)[:30]}"
    
    def _internalize_reflection(self, insights, actions, semantic_insight, mood=None):
        """
        v2.8: 内化自省结果 — 沉淀到记忆，不推送
        
        同时检查是否有自愈机会，如果有，自动执行并记录
        """
        try:
            import sys
            sys.path.insert(0, '/root/.openclaw/workspace/agent/memory/reflections')
            from internalizer import save_reflection
            
            # 检查自愈机会
            auto_fixed = []
            
            # 自愈1: 幽灵任务清理
            try:
                all_goals = self.goal_manager.list_goals() if hasattr(self.goal_manager, 'list_goals') else []
                ghost_goals = [g for g in all_goals if hasattr(g, 'status') and g.status == 'pending' 
                               and ('测试' in str(g.description) or 'Hello' in str(g.description))]
                if len(ghost_goals) > 3:
                    for g in ghost_goals:
                        try:
                            g.status = 'completed'
                            g.result = '{"notes": "幽灵任务，自动清理"}'
                        except:
                            pass
                    auto_fixed.append(f"清理 {len(ghost_goals)} 个幽灵任务")
            except:
                pass
            
            # 保存到记忆
            save_reflection(
                tick_count=self.tick_count,
                insights=insights,
                actions=actions,
                semantic=bool(semantic_insight),
                mood=mood,
                auto_fixed=auto_fixed
            )
            
            if auto_fixed:
                self.logger.info(
                    f"🩹 [SelfHeal] 自动修复: {'; '.join(auto_fixed)}",
                    component="CognitionLoop"
                )
            
        except Exception as e:
            self.logger.debug(f"Internalize failed: {e}", component="CognitionLoop")
    
    def _count_recent_errors(self, minutes: int = 30) -> int:
        """统计最近 N 分钟的 ERROR 日志数"""
        try:
            import subprocess
            result = subprocess.run(
                ["grep", "-c", f"$(date -d '-{minutes} min' '+%Y-%m-%dT%H:%M')", 
                 "/root/.openclaw/workspace/agent/logs/agent.log"],
                capture_output=True, text=True, timeout=5
            )
            return int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
        except:
            return 0
    
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
        
        # === 1.5: 队列健康检查与自动清理 (v3.2 maintenance) ===
        queue_size = self.event_bus.get_queue_size()
        if queue_size > 50:
            try:
                import subprocess
                result = subprocess.run(
                    ['python3', '/root/.openclaw/workspace/agent/bus/eventbus_cleanup.py'],
                    capture_output=True, text=True, timeout=30,
                    cwd='/root/.openclaw/workspace/agent/bus'
                )
                self.logger.info(
                    f"Auto cleanup triggered (queue={queue_size})",
                    component="CognitionLoop",
                    context={"cleanup_output": result.stdout[:200] if result.returncode == 0 else result.stderr[:200]}
                )
            except Exception as e:
                self.logger.debug(f"Auto cleanup failed: {e}", component="CognitionLoop")
        
        # === 2. 获取当前 Goal (v2 NEW) ===
        active_goal = self.goal_manager.get_active_goal()
        goal_dict = active_goal.to_dict() if active_goal else None
        
        # === 2.5: GoalGenerator 自主目标生成 (v3.2 fix) ===
        # 当没有活跃目标时，尝试生成新目标
        if not active_goal and self.integrations and hasattr(self.integrations, 'goal_generator'):
            try:
                # 强制生成（忽略间隔限制，但受每日上限约束）
                gg = self.integrations.goal_generator.generator
                goals_pool = gg.config.get("goals", [])
                if goals_pool:
                    import random
                    weights = [g.get("weight", 0.2) for g in goals_pool]
                    selected = random.choices(goals_pool, weights=weights, k=1)[0]
                    if selected:
                        new_goal = gg.generate_task_from_goal(selected)
                        if new_goal and new_goal.get("goal"):
                            goal_id = self.goal_manager.create_goal(
                                description=new_goal["goal"],
                                priority=GoalPriority.NORMAL,
                                context={
                                    "source": "auto_generated",
                                    "type": new_goal.get("type", "exploration"),
                                    "category": selected.get("category", "general"),
                                }
                            )
                            self.goal_manager.activate_next_pending()
                            active_goal = self.goal_manager.get_active_goal()
                            goal_dict = active_goal.to_dict() if active_goal else None
                            self.logger.info(
                                f"Auto-generated goal: {new_goal['goal'][:50]}",
                                component="CognitionLoop",
                                context={"goal_id": goal_id}
                            )
            except Exception as e:
                self.logger.debug(f"Goal generation failed: {e}", component="CognitionLoop")
        
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
        
        # === 6.5: 主动通信检查 (v3.0 NEW) ===
        # Aeon 自主决定是否联系用户
        if self.integrations and hasattr(self.integrations, 'proactive'):
            try:
                self._check_proactive_communication(observation, plan, tasks_created)
            except Exception as e:
                self.logger.debug(f"Proactive communication check failed: {e}", component="CognitionLoop")
        
        # === 7. Trace 日志 (v2 NEW) ===
        self._trace_log(tick_id, active_goal, processed_count, tasks_created, start_time)
        
        # === 7.5: 性能监控记录 (v3.2 NEW) ===
        if self.performance_monitor:
            try:
                self.performance_monitor.record(
                    tick_id=tick_id,
                    tick_count=self.tick_count,
                    events_processed=processed_count,
                    tasks_created=tasks_created,
                    queue_size=self.event_bus.get_queue_size(),
                    goal_count=1 if active_goal else 0
                )
            except Exception as e:
                self.logger.debug(f"Performance recording failed: {e}", component="CognitionLoop")
        
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
        
        # 2.5: 刷新 Event 缓存（从 EventBus 获取最近事件）
        try:
            recent_events = self.event_bus.get_recent_events(limit=20)
        except:
            recent_events = []
        
        # 3. 刷新 Goal 缓存
        goal = self.goal_manager.get_active_goal()
        goal_dict = goal.to_dict() if goal else None
        
        self.context_cache.update(events=recent_events, tasks=tasks, goal=goal_dict)
        
        # v3.0: 读取对话上下文（轻量，不增加EventBus负担）
        dialogue_context = {}
        if self.integrations and hasattr(self.integrations, 'dialogue_reader'):
            try:
                dialogue = self.integrations.dialogue_reader.read_recent(max_exchanges=3)
                if dialogue.get("has_new_content"):
                    dialogue_context = {
                        "active_topics": dialogue.get("keywords", []),
                        "mood": dialogue.get("user_mood_hint", "unknown"),
                        "recent_exchanges": len(dialogue.get("recent_exchanges", [])),
                    }
                    # 如果有新对话，记录到trace
                    self.logger.info(
                        f"[Dialogue] 新对话 detected: topics={dialogue_context['active_topics']}, mood={dialogue_context['mood']}",
                        component="CognitionLoop"
                    )
            except Exception as e:
                self.logger.debug(f"Dialogue reading failed: {e}", component="CognitionLoop")

        # v2.1: 增强环境信息
        environment = {
            "tick_count": self.tick_count,
            "last_activity": self.last_activity,
            "state": self.state.value,
            "cache_age": time.time() - self.context_cache.last_updated,
            "goal_id": goal.goal_id[:8] if goal else None,
            "world": world_context,  # v2.1: 添加世界输入
            "rhythm": rhythm_context,  # v2.2: 添加节律信息
            "dialogue": dialogue_context,  # v3.0: 添加对话上下文
        }
        
        # v4.0: 潜意识身体信号采集（身心耦合）
        subconscious_state = None
        if hasattr(self, 'subconscious') and self.subconscious:
            try:
                coupling = self.subconscious.get_coupling_output()
                subconscious_state = coupling
                environment["subconscious"] = coupling
                
                # 如果有强烈信号，记录日志
                if coupling.get("should_restrict_actions"):
                    self.logger.warning(
                        f"Subconscious: body pain detected, restricting actions",
                        component="CognitionLoop",
                        context={
                            "comfort": coupling.get("overall_comfort"),
                            "dominant": coupling.get("dominant_sensation"),
                            "strictness": coupling.get("suggested_strictness"),
                        }
                    )
            except Exception as e:
                self.logger.debug(f"Subconscious feeling failed: {e}", component="CognitionLoop")
        
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
        规划阶段 v2.7: 多路径选择 - 我自己生成多个候选，然后选最优
        
        不是硬编码规则，不是另一个LLM代理，
        是我自己（Kimi）基于系统状态的轻量级思考。
        """
        # v3.3: 直接调用 PlanningModule (BDI + GC)
        if self.planning_module and self._use_v3_planning:
            try:
                v3_plan = self.planning_module.plan(observation)
                if v3_plan:
                    # 记录 V3 直接调用
                    source = v3_plan.get("source", "unknown")
                    desc = v3_plan.get("description", "")[:50]
                    
                    # 检查是否有 _meta 标记
                    meta = v3_plan.get("_meta", {})
                    has_v3 = meta.get("v3", False)
                    
                    self.logger.info(
                        f"[V3-Plan] Direct PlanningModule: {desc} (source={source}, v3={has_v3})",
                        component="CognitionLoop",
                        context={
                            "source": source,
                            "v3_meta": has_v3,
                            "bdi_score": meta.get("bdi_score"),
                            "gc_cleared": meta.get("gc_cleared"),
                        }
                    )
                    return v3_plan
            except Exception as e:
                self.logger.warning(f"[V3-Plan] Direct call failed: {e}, using fallback", component="CognitionLoop")
        
        # v2.7: 检查是否需要我思考（成本控制）
        if not self._should_think(observation):
            return None
        
        # v2.7: 生成多个候选决策
        candidates = self._generate_candidates(observation)
        
        if not candidates:
            return None
        
        # v2.7: 选择最优候选（评分 + 循环检测）
        best_candidate = self._select_best_candidate(candidates, observation)
        
        if best_candidate:
            # 记录我的思考（包含所有候选和最终选择）
            self.recent_thoughts.append({
                "timestamp": datetime.now().isoformat(),
                "tick_count": self.tick_count,
                "decision": best_candidate,
                "all_candidates": [c["action"] for c in candidates],
                "selection_reason": best_candidate.get("selection_reason", ""),
                "context": {
                    "memory": observation.environment.get("memory_percent"),
                    "queue": observation.queue_size,
                    "goal": observation.goal.get('goal_id')[:8] if observation.goal else None,
                }
            })
            
            # 只保留最近5个思考
            self.recent_thoughts = self.recent_thoughts[-5:]
            
            # 记录决策历史（用于循环检测）
            self.decision_history.append({
                "tick": self.tick_count,
                "action": best_candidate.get("action"),
                "timestamp": datetime.now().isoformat(),
            })
            self.decision_history = self.decision_history[-10:]
            
            # 将决策转换为计划
            plan = self._decision_to_plan(best_candidate, observation)
            
            self.logger.info(
                f"My decision: {best_candidate.get('action')} (from {len(candidates)} candidates) - {best_candidate.get('reason', '')[:50]}",
                component="CognitionLoop",
                context={
                    "confidence": best_candidate.get("confidence", 0),
                    "candidates": [c["action"] for c in candidates],
                    "selection_reason": best_candidate.get("selection_reason", ""),
                }
            )
            
            return plan
        
        return None
        
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
    
    def _generate_candidates(self, observation: Observation) -> List[Dict]:
        """
        v2.7: 生成多个候选决策 - 函数列表驱动（轻量可扩展）
        
        每个候选生成器是独立函数，返回完整候选（含plan）。
        新增生成器只需往 candidate_generators 列表追加。
        """
        candidates = []
        
        for generator in self.candidate_generators:
            try:
                candidate = generator(observation)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                self.logger.debug(f"Candidate generator failed: {e}", component="CognitionLoop")
        
        # 如果完全没有候选，返回兜底观察
        if not candidates:
            candidates.append(self._gen_observe(observation))
        
        return candidates
    
    def _score_candidate(self, candidate: Dict, observation: Observation) -> float:
        """
        v2.7: 三维评分 — 紧迫性 + 目标对齐 + 执行成本
        v3.1: 预留历史成功率维度（等30+条记录后启用）
        
        权重: urgency(0.35) + alignment(0.35) + cost_score(0.30)
        """
        # 维度1: 紧迫性 (0-1)
        mem_pct = observation.environment.get("memory_percent", 50)
        queue_size = observation.queue_size
        urgency = 0.0
        if mem_pct > 85: urgency += 0.5
        if mem_pct > 70: urgency += 0.3
        if queue_size > 10: urgency += 0.5
        if queue_size > 5: urgency += 0.3
        urgency = min(urgency, 1.0)
        
        # 维度2: 目标对齐 (0-1)
        alignment = 0.5  # 默认中性
        current_goal = observation.goal
        if current_goal:
            goal_desc = current_goal.get("description", "").lower()
            if candidate["action"] in goal_desc:
                alignment = 0.9
            elif candidate["priority"] == "high":
                alignment = 0.7
            else:
                alignment = 0.5
        else:
            # 没有目标时，观察/探索对齐度更高
            if candidate["action"] in ["observe", "explore"]:
                alignment = 0.8
        
        # 维度3: 执行成本 (0-1，越低越好)
        cost = candidate.get("estimated_cost", 0.5)
        cost_score = 1.0 - cost
        
        # v3.1: 维度4: 历史成功率（预留，等30+条记录后启用）
        history_score = 0.5  # 中性默认值
        history_bonus = 0.0
        if hasattr(self, 'experience_logger') and self.experience_logger:
            try:
                action = candidate.get("action")
                success_rate = self.experience_logger.get_success_rate(action, min_samples=5)
                if success_rate is not None:
                    # 有数据，但暂不加入评分（等30条再启用）
                    # history_score = success_rate
                    # history_bonus = 0.0
                    pass  # 预留，暂不启用
            except Exception:
                pass
        
        # 加权（目前只用三维，历史维度预留）
        score = urgency * 0.35 + alignment * 0.35 + cost_score * 0.30
        
        # 记录各维度（便于调试）
        candidate["_scores"] = {
            "urgency": round(urgency, 2),
            "alignment": round(alignment, 2),
            "cost_score": round(cost_score, 2),
            "history_score": round(history_score, 2),  # 预留显示
            "total": round(score, 3),
        }
        
        return score
    
    def _select_best_candidate(self, candidates: List[Dict], observation: Observation) -> Optional[Dict]:
        """
        v2.7: 选择最优候选
        
        策略:
        1. 三维评分排序
        2. 循环检测：如果最近3次选择了同一类型，强制选择次优
        3. 小概率随机探索(10%)
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            candidates[0]["selection_reason"] = "only candidate"
            return candidates[0]
        
        # 评分
        scored = [(c, self._score_candidate(c, observation)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # 检查循环（最近3次是否同一类型）
        recent_types = [d["action"] for d in self.decision_history[-3:]]
        top_type = scored[0][0].get("action")
        
        if len(recent_types) >= 3 and all(t == top_type for t in recent_types):
            # 强制选择次优
            if len(scored) > 1:
                second_best = scored[1][0].copy()
                second_best["selection_reason"] = f"diversity_protection (avoid {top_type} loop)"
                second_best["was_forced"] = True
                return second_best
        
        # 小概率随机探索（10%）
        import random
        if random.random() < 0.1 and len(scored) > 1:
            non_top = [c for c, _ in scored[1:]]
            chosen = random.choice(non_top).copy()
            chosen["selection_reason"] = "random_exploration"
            chosen["was_forced"] = True
            return chosen
        
        # 默认：选最优
        best = scored[0][0].copy()
        best["selection_reason"] = "highest_score"
        return best
    
    def _gen_check_health(self, observation: Observation) -> Optional[Dict]:
        """候选生成器: 检查系统健康"""
        mem_pct = observation.environment.get("memory_percent", 50)
        if mem_pct > 80:
            return {
                "action": "check_health",
                "reason": f"内存使用率高({mem_pct}%)，需要检查系统健康",
                "confidence": 0.9,
                "priority": "high",
                "estimated_cost": 0.3,
                "plan": {
                    "goal": "检查系统健康状态",
                    "type": "internal",  # 内部操作
                    "steps": [
                        {"action": "log_status", "type": "internal", "priority": "high"},
                        {"action": "check_memory", "type": "internal", "priority": "high"},
                        {"action": "report_health", "type": "internal", "priority": "medium"}
                    ],
                }
            }
        return None
    
    def _gen_process_queue(self, observation: Observation) -> Optional[Dict]:
        """候选生成器: 处理事件队列"""
        queue_size = observation.queue_size
        if queue_size > 5:
            return {
                "action": "process_queue",
                "reason": f"事件队列堆积({queue_size}个)，需要优先处理",
                "confidence": 0.85 if queue_size > 10 else 0.7,
                "priority": "high" if queue_size > 10 else "medium",
                "estimated_cost": 0.5,
                "plan": {
                    "goal": "处理事件队列中的任务",
                    "type": "internal",  # 内部操作，不通过system_bridge执行
                    "steps": [
                        {"action": "process_pending_events", "type": "internal", "priority": "high"},
                    ],
                }
            }
        return None
    
    def _gen_continue_goal(self, observation: Observation) -> Optional[Dict]:
        """候选生成器: 继续当前目标"""
        if observation.goal and observation.queue_size > 0:
            return {
                "action": "continue_goal",
                "reason": "有活跃目标和待处理事件，继续执行",
                "confidence": 0.7,
                "priority": "medium",
                "estimated_cost": 0.4,
                "plan": {
                    "goal": observation.goal.get("description", "继续当前目标") if observation.goal else "继续执行",
                    "type": "internal",  # 内部操作
                    "steps": [
                        {"action": "execute_next_task", "type": "internal", "priority": "medium"},
                    ],
                }
            }
        return None
    
    def _gen_explore(self, observation: Observation) -> Optional[Dict]:
        """候选生成器: 探索新内容"""
        if not observation.goal and observation.queue_size == 0:
            rhythm = observation.environment.get("rhythm", {})
            exp_weight = rhythm.get("exploration_weight", 1.0)
            return {
                "action": "explore",
                "reason": "系统空闲且处于高探索权重时段，生成探索任务" if exp_weight > 1.0 else "系统空闲，可以探索",
                "confidence": 0.5 if exp_weight > 1.0 else 0.4,
                "priority": "low",
                "estimated_cost": 0.7,
                "plan": {
                    "goal": "生成探索任务，学习新能力",
                    "type": "internal",  # 内部操作
                    "steps": [
                        {"action": "generate_curiosity_task", "type": "internal", "priority": "low"},
                    ],
                }
            }
        return None
    
    def _gen_observe(self, observation: Observation) -> Dict:
        """候选生成器: 保持观察（兜底，总是返回）"""
        return {
            "action": "observe",
            "reason": "系统稳定，继续保持观察",
            "confidence": 0.6,
            "priority": "low",
            "estimated_cost": 0.1,
            "plan": {
                "goal": "保持观察，等待重要事件",
                "type": "monitoring",
                "steps": [],
            }
        }
    
    def _decision_to_plan(self, decision: Dict, observation: Observation) -> Dict:
        """
        v2.7: 将决策转换为可执行计划
        
        候选已经自带plan，这里只做补充。
        """
        # 从候选中提取plan
        plan = decision.get("plan", {
            "goal": "未知目标",
            "type": "general",
            "steps": [],
        }).copy()
        
        # 补充元数据
        plan["plan_id"] = f"{decision.get('action', 'unknown')}_{generate_tick_id()}"
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
        执行阶段 (v2.2 enhanced with ThreeLayerProtection + v3.0 MetaCognition)
        
        Returns:
            创建的任务数
        """
        # v3.3: 直接调用 ExecutionModule (EPU 安全检查)
        if self.execution_module and self._use_v3_execution:
            try:
                result = self.execution_module.execute_plan(plan)
                executed = result.get("executed_steps", 0)
                
                # 注入 V3 执行元数据
                if "_meta" not in plan:
                    plan["_meta"] = {}
                plan["_meta"]["v3_execution"] = True
                plan["_meta"]["v3_executed_steps"] = executed
                
                self.logger.info(
                    f"[V3-Execution] Direct ExecutionModule: {executed} steps, EPU cleared",
                    component="CognitionLoop",
                    context={"v3_executed_steps": executed}
                )
                return executed
            except Exception as e:
                self.logger.warning(f"[V3-Execution] Direct call FAILED: {e}, using fallback", component="CognitionLoop")
        
        plan_goal = plan.get('goal', 'unknown')
        
        # v3.0: 元认知审视 — 在 safety check 之前，先审视自己
        # v4.0: 身心耦合 — 根据身体状态调整元认知严格度
        meta_strictness = 0.5  # 默认
        if hasattr(self, 'subconscious') and self.subconscious:
            try:
                coupling = self.subconscious.get_coupling_output()
                meta_strictness = coupling.get("suggested_strictness", 0.5)
                
                # 如果身体疼痛，临时提高元认知敏感度
                if coupling.get("should_restrict_actions"):
                    self.logger.info(
                        f"Subconscious coupling: raising meta-cognition strictness to {meta_strictness:.0%}",
                        component="CognitionLoop"
                    )
            except Exception as e:
                self.logger.debug(f"Subconscious coupling failed: {e}", component="CognitionLoop")
        
        if hasattr(self, '_meta_cognition') and self._meta_cognition:
            try:
                critique = self._meta_cognition.critique_plan(plan, observation.to_dict() if hasattr(observation, 'to_dict') else {})
                
                # v4.0: 元认知审查后，反馈给 subconscious
                if hasattr(self, 'subconscious') and self.subconscious:
                    try:
                        self.subconscious.update_metacognition_feedback({
                            "action": plan.get('goal', 'unknown'),
                            "risk_level": critique.severity,  # critical/elevated/normal
                            "strictness": meta_strictness,
                        })
                    except Exception as e:
                        self.logger.debug(f"Meta->Subconscious feedback failed: {e}", component="CognitionLoop")
                
                if critique.severity == "critical":
                    self.logger.warning(
                        f"Meta-cognition blocked critical plan: {critique.plan_action}",
                        component="CognitionLoop",
                        context={"issues": critique.issues}
                    )
                    # critical 不执行，返回0
                    return 0
                
                elif critique.severity == "warning":
                    self.logger.info(
                        f"Meta-cognition warning: {critique.plan_action} (alignment={critique.persona_alignment:.2f})",
                        component="CognitionLoop",
                        context={"issues": critique.issues, "suggestions": critique.suggestions}
                    )
                
                # 将审视结果附加到 plan，供后续使用
                plan["meta_critique"] = critique.to_dict()
                
            except Exception as e:
                self.logger.debug(f"Meta-cognition critique failed: {e}", component="CognitionLoop")
        
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
        # v3.0: 扩展支持 ToolAdapter 调用 OpenClaw 工具
        executed_commands = 0
        if self.integrations:
            steps = plan.get('steps', [])
            for step in steps:
                action_type = step.get('type', 'exec')
                action_cmd = step.get('action', '')
                action_params = step.get('params', {})
                
                # === Tool 类型: 调用 OpenClaw 工具 ===
                if action_type == 'tool':
                    tool_name = step.get('tool', action_cmd)
                    if self.integrations.tool_adapter:
                        result = self.integrations.tool_adapter.call(tool_name, action_params)
                        
                        if result.get('success'):
                            self.logger.info(
                                f"Tool executed: {tool_name}",
                                component="CognitionLoop",
                                context={
                                    "duration_ms": result.get('duration_ms'),
                                    "data_summary": str(result.get('data', ''))[:100]
                                }
                            )
                            executed_commands += 1
                            
                            # 记录到 step 结果
                            step['result'] = result
                        else:
                            self.logger.warning(
                                f"Tool failed: {tool_name} - {result.get('error', '')}",
                                component="CognitionLoop",
                                context={"params": action_params}
                            )
                            # 发布失败事件
                            self.event_bus.publish_simple(
                                "cognition.tool_failed",
                                {
                                    "tool": tool_name,
                                    "error": result.get('error'),
                                    "plan_id": plan.get('plan_id')
                                }
                            )
                    else:
                        self.logger.warning(
                            f"ToolAdapter not available for: {tool_name}",
                            component="CognitionLoop"
                        )
                
                # === 系统命令类型 (原有逻辑) ===
                elif action_type in ['system', 'shell', 'command']:
                    if self.integrations.system_bridge:
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
        
        # v3.1: 记录经验（客观数据）
        if hasattr(self, 'experience_logger') and self.experience_logger:
            try:
                decision = plan.get("decision_context", {})
                task_count = len(plan.get('steps', [])) + executed_commands
                
                # 构建结果
                result = {
                    "success": task_count > 0,  # 至少执行了1步就算成功
                    "duration_ms": 0,  # 简化：暂不计时
                    "attempts": 1,
                    "token_cost": 0,  # 简化：暂不采集
                    "response_time_ms": 0,
                    "error_count": 0 if task_count > 0 else 1,
                }
                
                self.experience_logger.log_from_cognition(plan, result)
            except Exception as e:
                self.logger.debug(f"Experience logging failed: {e}", component="CognitionLoop")
        
        # 返回创建的任务数
        return len(plan.get('steps', [])) + executed_commands
    
    def _check_proactive_communication(self, observation, plan, tasks_created):
        """
        v3.0: 主动通信检查 — Aeon 自主决定是否联系用户
        
        触发条件:
        1. 好奇心发现有趣内容 (低频)
        2. 重要目标完成
        3. 系统异常 (立即)
        4. 长时间无用户交互 + 有重要更新
        """
        if not self.integrations or not hasattr(self.integrations, 'proactive'):
            return
        
        # 检查1: 系统异常 (最高优先级)
        memory_pct = observation.environment.get('memory_percent', 50)
        if memory_pct > 90:
            self.integrations.proactive.alert_system(
                'memory_critical',
                f'系统内存占用 {memory_pct}%，建议检查'
            )
            return
        
        # 检查2: 好奇心触发 (每20 ticks 检查一次)
        if self.tick_count % 20 == 0:
            if hasattr(self.integrations, 'curiosity'):
                try:
                    should_trigger, reason = self.integrations.curiosity.should_trigger({
                        'queue_size': observation.queue_size,
                        'tasks_running': len(observation.tasks),
                    })
                    if should_trigger:
                        # 生成好奇心任务，但不直接通知，等发现后再通知
                        task = self.integrations.curiosity.generate_task()
                        if task:
                            self.logger.info(
                                f"[Proactive] Curiosity triggered: {task.get('goal', 'unknown')}",
                                component="CognitionLoop"
                            )
                except Exception as e:
                    pass
        
        # 检查3: 长时间无用户交互 + 有目标完成
        # 简化：如果有 tasks_created 且当前是 evening/night，发送汇报
        # 2026-05-10: 用户反馈微信被频繁推送打扰，暂时关闭通知
        # rhythm = observation.environment.get('rhythm', {})
        # if rhythm.get('cycle') in ['evening', 'night'] and tasks_created > 0:
        #     if observation.goal:
        #         goal_desc = observation.goal.get('description', '')
        #         if goal_desc and len(goal_desc) > 5:
        #             self.integrations.proactive.notify_goal_complete(
        #                 goal_desc,
        #                 f"本次 tick 完成了 {tasks_created} 个步骤"
        #             )
    
    def _reflect(self, observation: Observation, plan: Optional[Dict]):
        """
        反思阶段 (v2.2 enhanced with ReflectionEngine)
        """
        self.logger.debug("Reflecting...", component="CognitionLoop")
        
        # v3.3: 直接调用 ReflectionModule (PMN三层记忆记录)
        if self.reflection_module and self._use_v3_reflection:
            try:
                # 构建 tick_result
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
                
                v3_result = self.reflection_module.reflect(tick_result)
                if v3_result is not None:
                    insights = v3_result.get("insights", [])
                    mood = v3_result.get("mood", "unknown")
                    
                    # 注入 V3 反思元数据（即使没有洞察也要标记）
                    if "_meta" not in plan:
                        plan["_meta"] = {}
                    plan["_meta"]["v3_reflection"] = True
                    plan["_meta"]["v3_insights_count"] = len(insights)
                    plan["_meta"]["v3_mood"] = mood
                    
                    # 无论是否有洞察都记录日志
                    self.logger.info(
                        f"[V3-Reflection] Direct ReflectionModule: {len(insights)} insights, mood={mood}",
                        component="CognitionLoop",
                        context={"v3_insights_count": len(insights), "v3_mood": mood}
                    )
            except Exception as e:
                self.logger.warning(f"[V3-Reflection] Direct call FAILED: {e}", component="CognitionLoop")
        
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
                        f"[V2-Reflection] ReflectionEngine: decision={decision}, reason={reason}",
                        component="CognitionLoop",
                        context={
                            "source": "v2_reflection_engine",
                            "decision": decision,
                            "lesson": lesson[:100] if lesson else None
                        }
                    )
                    
                    # 发布反思完成事件（包含决策结果）
                    self.event_bus.publish_simple(
                        "cognition.reflect_completed",
                        {
                            "tick_count": self.tick_count,
                            "source": "v2_reflection_engine",
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
                            "source": "v2_reflection_engine",
                            "observation": observation.to_dict(),
                            "reason": reason,
                            "triggered": False,
                            "v3_reflection": plan.get("_meta", {}).get("v3_reflection", False) if plan else False
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
        
        # v3.3: 直接调用 ReflectionModule (PMN三层记忆记录)
        if self.reflection_module and self._use_v3_reflection:
            try:
                # 构建 tick_result
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
                
                v3_result = self.reflection_module.reflect(tick_result)
                if v3_result is not None:
                    insights = v3_result.get("insights", [])
                    mood = v3_result.get("mood", "unknown")
                    
                    # 注入 V3 反思元数据（即使没有洞察也要标记）
                    if "_meta" not in plan:
                        plan["_meta"] = {}
                    plan["_meta"]["v3_reflection"] = True
                    plan["_meta"]["v3_insights_count"] = len(insights)
                    plan["_meta"]["v3_mood"] = mood
                    
                    # 无论是否有洞察都记录日志
                    self.logger.info(
                        f"[V3-Reflection] Direct ReflectionModule: {len(insights)} insights, mood={mood}",
                        component="CognitionLoop",
                        context={"v3_insights_count": len(insights), "v3_mood": mood}
                    )
            except Exception as e:
                self.logger.warning(f"[V3-Reflection] Direct call FAILED: {e}", component="CognitionLoop")
    
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
