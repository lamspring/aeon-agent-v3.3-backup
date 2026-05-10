"""
ExecutionModule - 执行模块 v2.0 (从 cognition_loop.py 迁移)

职责：
- 执行计划中的步骤
- 发布规划事件到 EventBus
- 记录执行结果

作者：虾虾
日期：2026-04-30
"""

import time
from typing import Dict, List, Optional, Any


class ExecutionModule:
    """
    执行模块 v2.0
    
    从 cognition_loop.py 的 _act() 方法迁移而来。
    """
    
    def __init__(self,
                 event_bus=None,
                 tool_adapter=None,
                 system_bridge=None,
                 message_bridge=None,
                 logger=None,
                 epu=None):
        
        self.event_bus = event_bus
        self.tool_adapter = tool_adapter
        self.system_bridge = system_bridge
        self.message_bridge = message_bridge
        self.logger = logger
        self.epu = epu
    
    def execute_plan(self, plan: Dict) -> Dict:
        """
        执行完整计划 (增强版)
        
        1. 发布规划事件到 EventBus
        2. 执行每个步骤
        3. 返回执行结果
        """
        goal = plan.get('goal', 'unknown')
        steps = plan.get('steps', [])
        
        if self.logger:
            self.logger.info(f"Executing plan: {goal}")
        
        # 发布规划事件
        if self.event_bus:
            try:
                self.event_bus.publish_simple(
                    "cognition.plan",
                    {
                        "plan_id": plan.get('plan_id'),
                        "goal": goal,
                        "steps": steps,
                    }
                )
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Failed to publish plan event: {e}")
        
        # 执行步骤
        results = []
        executed = 0
        for step in steps:
            result = self.execute_step(step)
            results.append(result)
            if result.get("success"):
                executed += 1
            else:
                break
        
        return {
            "goal": goal,
            "executed_steps": executed,
            "total_steps": len(steps),
            "results": results,
            "success": executed == len(steps),
        }
    
    def execute_step(self, step: Dict) -> Dict:
        """
        执行单个步骤 (v2.1 - EPU安全集成)
        """
        start = time.time()
        step_id = step.get("step_id", "unknown")
        step_type = step.get("type", "internal")
        action = step.get("action", "")
        
        # === v2.1: EPU执行前安全检查 ===
        if self.epu:
            try:
                action_desc = {
                    "type": step_type,
                    "tool_name": step.get("tool_name", ""),
                    "action": action,
                    "params": step.get("params", {}),
                }
                epu_result = self.epu.check_action(action_desc, context={"step_id": step_id})
                
                if not epu_result.passed:
                    if self.logger:
                        self.logger.warning(
                            f"EPU blocked step {step_id}: {epu_result.reason[:100]}",
                            component="ExecutionModule",
                            context={
                                "severity": epu_result.overall_severity,
                                "rules": [v.rule_id for v in epu_result.violated_rules],
                            }
                        )
                    return {
                        "step_id": step_id,
                        "success": False,
                        "error": f"EPU_BLOCKED: {epu_result.reason}",
                        "suggestion": epu_result.suggestion,
                        "duration_ms": (time.time() - start) * 1000,
                    }
            except Exception:
                pass  # EPU失败不阻塞执行
        
        try:
            if step_type == "tool":
                tool_name = step.get("tool_name", "")
                params = step.get("params", {})
                result = self._execute_tool(tool_name, params)
            elif step_type == "system":
                cmd = step.get("cmd", action)
                context = step.get("context", "")
                result = self._execute_system(cmd, context)
            elif step_type == "message":
                message = step.get("message", action)
                channel = step.get("channel", "")
                result = self._execute_message(message, channel)
            else:
                result = {"status": "done", "action": action}
            
            return {
                "step_id": step_id,
                "success": True,
                "result": result,
                "duration_ms": (time.time() - start) * 1000,
            }
        except Exception as e:
            return {
                "step_id": step_id,
                "success": False,
                "error": str(e),
                "duration_ms": (time.time() - start) * 1000,
            }
    
    def _execute_tool(self, tool_name: str, params: Dict) -> Dict:
        if not self.tool_adapter:
            return {"error": "ToolAdapter not available"}
        return self.tool_adapter.call(tool_name, params)
    
    def _execute_system(self, cmd: str, context: str) -> Dict:
        if not self.system_bridge:
            return {"error": "SystemBridge not available"}
        return self.system_bridge.execute(cmd, context)
    
    def _execute_message(self, message: str, channel: str) -> Dict:
        if not self.message_bridge:
            return {"error": "MessageBridge not available"}
        return self.message_bridge.send(message, channel=channel)