"""
CognitionLoop Shadow Mode Wrapper - 影子模式包装器

职责：
- 继承 CognitionLoop v2.3
- 添加 shadow_mode 开关
- tick() 时同时运行新模块链（v3.3）
- 记录差异日志

作者：虾虾
日期：2026-04-30
"""

import time
from typing import Dict, Optional, Any

# 导入旧系统
from cognition.cognition_loop_v2 import CognitionLoop, get_cognition, set_cognition

# 导入新模块（使用完整包路径避免冲突）
from cognition.orchestrator import OrchestratorModule
from cognition.perception import PerceptionModule
from cognition.planning import PlanningModule
from cognition.execution import ExecutionModule
from cognition.reflection import ReflectionModule


class CognitionLoopShadow(CognitionLoop):
    """
    CognitionLoop + Shadow Mode
    
    继承 v2.3 的所有功能，增加 shadow_mode 能力。
    默认 shadow_mode=False，完全等同于 v2.3。
    当 shadow_mode=True 时，每次 tick 同时运行新模块链。
    """
    
    def __init__(self, shadow_mode: bool = False, **kwargs):
        # 调用父类初始化
        super().__init__(**kwargs)
        
        self.shadow_mode = shadow_mode
        self._shadow_orchestrator = None
        self._shadow_comparison_log = []
        
        # 如果启用影子模式，初始化新模块链
        if shadow_mode:
            self._init_shadow_modules()
    
    def _init_shadow_modules(self):
        """初始化新模块链（v3.3）"""
        try:
            # 1. PerceptionModule — 复用 v2 的依赖
            perception = PerceptionModule(
                event_bus=self.event_bus,
                goal_manager=self.goal_manager,
                attention_manager=getattr(self, 'attention', None),
                world_input=getattr(self, 'world_input', None),
                logger=self.logger,
                max_events_per_tick=self.max_events_per_tick,
            )
            
            # 2. PlanningModule — 复用 v2 的依赖
            planning = PlanningModule(
                goal_manager=self.goal_manager,
                goal_generator=getattr(self, 'goal_generator', None),
                curiosity_trigger=getattr(self, 'curiosity_trigger', None),
                event_bus=self.event_bus,
                logger=self.logger,
                enable_llm=self.enable_llm,
                llm_threshold=self.llm_threshold,
                idle_timeout=self.idle_timeout,
            )
            
            # 复制规则处理器
            if hasattr(self, 'rule_handlers'):
                for trigger, handler in self.rule_handlers.items():
                    planning.register_rule_handler(trigger, handler)
            
            if hasattr(self, 'llm_planner'):
                planning.set_llm_planner(self.llm_planner)
            
            # 3. ExecutionModule
            execution = ExecutionModule(
                event_bus=self.event_bus,
                logger=self.logger,
            )
            
            # 4. ReflectionModule
            reflection = ReflectionModule(
                event_bus=self.event_bus,
                logger=self.logger,
            )
            
            # 5. OrchestratorModule — 连接所有模块
            self._shadow_orchestrator = OrchestratorModule(
                perception_module=perception,
                planning_module=planning,
                execution_module=execution,
                reflection_module=reflection,
                event_bus=self.event_bus,
                goal_manager=self.goal_manager,
                performance_monitor=getattr(self, 'performance_monitor', None),
                logger=self.logger,
                tick_interval=self.tick_interval,
                max_events_per_tick=self.max_events_per_tick,
            )
            
            self.logger.info(
                "Shadow mode initialized",
                component="CognitionLoopShadow",
                context={"shadow_modules": 5}
            )
            
        except Exception as e:
            self.logger.error(
                f"Shadow mode init failed: {e}",
                component="CognitionLoopShadow"
            )
            self.shadow_mode = False
    
    def tick(self):
        """
        tick() - 同时运行旧系统和新系统（如果 shadow_mode=True）
        """
        # 1. 运行旧的 tick（父类）
        # 注意：父类 tick() 不返回值，是 void
        super().tick()
        
        # 2. 如果启用影子模式，运行新系统
        if self.shadow_mode and self._shadow_orchestrator:
            try:
                start = time.time()
                shadow_result = self._shadow_orchestrator.tick()
                elapsed = (time.time() - start) * 1000
                
                # 记录对比
                comparison = {
                    "tick_count": self.tick_count,
                    "shadow_tick_count": shadow_result.tick_count,
                    "shadow_state": shadow_result.state.name,
                    "shadow_elapsed_ms": shadow_result.elapsed_ms,
                    "has_observation": shadow_result.observation is not None,
                    "has_plan": shadow_result.plan is not None,
                    "has_execution": shadow_result.execution_result is not None,
                    "has_reflection": shadow_result.reflection is not None,
                    "shadow_error": shadow_result.error,
                    "timestamp": time.time(),
                }
                
                self._shadow_comparison_log.append(comparison)
                
                # 只保留最近 500 条
                if len(self._shadow_comparison_log) > 500:
                    self._shadow_comparison_log = self._shadow_comparison_log[-250:]
                
                # 低频率日志（每20 tick）
                if self.tick_count % 20 == 0:
                    self.logger.info(
                        f"Shadow tick: {shadow_result.tick_count}, "
                        f"state={shadow_result.state.name}, "
                        f"elapsed={shadow_result.elapsed_ms:.1f}ms",
                        component="CognitionLoopShadow",
                        context={
                            "shadow_has_plan": comparison["has_plan"],
                            "shadow_has_execution": comparison["has_execution"],
                        }
                    )
                    
            except Exception as e:
                self.logger.error(
                    f"Shadow tick failed: {e}",
                    component="CognitionLoopShadow"
                )
    
    def get_shadow_report(self) -> Dict:
        """获取影子模式运行报告"""
        if not self.shadow_mode:
            return {"status": "shadow_mode_disabled"}
        
        if not self._shadow_comparison_log:
            return {"status": "no_data"}
        
        recent = self._shadow_comparison_log[-50:]
        
        # 统计
        total = len(self._shadow_comparison_log)
        has_plan_count = sum(1 for c in recent if c.get("has_plan"))
        has_execution_count = sum(1 for c in recent if c.get("has_execution"))
        error_count = sum(1 for c in recent if c.get("shadow_error"))
        
        avg_elapsed = sum(c.get("shadow_elapsed_ms", 0) for c in recent) / len(recent)
        
        return {
            "status": "running",
            "total_shadow_ticks": total,
            "recent_ticks": len(recent),
            "plan_rate": round(has_plan_count / len(recent) * 100, 1),
            "execution_rate": round(has_execution_count / len(recent) * 100, 1),
            "error_rate": round(error_count / len(recent) * 100, 1),
            "avg_elapsed_ms": round(avg_elapsed, 2),
            "last_tick": self._shadow_comparison_log[-1] if self._shadow_comparison_log else None,
        }
    
    def get_status(self) -> Dict:
        """扩展状态，包含影子模式信息"""
        status = super().get_status()
        status["shadow_mode"] = self.shadow_mode
        if self.shadow_mode:
            status["shadow_report"] = self.get_shadow_report()
        return status


# ============== 全局实例管理 ==============
# 替换 get_cognition()，让它可以返回 Shadow 版本

def get_cognition_shadow(shadow_mode: bool = False) -> CognitionLoopShadow:
    """
    获取带影子模式的 CognitionLoop 实例
    
    如果全局实例是普通 CognitionLoop，会升级它。
    """
    import cognition.cognition_loop_v2 as v2
    
    if v2._cognition_instance is None:
        instance = CognitionLoopShadow(shadow_mode=shadow_mode)
        v2._cognition_instance = instance
        return instance
    
    # 如果已有实例是普通版本，检查是否需要升级
    if shadow_mode and not isinstance(v2._cognition_instance, CognitionLoopShadow):
        # 创建新的 Shadow 实例，复用配置
        old = v2._cognition_instance
        instance = CognitionLoopShadow(
            shadow_mode=True,
            tick_interval=old.tick_interval,
            idle_timeout=old.idle_timeout,
            enable_llm=old.enable_llm,
            llm_threshold=old.llm_threshold,
            max_events_per_tick=old.max_events_per_tick,
        )
        v2._cognition_instance = instance
        return instance
    
    return v2._cognition_instance


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== CognitionLoopShadow Test ===")
    
    # 测试 1：普通模式（shadow_mode=False）
    loop1 = CognitionLoopShadow(shadow_mode=False)
    print(f"Normal mode: shadow={loop1.shadow_mode}")
    loop1.tick()
    status = loop1.get_status()
    print(f"Status: {status['state']}, ticks={status['tick_count']}")
    
    # 测试 2：影子模式
    loop2 = CognitionLoopShadow(shadow_mode=True)
    print(f"\nShadow mode: shadow={loop2.shadow_mode}")
    
    for i in range(5):
        loop2.tick()
    
    status2 = loop2.get_status()
    print(f"Status: {status2['state']}, ticks={status2['tick_count']}")
    
    report = loop2.get_shadow_report()
    print(f"Shadow report: {report}")
    
    print("\n✅ CognitionLoopShadow ready")
