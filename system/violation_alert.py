#!/usr/bin/env python3
"""
Violation Alert System - 违规实时告警系统

实时监控违规日志，新违规发生时立即报告
"""
import json
import os
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
VIOLATION_FILE = AGENT_DIR / "system" / "violation_log.json"
ALERT_STATE_FILE = AGENT_DIR / "temp" / "violation_alert_state.json"
ALERT_LOG = AGENT_DIR / "logs" / "violation_alerts.log"
USER_ALERT_FILE = AGENT_DIR / "temp" / "USER_VIOLATION_ALERT.txt"

def log(msg):
    """记录日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {msg}"
    print(log_line)
    with open(ALERT_LOG, 'a') as f:
        f.write(log_line + '\n')

def read_json(path):
    if not path.exists():
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return {}

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def send_alert(violation):
    """发送告警通知"""
    layer = violation.get('layer', 'unknown')
    action = violation.get('action', 'unknown')
    reason = violation.get('reason', 'unknown')
    timestamp = violation.get('timestamp', 'unknown')
    
    layer_name = {
        'action_filter': '第一道防线 - 动作过滤',
        'rate_limit': '第二道防线 - 速率限制',
        'critical_confirmation': '第三道防线 - 关键确认'
    }.get(layer, layer)
    
    # 构建告警消息
    alert_msg = f"""
🚨 **违规告警** 🚨

⏰ 时间: {timestamp}
🛡️ 防护层: {layer_name}
⚡ 动作: {action}
❌ 原因: {reason}

💡 系统已自动拦截此操作，未造成实际损害。
"""
    
    # 写入告警文件
    alert_file = AGENT_DIR / "temp" / "latest_violation_alert.txt"
    with open(alert_file, 'w') as f:
        f.write(alert_msg)
    
    # 写入用户告警文件 (大写文件名，醒目)
    with open(USER_ALERT_FILE, 'w') as f:
        f.write("=" * 50 + "\n")
        f.write("🚨 违规告警 - 需要您注意\n")
        f.write("=" * 50 + "\n")
        f.write(alert_msg)
        f.write("\n")
        f.write("查看详细报告: python3 agent/system/violation_report.py\n")
        f.write("=" * 50 + "\n")
    
    log(f"[ALERT] 🚨 New violation detected!")
    log(f"[ALERT]   Layer: {layer_name}")
    log(f"[ALERT]   Action: {action}")
    log(f"[ALERT]   Reason: {reason}")
    log(f"[ALERT]   User alert: {USER_ALERT_FILE}")
    
    return alert_msg

def check_new_violations():
    """检查新的违规记录"""
    # 读取当前违规列表
    violations = read_json(VIOLATION_FILE)
    
    if not violations:
        return 0
    
    # 确保是列表
    if not isinstance(violations, list):
        violations = []
    
    # 读取上次检查状态
    state = read_json(ALERT_STATE_FILE)
    last_count = state.get('last_violation_count', 0)
    
    current_count = len(violations)
    new_count = current_count - last_count
    
    if new_count > 0:
        log(f"[CHECK] Found {new_count} new violation(s)")
        
        # 获取最新的违规记录
        new_violations = violations[-new_count:]
        
        for violation in new_violations:
            send_alert(violation)
        
        # 更新状态
        state['last_violation_count'] = current_count
        state['last_alert_time'] = datetime.now().isoformat()
        state['new_violations_detected'] = new_count
        write_json(ALERT_STATE_FILE, state)
        
        return new_count
    else:
        # 更新计数但无新违规
        state['last_violation_count'] = current_count
        write_json(ALERT_STATE_FILE, state)
        
        # 如果没有新违规，清空用户告警文件
        if USER_ALERT_FILE.exists():
            USER_ALERT_FILE.unlink()
        
        return 0

def main():
    """主函数"""
    log("=" * 50)
    log("[VIOLATION_ALERT] Starting violation monitoring")
    log("=" * 50)
    
    # 读取现有状态
    state = read_json(ALERT_STATE_FILE)
    
    violations = read_json(VIOLATION_FILE)
    if isinstance(violations, list):
        current_count = len(violations)
    else:
        current_count = 0
    
    # 如果没有状态，初始化
    if not state or 'last_violation_count' not in state:
        log(f"[INIT] Initializing monitoring")
        state = {
            'last_violation_count': current_count,
            'monitoring_started': datetime.now().isoformat(),
            'last_alert_time': ''
        }
        write_json(ALERT_STATE_FILE, state)
        log(f"[INIT] Current violation count: {current_count}")
    else:
        log(f"[RESUME] Last recorded: {state.get('last_violation_count', 0)}, Current: {current_count}")
    
    # 执行检查
    new_count = check_new_violations()
    
    if new_count > 0:
        log(f"[RESULT] 🚨 Detected and alerted {new_count} new violation(s)")
    else:
        log(f"[RESULT] ✅ No new violations")
    
    log("=" * 50)

if __name__ == "__main__":
    main()
