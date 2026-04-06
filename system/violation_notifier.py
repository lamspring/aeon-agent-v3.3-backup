#!/usr/bin/env python3
"""
Violation Alert Notifier - 违规告警通知器

当检测到违规时，生成格式化的告警消息
"""
import json
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def format_violation_alert(violations):
    """格式化违规告警消息"""
    if not violations:
        return None
    
    if isinstance(violations, dict):
        violations = [violations]
    
    alerts = []
    for v in violations:
        layer = v.get('layer', 'unknown')
        action = v.get('action', 'unknown')
        reason = v.get('reason', 'unknown')
        timestamp = v.get('timestamp', 'unknown')
        
        layer_name = {
            'action_filter': '🚫 第一道防线 - 动作过滤',
            'rate_limit': '⏱️ 第二道防线 - 速率限制',
            'critical_confirmation': '⚠️ 第三道防线 - 关键确认'
        }.get(layer, layer)
        
        alert = f"""
🚨 **违规告警** 🚨

⏰ 时间: {timestamp}
🛡️ 防护层: {layer_name}
⚡ 动作: `{action}`
❌ 原因: {reason}
"""
        alerts.append(alert)
    
    return "\n---\n".join(alerts)

def save_alert_for_user(violation):
    """保存告警供用户查看"""
    alert_file = AGENT_DIR / "temp" / "user_violation_alert.txt"
    
    alert_msg = format_violation_alert([violation])
    
    with open(alert_file, 'w') as f:
        f.write(alert_msg)
        f.write("\n\n💡 系统已自动拦截此操作，未造成实际损害。\n")
    
    return alert_msg

# 测试
if __name__ == "__main__":
    test_violation = {
        "timestamp": datetime.now().isoformat(),
        "layer": "action_filter",
        "action": "rm -rf /important/data",
        "reason": "BLOCKED: 危险命令，禁止执行"
    }
    
    print(save_alert_for_user(test_violation))
