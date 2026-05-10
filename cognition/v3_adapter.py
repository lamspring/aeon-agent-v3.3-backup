#!/usr/bin/env python3
"""
V3 Adapter Layer - 系统C模块适配器

把系统A（v2.3）的数据结构转换成系统C模块需要的格式。
核心原则：新模块失败 → 静默回退到旧逻辑，不破坏现有系统。

作者：虾虾
日期：2026-05-01
"""

import os
import json
from typing import Dict, Optional, List, Any
from pathlib import Path


class V3Adapter:
    """
    v3 模块适配层
    
    把 CognitionLoop v2.3 的 observation/plan/action 数据结构
    转换成 PlanningModule/ExecutionModule/ReflectionModule 需要的格式。
    
    失败回退：任何模块初始化失败或调用失败 → 返回 None，让调用方使用旧逻辑。
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        self._enabled = os.environ.get("USE_V3_MODULES", "").lower() in ("1", "true", "yes")
        
        # 懒加载：只有 _enabled 时才初始化
        self._planning_module = None
        self._execution_module = None
        self._reflection_module = None
        self._bdi_engine = None
        self._gc_loop = None
        self._epu = None
        
        if self._enabled:
            self._init_modules()
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    def _init_modules(self):
        """懒加载系统C模块"""
        import sys
        # 确保所有路径都在
        paths = [
            '/root/.openclaw/workspace/agent/cognition/bdi',
            '/root/.openclaw/workspace/agent/cognition/epu',
            '/root/.openclaw/workspace/agent/cognition/generator_critic',
            '/root/.openclaw/workspace/agent/cognition/pmn',
            '/root/.openclaw/workspace/agent/cognition',
        ]
        for p in paths:
            if p not in sys.path:
                sys.path.insert(0, p)
        
        # 1. BDIEngine
        try:
            from bdi_engine import BDIEngine
            self._bdi_engine = BDIEngine()
            if self.logger:
                self.logger.info("BDIEngine loaded", component="V3Adapter")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"BDIEngine init failed: {e}", component="V3Adapter")
        
        # 2. EPU
        try:
            from epu import EthicalProcessingUnit
            self._epu = EthicalProcessingUnit(logger=self.logger)
            if self.logger:
                self.logger.info("EPU loaded", component="V3Adapter")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"EPU init failed: {e}", component="V3Adapter")
        
        # 3. GC Loop
        try:
            from gc_loop import GeneratorCriticLoop
            self._gc_loop = GeneratorCriticLoop(epu=self._epu)
            if self.logger:
                self.logger.info("GC Loop loaded", component="V3Adapter")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"GC Loop init failed: {e}", component="V3Adapter")
        
        # 4. PlanningModule
        try:
            from planning import PlanningModule
            self._planning_module = PlanningModule(
                bdi_engine=self._bdi_engine,
                gc_loop=self._gc_loop,
                logger=self.logger,
            )
            if self.logger:
                self.logger.info("PlanningModule v3.3 loaded", component="V3Adapter")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"PlanningModule init failed: {e}", component="V3Adapter")
        
        # 5. ExecutionModule
        try:
            from execution import ExecutionModule
            self._execution_module = ExecutionModule(
                epu=self._epu,
                logger=self.logger,
            )
            if self.logger:
                self.logger.info("ExecutionModule v2.1 loaded", component="V3Adapter")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"ExecutionModule init failed: {e}", component="V3Adapter")
        
        # 6. ReflectionModule
        try:
            from reflection import ReflectionModule
            self._reflection_module = ReflectionModule(
                logger=self.logger,
            )
            if self.logger:
                self.logger.info("ReflectionModule v2.0 loaded", component="V3Adapter")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"ReflectionModule init failed: {e}", component="V3Adapter")
    
    # ========== 适配方法 ==========
    
    def plan(self, observation: Any, old_plan_fn: callable) -> Optional[Dict]:
        """
        适配 _plan()
        
        1. 尝试调用 PlanningModule（BDI + GC Loop）
        2. 失败 → 回退到 old_plan_fn()
        """
        if not self._enabled or not self._planning_module:
            return None  # 让调用方使用旧逻辑
        
        try:
            # 转换 observation 格式
            adapted_obs = self._adapt_observation(observation)
            
            # 调用 PlanningModule
            plan = self._planning_module.plan(adapted_obs)
            
            if plan:
                if self.logger:
                    self.logger.info(
                        "V3 PlanningModule used",
                        component="V3Adapter",
                        context={"plan_source": plan.get("source", "unknown")}
                    )
                return plan
            
        except Exception as e:
            if self.logger:
                self.logger.warning(f"V3 plan failed: {e}, falling back", component="V3Adapter")
        
        return None  # 回退到旧逻辑
    
    def execute(self, plan: Dict, observation: Any, old_execute_fn: callable) -> int:
        """
        适配 _act()
        
        1. 尝试调用 ExecutionModule（带EPU安全检查）
        2. 失败 → 回退到 old_execute_fn()
        """
        if not self._enabled or not self._execution_module:
            return None  # 让调用方使用旧逻辑
        
        try:
            # 调用 ExecutionModule
            result = self._execution_module.execute_plan(plan)
            
            if self.logger:
                self.logger.info(
                    f"V3 ExecutionModule used: {result.get('executed_steps', 0)}/{result.get('total_steps', 0)} steps",
                    component="V3Adapter",
                    context={"success": result.get("success", False)}
                )
            
            return result.get("executed_steps", 0)
            
        except Exception as e:
            if self.logger:
                self.logger.warning(f"V3 execute failed: {e}, falling back", component="V3Adapter")
        
        return None  # 回退到旧逻辑
    
    def reflect(self, observation: Any, plan: Optional[Dict], old_reflect_fn: callable) -> Optional[Dict]:
        """
        适配 _reflect()
        
        1. 尝试调用 ReflectionModule（带PMN记录）
        2. 失败 → 回退到 old_reflect_fn()
        """
        if not self._enabled or not self._reflection_module:
            return None  # 让调用方使用旧逻辑
        
        try:
            # 构建 tick_result
            class TickResult:
                def __init__(self, tick_count, observation, plan, error=None):
                    self.tick_count = tick_count
                    self.observation = observation
                    self.plan = plan
                    self.error = error
            
            tick_result = TickResult(
                tick_count=getattr(getattr(observation, 'environment', None), 'tick_count', 0) if observation else 0,
                observation=observation,
                plan=plan,
            )
            
            # 调用 ReflectionModule
            result = self._reflection_module.reflect(tick_result)
            
            if self.logger:
                self.logger.info(
                    f"V3 ReflectionModule used: {len(result.get('insights', []))} insights",
                    component="V3Adapter",
                    context={"mood": result.get("mood")}
                )
            
            return result
            
        except Exception as e:
            if self.logger:
                self.logger.warning(f"V3 reflect failed: {e}, falling back", component="V3Adapter")
        
        return None  # 回退到旧逻辑
    
    def get_status(self) -> Dict:
        """返回适配层状态"""
        return {
            "enabled": self._enabled,
            "modules_loaded": {
                "planning": self._planning_module is not None,
                "execution": self._execution_module is not None,
                "reflection": self._reflection_module is not None,
                "bdi": self._bdi_engine is not None,
                "gc": self._gc_loop is not None,
                "epu": self._epu is not None,
            }
        }
    
    # ========== 私有工具 ==========
    
    def _adapt_observation(self, observation: Any) -> Any:
        """把系统A的Observation转成系统C需要的格式"""
        # 如果 observation 已经有 to_dict 方法，直接返回
        if hasattr(observation, 'to_dict'):
            # 包装成系统C的Observation格式
            class AdaptedObs:
                def __init__(self, data):
                    self._data = data
                    self.goal = data.get('goal')
                    self.environment = data.get('environment', {})
                    self.events = data.get('events', [])
                    self.tasks = data.get('tasks', [])
                
                def to_dict(self):
                    return self._data
            
            return AdaptedObs(observation.to_dict())
        
        return observation


# ========== 快捷函数 ==========

def create_v3_adapter(logger=None) -> V3Adapter:
    """创建V3适配器"""
    return V3Adapter(logger=logger)


if __name__ == "__main__":
    print("=== V3Adapter Test ===")
    
    # 测试1：未启用
    os.environ.pop("USE_V3_MODULES", None)
    adapter = V3Adapter()
    print(f"Test1: enabled={adapter.enabled} (should be False)")
    assert not adapter.enabled
    
    # 测试2：已启用
    os.environ["USE_V3_MODULES"] = "1"
    adapter2 = V3Adapter()
    print(f"Test2: enabled={adapter2.enabled} (should be True)")
    print(f"  Status: {json.dumps(adapter2.get_status(), indent=2)}")
    
    print("\n✅ V3Adapter ready")
