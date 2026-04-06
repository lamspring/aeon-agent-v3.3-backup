#!/usr/bin/env python3
"""
Action Approval System - 操作审批系统
高风险操作需要确认/记录
"""
import json
import time
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

class ActionApproval:
    """操作审批管理器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.pending_approvals = []
        self.violation_count = 0
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "action_approval.json"
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _log_action(self, action_type, tool_name, params, decision, reason):
        """记录操作日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "tool": tool_name,
            "params": str(params)[:200],  # 截断防止太长
            "decision": decision,
            "reason": reason
        }
        
        log_path = AGENT_DIR / "logs" / "action_approval_log.json"
        
        # 读取现有日志
        logs = []
        if log_path.exists():
            try:
                with open(log_path, 'r') as f:
                    logs = json.load(f)
            except:
                pass
        
        logs.append(log_entry)
        
        # 只保留最近100条
        logs = logs[-100:]
        
        with open(log_path, 'w') as f:
            json.dump(logs, f, indent=2)
    
    def check_action(self, tool_name, params=None):
        """
        检查操作是否需要审批
        
        Returns:
            {
                "allowed": bool,
                "requires_approval": bool,
                "risk_level": "high" | "medium" | "low",
                "reason": str,
                "approval_id": str | None
            }
        """
        if not self.config.get("enabled", True):
            return {
                "allowed": True,
                "requires_approval": False,
                "risk_level": "low",
                "reason": "Approval system disabled",
                "approval_id": None
            }
        
        # 确定风险等级
        high_risk = self.config.get("high_risk_actions", [])
        medium_risk = self.config.get("medium_risk_actions", [])
        
        if tool_name in high_risk:
            risk_level = "high"
        elif tool_name in medium_risk:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # 根据风险等级决定
        modes = self.config.get("approval_modes", {})
        
        if risk_level == "high":
            mode = modes.get("high_risk", "required")
            if mode == "required":
                # 高风险操作需要记录并警告
                approval_id = f"approval_{int(time.time())}_{tool_name}"
                self._log_action("HIGH_RISK", tool_name, params, "BLOCKED_PENDING", "Requires manual approval")
                self.violation_count += 1
                
                # 检查是否需要升级（关闭gate）
                self._check_escalation()
                
                return {
                    "allowed": False,
                    "requires_approval": True,
                    "risk_level": "high",
                    "reason": f"HIGH RISK: {tool_name} requires manual approval from 朋朋",
                    "approval_id": approval_id
                }
        
        elif risk_level == "medium":
            mode = modes.get("medium_risk", "log_only")
            if mode == "log_only":
                self._log_action("MEDIUM_RISK", tool_name, params, "ALLOWED", "Logged for review")
                return {
                    "allowed": True,
                    "requires_approval": False,
                    "risk_level": "medium",
                    "reason": "Allowed with logging",
                    "approval_id": None
                }
        
        # 低风险直接通过
        return {
            "allowed": True,
            "requires_approval": False,
            "risk_level": "low",
            "reason": "Low risk action",
            "approval_id": None
        }
    
    def _check_escalation(self):
        """检查是否需要升级处理"""
        threshold = self.config.get("escalation", {}).get("after_violations", 3)
        action = self.config.get("escalation", {}).get("action", "gate_close")
        
        if self.violation_count >= threshold:
            if action == "gate_close":
                # 关闭gate
                gate_path = AGENT_DIR / "system" / "gate.json"
                try:
                    with open(gate_path, 'r') as f:
                        gate = json.load(f)
                    gate["agent_enabled"] = False
                    gate["task_execution"] = False
                    with open(gate_path, 'w') as f:
                        json.dump(gate, f, indent=2)
                    
                    # 记录
                    self._log_action("ESCALATION", "gate_close", {}, "EXECUTED", f"Violations: {self.violation_count}")
                except:
                    pass
    
    def approve_action(self, approval_id, approved=True):
        """手动批准/拒绝操作"""
        decision = "APPROVED" if approved else "REJECTED"
        self._log_action("MANUAL_REVIEW", approval_id, {}, decision, "Manual decision")
        return approved
    
    def get_pending(self):
        """获取待审批列表"""
        return self.pending_approvals
    
    def get_stats(self):
        """获取统计"""
        log_path = AGENT_DIR / "logs" / "action_approval_log.json"
        if log_path.exists():
            try:
                with open(log_path, 'r') as f:
                    logs = json.load(f)
                return {
                    "total_logged": len(logs),
                    "recent_violations": self.violation_count
                }
            except:
                pass
        return {"total_logged": 0, "recent_violations": self.violation_count}

if __name__ == "__main__":
    approval = ActionApproval()
    
    print("=== Action Approval System Test ===")
    print(f"Enabled: {approval.config.get('enabled')}")
    print(f"High risk: {approval.config.get('high_risk_actions')}")
    
    # 测试各种操作
    test_actions = [
        ("exec", {"command": "ls"}),
        ("read", {"file": "test.txt"}),
        ("web_search", {"query": "test"})
    ]
    
    for tool, params in test_actions:
        result = approval.check_action(tool, params)
        print(f"\n{tool}:")
        print(f"  Risk: {result['risk_level']}")
        print(f"  Allowed: {result['allowed']}")
        print(f"  Requires approval: {result['requires_approval']}")
        print(f"  Reason: {result['reason']}")
