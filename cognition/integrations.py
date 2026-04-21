#!/usr/bin/env python3
"""
CognitionLoop Integrations - 集成封装模块 v1.2 (完全体)

封装所有模块：
- LifeRhythm, ReflectionEngine, ThreeLayerProtection
- GoalGenerator, CuriosityTrigger, AsyncTaskRunner
- ActionApproval, RateLimiter

为 CognitionLoop 提供统一的调用接口

版本: v1.2
更新: 2026-04-16 - 添加 ActionApproval, RateLimiter，完成完全体
"""

import sys
from pathlib import Path
from typing import Dict, Tuple, Optional, Any
from datetime import datetime

# 添加 agent 目录到路径
AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(AGENT_DIR / "system"))
sys.path.insert(0, str(AGENT_DIR / "cognition"))

# 导入所有核心模块
from life_rhythm import LifeRhythm
from reflection_engine import ReflectionEngine
from three_layer_protection import ThreeLayerProtection
from goal_generator import GoalGenerator
from curiosity_trigger import CuriosityTrigger
from async_task_runner import AsyncTaskRunner
from action_approval import ActionApproval
from rate_limiter import RateLimiter


class LifeRhythmIntegration:
    """LifeRhythm 集成层 - 节律感知影响决策权重"""
    
    def __init__(self):
        self.rhythm = LifeRhythm()
        self._weight_adjustments = {
            "morning": {"exploration_weight": 1.2, "reflection_weight": 0.8, "execution_weight": 1.0},
            "afternoon": {"exploration_weight": 1.0, "reflection_weight": 0.9, "execution_weight": 1.1},
            "night": {"exploration_weight": 0.8, "reflection_weight": 1.3, "execution_weight": 0.9},
            "late_night": {"exploration_weight": 0.6, "reflection_weight": 1.0, "execution_weight": 0.7}
        }
    
    def get_current_weights(self) -> Dict[str, float]:
        """获取当前时间段的权重调整"""
        cycle = self.rhythm.get_current_cycle()
        if not cycle:
            return {"exploration_weight": 1.0, "reflection_weight": 1.0, "execution_weight": 1.0, 
                    "cycle_name": "unknown", "focus": "general", "should_suspend_long_tasks": False}
        
        cycle_name = cycle.get("name", "unknown")
        focus = cycle.get("focus", "general")
        weights = self._weight_adjustments.get(cycle_name, 
                {"exploration_weight": 1.0, "reflection_weight": 1.0, "execution_weight": 1.0})
        
        special = self.rhythm.is_special_phase()
        should_suspend = bool(special and special.get("is_preparation_phase"))
        
        return {**weights, "cycle_name": cycle_name, "focus": focus, 
                "should_suspend_long_tasks": should_suspend}
    
    def should_execute_task(self, task_type: str) -> str:
        return self.rhythm.should_do_task(task_type)
    
    def get_rhythm_summary(self) -> Dict[str, Any]:
        return self.rhythm.get_rhythm_summary()


class ReflectionIntegration:
    """ReflectionEngine 集成层 - 实际反思执行"""
    
    def __init__(self, queue_manager=None):
        self.engine = ReflectionEngine()
        self.queue_manager = queue_manager
    
    def should_reflect(self, running_task: Dict, action_result: Dict) -> Tuple[bool, str]:
        return self.engine.should_reflect(running_task, action_result)
    
    def reflect(self, observation: Dict, plan: Dict, action_result: Dict, running_task: Dict = None) -> Dict:
        task = running_task or {
            "goal": plan.get("goal", "unknown"),
            "type": plan.get("type", "general"),
            "task_id": plan.get("task_id", "unknown")
        }
        running_state = {
            "progress": action_result.get("progress", 0),
            "retry_count": running_task.get("retry_count", 0) if running_task else 0,
            "total_steps": plan.get("total_steps", 4)
        }
        current_step = action_result.get("step", 0)
        
        result = self.engine.reflect_and_spawn(
            task=task, current_step=current_step, step_result=action_result,
            running_state=running_state, queue_manager=self.queue_manager
        )
        
        if running_task:
            self.engine.log_reflection(task.get("task_id", "unknown"), current_step,
                                     action_result.get("action", "unknown"),
                                     f"{running_state['progress']*100:.0f}%", result)
        return result
    
    def apply_decision(self, decision: str, running_task: Dict) -> Tuple[Optional[Dict], bool]:
        if not self.queue_manager:
            if decision == "stop":
                return None, False
            elif decision == "adjust":
                running_task["retry_count"] = running_task.get("retry_count", 0) + 1
                return running_task, True
            return running_task, True
        return self.engine.apply_decision(decision, running_task, self.queue_manager)


class SafetyIntegration:
    """ThreeLayerProtection 集成层 - 执行前安全检查"""
    
    def __init__(self):
        self.protection = ThreeLayerProtection()
    
    def check_action(self, action: str, action_type: str = "exec") -> Dict:
        return self.protection.check_action(action, action_type)
    
    def confirm_action(self, confirmation_id: str, approved: bool) -> bool:
        return self.protection.confirm_action(confirmation_id, approved)
    
    def get_stats(self) -> Dict:
        return self.protection.get_stats()


class GoalGeneratorIntegration:
    """GoalGenerator 集成层 - 自主目标生成"""
    
    def __init__(self):
        self.generator = GoalGenerator()
    
    def should_generate(self, current_state: Dict) -> bool:
        return self.generator.should_generate_goal(current_state)
    
    def generate(self, current_state: Dict = None) -> Optional[Dict]:
        if current_state is None:
            current_state = {}
        return self.generator.generate(current_state)
    
    def get_stats(self) -> Dict:
        return self.generator.get_stats()


class CuriosityTriggerIntegration:
    """CuriosityTrigger 集成层 - 空闲时主动探索"""
    
    def __init__(self):
        self.curiosity = CuriosityTrigger()
    
    def should_trigger(self, task_state: Dict) -> Tuple[bool, str]:
        return self.curiosity.should_trigger(task_state)
    
    def generate_task(self) -> Optional[Dict]:
        return self.curiosity.generate_curiosity_task()
    
    def get_stats(self) -> Dict:
        return self.curiosity.get_stats()


class AsyncTaskRunnerIntegration:
    """AsyncTaskRunner 集成层 - 异步任务执行防阻塞"""
    
    def __init__(self, timeout: int = 60, max_concurrent: int = 3):
        self.runner = AsyncTaskRunner(timeout=timeout, max_concurrent=max_concurrent)
    
    async def run_task(self, task_func, *args, task_id: str = "", **kwargs) -> Dict:
        return await self.runner.run_task(task_func, *args, task_id=task_id, **kwargs)
    
    async def run_tasks_concurrent(self, tasks: list, task_id_prefix: str = "batch") -> list:
        return await self.runner.run_tasks_concurrent(tasks, task_id_prefix)
    
    def shutdown(self):
        self.runner.shutdown()


class ActionApprovalIntegration:
    """ActionApproval 集成层 - 操作审批系统"""
    
    def __init__(self):
        self.approval = ActionApproval()
    
    def check_action(self, tool_name: str, params: Dict = None) -> Dict:
        """
        检查操作是否需要审批
        
        Returns:
            {
                "allowed": bool,
                "requires_approval": bool,
                "risk_level": str,
                "reason": str,
                "approval_id": str | None
            }
        """
        return self.approval.check_action(tool_name, params)
    
    def approve_action(self, approval_id: str, approved: bool = True) -> bool:
        """手动批准/拒绝操作"""
        return self.approval.approve_action(approval_id, approved)
    
    def get_stats(self) -> Dict:
        return self.approval.get_stats()


class RateLimiterIntegration:
    """RateLimiter 集成层 - API和任务限流"""
    
    def __init__(self):
        self.limiter = RateLimiter()
    
    def check_api_call(self, action: str = "generic") -> Tuple[bool, str, int]:
        """
        检查是否可以进行API调用
        
        Returns:
            (allowed, reason, remaining)
        """
        return self.limiter.check_api_call(action)
    
    def check_task_creation(self, task_type: str = "generic", parent_depth: int = 0) -> Tuple[bool, str]:
        """检查是否可以创建任务"""
        return self.limiter.check_task_creation(task_type, parent_depth)
    
    def check_subtask_spawn(self, parent_task: Dict) -> Tuple[bool, str]:
        """检查是否可以产生子任务"""
        return self.limiter.check_subtask_spawn(parent_task)
    
    def get_stats(self) -> Dict:
        return self.limiter.get_stats()


class CognitionIntegrations:
    """统一的 CognitionLoop 集成管理器 - 完全体 v1.2"""
    
    def __init__(self, queue_manager=None, async_timeout: int = 60):
        # --- [Aeon Bridge Injection v1.0] ---
        self.aeon_bridge = None
        self.aeon_bridge_loaded = False
        try:
            import sys
            bridge_path = "/root/.openclaw/workspace/shrimp_wisdom"
            if bridge_path not in sys.path:
                sys.path.insert(0, bridge_path)
            
            from metabridge_v1 import MetaBridgeV1
            self.aeon_bridge = MetaBridgeV1()
            self.aeon_bridge_loaded = True
            print("[Aeon Bridge] 元认知层已激活")
        except Exception as e:
            # 失败静默
            print(f"[Aeon Bridge] 加载失败（静默）: {e}")
            pass
        # --- [End of Injection] ---
        
        # v2.2 核心模块
        self.life_rhythm = LifeRhythmIntegration()
        self.reflection = ReflectionIntegration(queue_manager=queue_manager)
        self.safety = SafetyIntegration()
        
        # v2.3 自主模块
        self.goal_generator = GoalGeneratorIntegration()
        self.curiosity = CuriosityTriggerIntegration()
        self.async_runner = AsyncTaskRunnerIntegration(timeout=async_timeout)
        
        # v2.4 完全体新增
        self.action_approval = ActionApprovalIntegration()
        self.rate_limiter = RateLimiterIntegration()
        
        # v2.5 准自主模式 - System Bridge
        self.system_bridge = SystemBridgeIntegration(mode="AUTONOMOUS_PLUS_NOTIFY")
        
        self._initialized_at = datetime.now().isoformat()
    
    
    # --- [HOTLOAD: FuzzinessDetector v1.0 - Injected 2026-04-17] ---
    def intercept_goal_activation(self, goal_id: str) -> dict:
        """
        热加载：拦截目标激活，检测 is_vague
        在 CognitionLoop._plan() 阶段调用
        """
        result = {
            "should_activate": True,
            "is_vague": False,
            "decomposed_tasks": [],
            "action": "activate",
            "message": ""
        }
        
        try:
            from goals import get_goal_manager
            from metabridge_v1 import MetaBridgeV1
            import sqlite3
            
            gm = get_goal_manager()
            bridge = MetaBridgeV1()
            
            # 获取目标信息
            goal = gm.get_goal(goal_id)
            if not goal:
                return result
            
            description = goal.description if hasattr(goal, 'description') else str(goal)
            
            # Bridge 分析
            thought = bridge.think_before_act(description, {
                "context": "goal_activation_intercept",
                "goal_id": goal_id
            })
            
            analysis = thought.get("analysis", {})
            is_vague = analysis.get("is_vague", False)
            
            # 更新数据库标记
            try:
                db_path = gm.store.db_path if hasattr(gm, 'store') and hasattr(gm.store, 'db_path') else '/root/.openclaw/workspace/agent/db/goals.db'
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE goals SET is_vague = ? WHERE goal_id = ?",
                    (1 if is_vague else 0, goal_id)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[FuzzinessDetector] 数据库更新失败: {e}")
            
            if is_vague:
                result["is_vague"] = True
                result["action"] = "decompose"
                result["message"] = f"检测到模糊目标: {description[:40]}..."
                
                print(f"[Bridge] ⚠️  {result['message']}")
                
                # 尝试自动拆解
                try:
                    from auto_decomposer import GoalDecomposer
                    decomposer = GoalDecomposer()
                    tasks = decomposer.decompose(description, goal_id)
                    
                    if tasks:
                        result["decomposed_tasks"] = tasks
                        result["should_activate"] = True
                        
                        print(f"[Bridge] ✅ 已拆解为 {len(tasks)} 个子任务:")
                        for i, task in enumerate(tasks, 1):
                            print(f"    {i}. {task['name']}")
                    else:
                        result["should_activate"] = True
                        result["message"] += " (拆解为空，原样激活)"
                        
                except Exception as e:
                    print(f"[Bridge] ⚠️  拆解失败: {e}")
                    result["should_activate"] = True
                    result["message"] += f" (拆解异常)"
            else:
                result["message"] = "目标清晰，直接激活"
            
            # 记录到日志
            import json
            from datetime import datetime
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "goal_id": goal_id,
                "description": description[:50],
                "is_vague": is_vague,
                "action": result["action"],
                "decomposed_count": len(result["decomposed_tasks"])
            }
            
            log_path = "/root/.openclaw/workspace/shrimp_wisdom/fuzziness_intercept_log.jsonl"
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
        except Exception as e:
            print(f"[Bridge] 拦截失败 (静默): {e}")
            result["message"] = f"拦截失败: {str(e)[:30]}"
        
        return result
    
    # --- [HOTLOAD: DynamicPlanner v0.2 - Merged 2026-04-17] ---
    def dynamic_plan_next_step(self, goal_description: str, current_state: dict) -> dict:
        """
        DynamicPlanner 运行时动态规划
        根据当前状态动态生成下一步任务
        
        与 auto_decomposer 区别:
        - auto_decomposer: 预生成所有任务
        - DynamicPlanner: 每次 tick 只生成下一步
        """
        try:
            # 导入实验模块
            sys.path.insert(0, '/root/.openclaw/workspace/experiments')
            
            # 简化版动态规划逻辑 (内嵌，避免外部依赖失败)
            phase = current_state.get("phase", "init")
            progress = current_state.get("progress", 0.0)
            
            # 状态机驱动的动态规划
            phases = [
                ("analyze", "[分析] 解析需求，识别关键约束"),
                ("design", "[设计] 绘制架构蓝图，定义模块边界"),
                ("implement", "[实现] 开发核心逻辑，保留扩展点"),
                ("verify", "[验证] 测试核心功能，收集反馈"),
                ("deliver", "[交付] 整理文档，准备部署"),
                ("complete", "[完成] 目标达成，归档经验")
            ]
            
            # 找到当前阶段索引
            current_idx = -1
            for i, (p, _) in enumerate(phases):
                if p == phase:
                    current_idx = i
                    break
            
            # 生成下一步
            next_idx = current_idx + 1 if current_idx >= 0 else 0
            
            if next_idx >= len(phases):
                return {
                    "has_next": False,
                    "message": "目标已完成",
                    "phase": "complete",
                    "progress": 1.0
                }
            
            next_phase, next_name = phases[next_idx]
            
            # 根据目标类型调整
            if "优化" in goal_description and next_phase == "design":
                next_name = "[诊断] 定位性能瓶颈，收集基准数据"
            elif "修复" in goal_description and next_phase == "implement":
                next_name = "[修复] 定位故障点，实施修复方案"
            
            new_progress = min((next_idx + 1) / len(phases), 0.95)
            
            result = {
                "has_next": True,
                "task": {
                    "phase": next_phase,
                    "name": next_name,
                    "id": f"{next_phase}_dynamic"
                },
                "new_state": {
                    "phase": next_phase,
                    "progress": new_progress
                },
                "message": f"DynamicPlanner 生成: {next_name}",
                "planner_type": "dynamic"
            }
            
            # 记录规划决策
            import json
            from datetime import datetime
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "planner": "DynamicPlanner",
                "goal": goal_description[:50],
                "phase": next_phase,
                "progress": new_progress
            }
            
            log_path = "/root/.openclaw/workspace/shrimp_wisdom/dynamic_planner_log.jsonl"
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
            print(f"[DynamicPlanner] {result['message']}")
            return result
            
        except Exception as e:
            # 失败静默，返回安全默认值
            print(f"[DynamicPlanner] 规划失败 (静默): {e}")
            return {
                "has_next": True,
                "task": {"phase": "unknown", "name": "[默认] 继续执行", "id": "default"},
                "new_state": current_state,
                "message": "DynamicPlanner 失败，使用默认",
                "planner_type": "fallback"
            }
    
    def should_use_dynamic_planner(self, goal_description: str) -> bool:
        """
        判断是否应该使用 DynamicPlanner
        模糊目标 + 高不确定性 → 使用 DynamicPlanner
        """
        # 简单启发式
        vague_indicators = ["架构", "设计", "优化", "重构", "升级", "v3.1", "v3.2"]
        has_vague = any(v in goal_description for v in vague_indicators)
        is_long = len(goal_description) > 15
        
        return has_vague and is_long
    # --- [END DynamicPlanner HOTLOAD] ---

# --- [END HOTLOAD] ---

    def get_status(self) -> Dict:
        """获取集成模块状态"""
        return {
            "initialized_at": self._initialized_at,
            "version": "v1.2_complete_with_bridge",
            "aeon_bridge_loaded": self.aeon_bridge_loaded,
            "modules": {
                "life_rhythm": {
                    "current_cycle": self.life_rhythm.rhythm.get_cycle_name(),
                    "current_focus": self.life_rhythm.rhythm.get_focus()
                },
                "reflection": {
                    "enabled": self.reflection.engine.config.get("enabled", True)
                },
                "safety": self.safety.get_stats(),
                "goal_generator": self.goal_generator.get_stats(),
                "curiosity": self.curiosity.get_stats(),
                "async_runner": {
                    "timeout": self.async_runner.runner.timeout,
                    "max_concurrent": self.async_runner.runner.max_concurrent
                },
                "action_approval": self.action_approval.get_stats(),
                "rate_limiter": self.rate_limiter.get_stats(),
                "system_bridge": self.system_bridge.get_stats() if self.system_bridge else None
            }
        }
    
    def optimize_intent(self, intent: str, context: Dict = None) -> Dict:
        """
        使用 Aeon Bridge 优化意图
        
        Args:
            intent: 原始意图描述
            context: 上下文信息
            
        Returns:
            {
                "original_intent": str,
                "optimized_intent": str,
                "bridge_active": bool,
                "execution_plan": Dict | None,
                "matched_tools": list
            }
        """
        result = {
            "original_intent": intent,
            "optimized_intent": intent,
            "bridge_active": False,
            "execution_plan": None,
            "matched_tools": []
        }
        
        if not self.aeon_bridge or not self.aeon_bridge_loaded:
            return result
        
        try:
            # 调用 Bridge 进行元认知处理
            thought = self.aeon_bridge.think_before_act(intent, context or {})
            
            result["bridge_active"] = True
            result["optimized_intent"] = thought.get("refined_intent", intent)
            result["execution_plan"] = thought.get("execution_plan")
            result["matched_tools"] = thought.get("matched_tools", [])
            
            if thought.get("analysis"):
                result["complexity"] = thought["analysis"].get("complexity")
                result["domain"] = thought["analysis"].get("domain")
                result["is_vague"] = thought["analysis"].get("is_vague", False)
            
            print(f"[Aeon Bridge] Intent optimized: {intent[:50]}... -> {result['optimized_intent'][:50]}...")
            
        except Exception as e:
            # 失败静默，返回原始意图
            print(f"[Aeon Bridge] Optimization failed (silent): {e}")
            pass
        
        return result


class SystemBridgeIntegration:
    """
    System Bridge 集成层 - 准自主模式系统执行
    
    让 Aeon 能真正操作系统，同时保持审计和安全
    
    模式: AUTONOMOUS_PLUS_NOTIFY
    - 大部分操作自主执行
    - 极高风险操作(删系统/改核心)需要确认
    - 执行后立即通知用户
    - 完整审计日志
    """
    
    def __init__(self, mode: str = "AUTONOMOUS_PLUS_NOTIFY"):
        self.bridge_script = "/root/aeon_system_bridge.sh"

    def command_exists(self, cmd: str) -> bool:
        """检查命令是否存在于 PATH 中"""
        import shutil
        return shutil.which(cmd) is not None

        self.log_file = "/var/log/aeon_bridge.log"
        self.mode = mode
        self.approval = ActionApprovalIntegration()
        self._execution_history = []
        self._max_history = 100
    
    def execute(self, cmd: str, context: str = "") -> Dict:
        """
        执行系统命令（准自主模式）
        
        Args:
            cmd: 要执行的命令
            context: 执行上下文/原因
        
        Returns:
            {
                "success": bool,
                "exit_code": int,
                "risk_level": str,
                "cmd": str,
                "stdout": str,
                "duration_seconds": float,
                "mode": str
            }
        """
        import subprocess
        import json
        from datetime import datetime
        
        # 1. 前置安全检查
        if self._is_ultra_high_risk(cmd):
            result = {
                "success": False,
                "error": "极高风险操作被拦截，需要手动确认",
                "risk_level": "ULTRA_HIGH",
                "cmd": cmd,
                "requires_manual_confirmation": True,
                "mode": self.mode
            }
            self._log_execution(result, context)
            return result
        
        # 检查桥接脚本是否存在
        if not os.path.exists(self.bridge_script):
            result = {
                "success": False,
                "error": f"桥接脚本不存在: {self.bridge_script}",
                "risk_level": "MISSING_DEPENDENCY",
                "cmd": cmd,
                "requires_manual_confirmation": False,
                "mode": self.mode,
                "suggestion": "检查 bridge_script 路径配置"
            }
            self._log_execution(result, context)
            return result
        
        # 2. 执行命令（通过桥接脚本）
        try:
            start_time = datetime.now()
            
            result = subprocess.run(
                ["bash", self.bridge_script, cmd],
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                shell=False
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            # 3. 解析桥接脚本返回的 JSON
            try:
                # 尝试从 stdout 解析 JSON
                output_lines = result.stdout.strip().split('\n')
                json_lines = []
                in_json = False
                
                for line in output_lines:
                    if line.startswith('{'):
                        in_json = True
                    if in_json:
                        json_lines.append(line)
                    if line.startswith('}'):
                        break
                
                if json_lines:
                    result_data = json.loads('\n'.join(json_lines))
                else:
                    # 回退到简单解析
                    result_data = {
                        "success": result.returncode == 0,
                        "exit_code": result.returncode,
                        "stdout": result.stdout[:1000],
                        "stderr": result.stderr[:500],
                        "risk_level": "UNKNOWN",
                        "cmd": cmd,
                        "mode": self.mode
                    }
                    
            except json.JSONDecodeError:
                result_data = {
                    "success": result.returncode == 0,
                    "exit_code": result.returncode,
                    "stdout": result.stdout[:1000],
                    "stderr": result.stderr[:500],
                    "risk_level": "UNKNOWN",
                    "cmd": cmd,
                    "mode": self.mode,
                    "parse_error": True
                }
            
            # 4. 添加执行元数据
            result_data["executed_at"] = start_time.isoformat()
            result_data["duration_seconds"] = duration
            result_data["context"] = context
            
            # 5. 记录到历史
            self._log_execution(result_data, context)
            
            return result_data
            
        except subprocess.TimeoutExpired:
            result = {
                "success": False,
                "error": "命令执行超时(5分钟)",
                "cmd": cmd,
                "risk_level": "TIMEOUT",
                "mode": self.mode
            }
            self._log_execution(result, context)
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "error": str(e),
                "cmd": cmd,
                "risk_level": "ERROR",
                "mode": self.mode
            }
            self._log_execution(result, context)
            return result
    
    def _is_ultra_high_risk(self, cmd: str) -> bool:
        """检查是否为极高风险操作（准自主模式的最后防线）"""
        ultra_high_patterns = [
            "rm -rf /", "mkfs", "dd if=/dev/zero", "> /etc/passwd",
            "chmod 777 /", "userdel root", "rm -rf /root", 
            "rm -rf /etc", "rm -rf /var", "mkfs.ext4"
        ]
        
        cmd_lower = cmd.lower()
        for pattern in ultra_high_patterns:
            if pattern in cmd_lower:
                return True
        return False
    
    def _log_execution(self, result: Dict, context: str):
        """记录执行历史"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "cmd": result.get("cmd", ""),
            "success": result.get("success", False),
            "risk_level": result.get("risk_level", "UNKNOWN"),
            "context": context,
            "exit_code": result.get("exit_code", -1)
        }
        
        self._execution_history.append(entry)
        
        # 限制历史大小
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]
    
    def get_execution_history(self, limit: int = 10) -> list:
        """获取最近执行历史"""
        return self._execution_history[-limit:]
    
    def get_stats(self) -> Dict:
        """获取执行统计"""
        if not self._execution_history:
            return {"total": 0, "success_rate": 0, "mode": self.mode}
        
        total = len(self._execution_history)
        successful = sum(1 for e in self._execution_history if e.get("success"))
        
        return {
            "total": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0,
            "mode": self.mode,
            "bridge_script": self.bridge_script
        }
    
    def tail_log(self, lines: int = 20) -> str:
        """读取最近日志"""
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", str(lines), self.log_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout if result.returncode == 0 else f"无法读取日志: {result.stderr}"
        except Exception as e:
            return f"读取日志失败: {e}"
