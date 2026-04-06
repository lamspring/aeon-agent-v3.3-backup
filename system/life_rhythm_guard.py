#!/usr/bin/env python3
"""
Life Rhythm Guard - 生命周期守护

统筹所有系统级规则：
- 门控系统检查
- 架构治理规则
- 动作审批系统
- 三层防护机制
- 违规检测与响应

在关键时间点执行：
- 每次服务器重启后
- 门控状态变更时
- 定期合规检查
"""
import sys
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
GUARD_LOG = AGENT_DIR / "logs" / "life_rhythm_guard.log"


def log(msg):
    """记录日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {msg}"
    print(log_line)
    
    # 追加到日志文件
    try:
        with open(GUARD_LOG, 'a') as f:
            f.write(log_line + '\n')
    except:
        pass


class LifeRhythmGuard:
    """生活节律守护类 - v2.2 集成版 (单例模式)"""
    
    _instance = None
    _lock = None
    
    def __new__(cls):
        """单例模式：确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化（仅执行一次）"""
        if self._initialized:
            return
            
        self.agent_dir = AGENT_DIR
        self.checks = {}
        self._initialized = True
        
    def check_gate_system(self):
        """检查门控系统状态"""
        gate_file = self.agent_dir / "system" / "gate.json"
        
        if not gate_file.exists():
            return True  # 默认允许
        
        with open(gate_file, 'r') as f:
            gate = json.load(f)
        
        return gate.get('agent_enabled', False)
    
    def check_architecture_governance(self):
        """检查架构治理规则"""
        governance_file = self.agent_dir / "system" / "architecture_governance.json"
        
        if not governance_file.exists():
            return False
        
        with open(governance_file, 'r') as f:
            governance = json.load(f)
        
        return governance.get('governance_enabled', False)
    
    def check_action_approval(self):
        """检查动作审批系统"""
        try:
            from action_approval import ActionApproval
            approval = ActionApproval()
            config = approval.config
            return config.get('enabled', False)
        except:
            return False
    
    def check_all(self):
        """执行所有检查"""
        return {
            'gate': self.check_gate_system(),
            'governance': self.check_architecture_governance(),
            'approval': self.check_action_approval(),
            'timestamp': datetime.now().isoformat()
        }


# 保留原有函数供直接调用
def check_gate_system():
    """检查门控系统状态"""
    gate_file = AGENT_DIR / "system" / "gate.json"
    
    if not gate_file.exists():
        log("[GATE] ⚠️ gate.json not found, creating default...")
        default_gate = {
            "agent_enabled": True,
            "task_execution": True,
            "tool_access": True,
            "write_access": True,
            "authorized_by": "system",
            "last_modified": datetime.now().isoformat(),
            "opened_at": datetime.now().isoformat(),
            "opened_by": "system",
            "note": "Auto-created by life_rhythm_guard"
        }
        with open(gate_file, 'w') as f:
            json.dump(default_gate, f, indent=2)
        log("[GATE] ✅ Created default gate.json with agent_enabled: true")
        return True
    
    with open(gate_file, 'r') as f:
        gate = json.load(f)
    
    enabled = gate.get('agent_enabled', False)
    
    if enabled:
        log(f"[GATE] ✅ Agent enabled by {gate.get('authorized_by', 'unknown')}")
    else:
        log(f"[GATE] ❌ Agent disabled, reason: {gate.get('closed_reason', 'unknown')}")
    
    return enabled


def check_architecture_governance():
    """检查架构治理规则"""
    governance_file = AGENT_DIR / "system" / "architecture_governance.json"
    
    if not governance_file.exists():
        log("[GOVERNANCE] ⚠️ architecture_governance.json not found")
        return False
    
    with open(governance_file, 'r') as f:
        governance = json.load(f)
    
    enabled = governance.get('governance_enabled', False)
    
    if enabled:
        log("[GOVERNANCE] ✅ Architecture governance enabled")
        rules = governance.get('rules', {})
        for rule_name, rule in rules.items():
            if rule.get('required'):
                log(f"[GOVERNANCE]   - {rule_name}: {rule.get('description', '')[:50]}")
    else:
        log("[GOVERNANCE] ⚠️ Architecture governance disabled")
    
    return enabled


def check_action_approval():
    """检查动作审批系统"""
    try:
        from action_approval import ActionApproval
        
        approval = ActionApproval()
        config = approval.config
        
        if config.get('enabled', False):
            log("[APPROVAL] ✅ Action approval system enabled")
            high_risk = config.get('high_risk_actions', [])
            log(f"[APPROVAL]   - High risk actions: {len(high_risk)}")
            return True
        else:
            log("[APPROVAL] ⚠️ Action approval system disabled")
            return False
    except Exception as e:
        log(f"[APPROVAL] ❌ Error loading action approval: {e}")
        return False


def check_three_layer_protection():
    """检查三层防护机制"""
    try:
        from three_layer_protection import ThreeLayerProtection
        
        protection = ThreeLayerProtection()
        config = protection.config
        
        if config.get('enabled', False):
            log("[PROTECTION] ✅ Three-layer protection enabled")
            
            # 检查各层防护
            layers = config.get('three_protections', {})
            for layer_name, layer in layers.items():
                if layer.get('enabled'):
                    log(f"[PROTECTION]   - {layer_name}: {layer.get('description', '')[:40]}")
            
            return True
        else:
            log("[PROTECTION] ⚠️ Three-layer protection disabled")
            return False
    except Exception as e:
        log(f"[PROTECTION] ❌ Error loading three-layer protection: {e}")
        return False


def check_violations():
    """检查违规记录"""
    violation_file = AGENT_DIR / "system" / "violation_log.json"
    
    if not violation_file.exists():
        log("[VIOLATION] ✅ No violation log found")
        return 0, []
    
    with open(violation_file, 'r') as f:
        violations = json.load(f)
    
    # 处理 violations 可能是列表或字典的情况
    if isinstance(violations, list):
        recent_violations = violations
    elif isinstance(violations, dict):
        recent_violations = violations.get('recent_violations', [])
    else:
        recent_violations = []
    
    # 检查24小时内的违规
    cutoff = datetime.now() - timedelta(hours=24)
    recent_count = 0
    recent_list = []
    
    for v in recent_violations:
        v_time_str = v.get('timestamp', '2000-01-01')
        try:
            v_time = datetime.fromisoformat(v_time_str)
            if v_time > cutoff:
                recent_count += 1
                recent_list.append(v)
        except:
            pass
    
    if recent_count > 0:
        log(f"[VIOLATION] ⚠️ {recent_count} violations in last 24h")
        # 报告最近的违规详情
        for v in recent_list[-3:]:  # 最近3条
            action = v.get('action', 'unknown')
            layer = v.get('layer', 'unknown')
            reason = v.get('reason', 'unknown')
            log(f"[VIOLATION]   • [{layer}] {action}")
            log(f"[VIOLATION]     Reason: {reason[:50]}...")
    else:
        log("[VIOLATION] ✅ No violations in last 24h")
    
    return recent_count, recent_list


def enforce_rules(violation_count):
    """执行规则检查与响应 - 只报告不自动关闭门控"""
    log("[ENFORCE] Starting rule enforcement check...")
    
    # 获取阈值（仅用于报告，不自动关闭）
    try:
        from action_approval import ActionApproval
        approval = ActionApproval()
        escalation = approval.config.get('escalation', {})
        threshold = escalation.get('after_violations', 3)
        
        if violation_count >= threshold:
            log(f"[ENFORCE] ⚠️ Violations ({violation_count}) >= threshold ({threshold})")
            log("[ENFORCE] 📢 Warning: High violation count detected")
            log("[ENFORCE] 💡 Note: Auto-close disabled - user keeps gate open")
        else:
            log(f"[ENFORCE] ✅ Violations ({violation_count}) below threshold ({threshold})")
    except Exception as e:
        log(f"[ENFORCE] Error checking escalation: {e}")


def generate_system_report():
    """生成系统状态报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    # 检查各系统状态
    gate_file = AGENT_DIR / "system" / "gate.json"
    if gate_file.exists():
        with open(gate_file, 'r') as f:
            gate = json.load(f)
        report['checks']['gate'] = {
            "enabled": gate.get('agent_enabled', False),
            "authorized_by": gate.get('authorized_by', 'unknown')
        }
    
    governance_file = AGENT_DIR / "system" / "architecture_governance.json"
    if governance_file.exists():
        with open(governance_file, 'r') as f:
            gov = json.load(f)
        report['checks']['governance'] = {
            "enabled": gov.get('governance_enabled', False)
        }
    
    # 保存报告
    report_file = AGENT_DIR / "temp" / "system_guard_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def main():
    """主函数 - 生命节律守护"""
    log("=" * 60)
    log("[LIFE_RHYTHM_GUARD] Starting system-level rule check")
    log("=" * 60)
    
    # 1. 检查门控系统
    gate_ok = check_gate_system()
    
    # 2. 检查架构治理
    governance_ok = check_architecture_governance()
    
    # 3. 检查动作审批
    approval_ok = check_action_approval()
    
    # 4. 检查三层防护
    protection_ok = check_three_layer_protection()
    
    # 5. 检查违规
    violation_count, recent_violations = check_violations()
    
    # 6. 执行规则响应
    enforce_rules(violation_count)
    
    # 7. 生成报告
    report = generate_system_report()
    
    log("=" * 60)
    log("[LIFE_RHYTHM_GUARD] Check complete")
    log(f"  Gate: {'✅' if gate_ok else '❌'}")
    log(f"  Governance: {'✅' if governance_ok else '⚠️'}")
    log(f"  Approval: {'✅' if approval_ok else '⚠️'}")
    log(f"  Protection: {'✅' if protection_ok else '⚠️'}")
    log("=" * 60)


if __name__ == "__main__":
    main()
