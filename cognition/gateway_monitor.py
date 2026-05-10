#!/usr/bin/env python3
"""
Aeon Gateway Bridge 健康监控脚本

功能：
1. 检查 Gateway Bridge 进程存活
2. 检查 9091 端口响应
3. 检查 message.received 事件小时级数量
4. 异常时发送告警

用法：
    python3 gateway_monitor.py  # 单次检查
    python3 gateway_monitor.py --daemon  # 后台每5分钟检查

作者：虾虾
日期：2026-05-01
"""

import sys
import time
import sqlite3
import requests
import subprocess
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

# 告警阈值
ALERT_NO_MESSAGE_HOURS = 1  # 连续1小时无消息则告警
ALERT_PORT_TIMEOUT = 5      # 端口检查超时秒数

# 数据库路径
EVENTS_DB = "/root/.openclaw/workspace/agent/db/events.db"

def check_process() -> Dict:
    """检查 systemd 服务状态"""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "aeon-gateway-bridge"],
            capture_output=True, text=True, timeout=5
        )
        return {
            "ok": result.returncode == 0,
            "status": result.stdout.strip(),
            "detail": result.stderr.strip() if result.returncode != 0 else ""
        }
    except Exception as e:
        return {"ok": False, "status": "check_failed", "detail": str(e)}

def check_port() -> Dict:
    """检查 9091 端口响应"""
    try:
        # gateway_bridge.py 没有 GET /api/status，改用 POST 测试
        r = requests.post(
            "http://localhost:9091/api/message",
            json={"user_id":"health_check","channel":"weixin","message":"ping","message_id":"ping"},
            timeout=ALERT_PORT_TIMEOUT
        )
        return {
            "ok": r.status_code in (200, 202),
            "status_code": r.status_code,
            "latency_ms": round(r.elapsed.total_seconds() * 1000, 1)
        }
    except requests.exceptions.ConnectionError:
        return {"ok": False, "status_code": None, "detail": "Connection refused"}
    except requests.exceptions.Timeout:
        return {"ok": False, "status_code": None, "detail": "Timeout"}
    except Exception as e:
        return {"ok": False, "status_code": None, "detail": str(e)}

def check_message_flow() -> Dict:
    """检查 message.received 事件流量"""
    try:
        conn = sqlite3.connect(EVENTS_DB)
        
        # 过去1小时
        one_hour_ago = int((datetime.now() - timedelta(hours=1)).timestamp())
        cursor = conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'message.received' AND timestamp > ?",
            (one_hour_ago,)
        )
        count_1h = cursor.fetchone()[0]
        
        # 过去24小时
        one_day_ago = int((datetime.now() - timedelta(days=1)).timestamp())
        cursor = conn.execute(
            "SELECT COUNT(*) FROM events WHERE type = 'message.received' AND timestamp > ?",
            (one_day_ago,)
        )
        count_24h = cursor.fetchone()[0]
        
        # 最新一条的时间
        cursor = conn.execute(
            "SELECT timestamp FROM events WHERE type = 'message.received' ORDER BY timestamp DESC LIMIT 1"
        )
        latest = cursor.fetchone()
        latest_time = datetime.fromtimestamp(latest[0]).strftime('%H:%M') if latest else "never"
        
        conn.close()
        
        return {
            "ok": count_1h > 0,
            "count_1h": count_1h,
            "count_24h": count_24h,
            "latest_time": latest_time,
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}

def send_alert(check_name: str, detail: str) -> None:
    """发送告警（写入日志 + 尝试消息推送）"""
    timestamp = datetime.now().isoformat()
    alert = f"[{timestamp}] 🚨 AEON ALERT: {check_name}\n{detail}"
    
    # 写入告警日志
    alert_log = Path("/root/.openclaw/workspace/agent/logs/alerts.log")
    alert_log.parent.mkdir(parents=True, exist_ok=True)
    with open(alert_log, "a") as f:
        f.write(alert + "\n\n")
    
    print(alert)
    
    # 尝试通过 MessageBridge 发送（如果可用）
    try:
        sys.path.insert(0, "/root/.openclaw/workspace/agent/cognition")
        from message_bridge import MessageBridge
        bridge = MessageBridge()
        bridge.alert_system("gateway_monitor", f"{check_name}: {detail[:100]}")
    except:
        pass

def run_check() -> Dict:
    """执行完整检查"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "checks": {}
    }
    
    # 1. 进程检查
    proc = check_process()
    results["checks"]["process"] = proc
    if not proc["ok"]:
        send_alert("Gateway Bridge 进程异常", f"systemctl status: {proc.get('status', 'unknown')}, detail: {proc.get('detail', '')}")
    
    # 2. 端口检查
    port = check_port()
    results["checks"]["port"] = port
    if not port["ok"]:
        send_alert("Gateway Bridge 端口无响应", f"9091: {port.get('detail', 'unknown')}")
    
    # 3. 消息流检查
    flow = check_message_flow()
    results["checks"]["message_flow"] = flow
    if not flow["ok"]:
        send_alert("消息流中断", f"过去1小时 message.received = {flow.get('count_1h', 'unknown')}, 最新: {flow.get('latest_time', 'unknown')}")
    
    # 汇总
    all_ok = all(c["ok"] for c in results["checks"].values())
    results["overall"] = "healthy" if all_ok else "degraded"
    
    # 写入状态日志
    status_log = Path("/root/.openclaw/workspace/agent/logs/gateway_monitor.jsonl")
    with open(status_log, "a") as f:
        f.write(json.dumps(results, ensure_ascii=False) + "\n")
    
    return results

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true", help="后台循环监控")
    parser.add_argument("--interval", type=int, default=300, help="检查间隔秒数（默认5分钟）")
    args = parser.parse_args()
    
    if args.daemon:
        print(f"[{datetime.now().isoformat()}] Gateway Monitor daemon started (interval={args.interval}s)")
        while True:
            result = run_check()
            status = "✅" if result["overall"] == "healthy" else "❌"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {status} {result['overall']}")
            time.sleep(args.interval)
    else:
        result = run_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
