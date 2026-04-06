#!/usr/bin/env python3
"""
Aeon Health Monitor - 独立健康检查脚本

不依赖Aeon Agent运行，用于外部监控。
可以定时执行（cron）或手动运行。

功能:
- 检查服务状态
- 检查HTTP健康端点
- 自动重启失败的服务
- 发送告警通知

Usage:
    ./health_monitor.py           # 单次检查
    ./health_monitor.py --daemon  # 持续监控（每60秒）
    ./health_monitor.py --alert   # 检查失败时发送告警
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# 添加agent路径
sys.path.insert(0, '/root/.openclaw/workspace/agent')

HEALTH_URL = "http://localhost:9090/health"
SERVICE_NAME = "aeon-agent.service"


class HealthMonitor:
    """健康监控器"""
    
    def __init__(self, auto_restart=False, send_alert=False):
        self.auto_restart = auto_restart
        self.send_alert = send_alert
        self.alert_sent = False  # 防止重复告警
    
    def check_systemd(self) -> tuple[bool, str]:
        """检查systemd服务状态"""
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=5
            )
            status = result.stdout.strip()
            if status == "active":
                return True, "running"
            elif status == "activating":
                return True, "starting"
            elif status == "failed":
                return False, "failed"
            else:
                return False, status
        except Exception as e:
            return False, f"error: {e}"
    
    def check_http_health(self) -> tuple[bool, dict]:
        """检查HTTP健康端点"""
        try:
            response = urllib.request.urlopen(HEALTH_URL, timeout=5)
            data = json.loads(response.read())
            return data.get('status') == 'healthy', data
        except Exception as e:
            return False, {"error": str(e)}
    
    def restart_service(self) -> bool:
        """重启服务"""
        try:
            # 先重置失败状态
            subprocess.run(
                ['systemctl', 'reset-failed', SERVICE_NAME],
                capture_output=True,
                timeout=10
            )
            # 然后重启
            result = subprocess.run(
                ['systemctl', 'restart', SERVICE_NAME],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except Exception as e:
            print(f"重启失败: {e}")
            return False
    
    def send_notification(self, title: str, message: str, level: str = "error"):
        """发送告警通知"""
        if not self.send_alert:
            return False
        
        try:
            from alert import get_alert_manager, AlertLevel
            alert = get_alert_manager()
            
            level_map = {
                "info": AlertLevel.INFO,
                "warning": AlertLevel.WARNING,
                "error": AlertLevel.ERROR,
                "critical": AlertLevel.CRITICAL,
            }
            
            return alert.send(
                title=title,
                message=message,
                level=level_map.get(level, AlertLevel.ERROR),
                force=True  # 忽略抑制，确保关键告警送达
            )
        except Exception as e:
            print(f"发送告警失败: {e}")
            return False
    
    def check_once(self) -> dict:
        """执行单次检查"""
        result = {
            "timestamp": datetime.now().isoformat(),
            "systemd_ok": False,
            "systemd_status": "unknown",
            "http_ok": False,
            "http_data": {},
            "action_taken": None,
            "alert_sent": False,
        }
        
        # 1. 检查systemd
        systemd_ok, systemd_status = self.check_systemd()
        result["systemd_ok"] = systemd_ok
        result["systemd_status"] = systemd_status
        
        # 2. 检查HTTP（只有systemd running才检查）
        if systemd_ok and systemd_status == "running":
            http_ok, http_data = self.check_http_health()
            result["http_ok"] = http_ok
            result["http_data"] = http_data
        
        # 3. 判断整体状态
        overall_ok = systemd_ok and result["http_ok"]
        
        if not overall_ok:
            print(f"[WARNING] 健康检查失败: systemd={systemd_status}, http={result['http_ok']}")
            
            # 自动重启
            if self.auto_restart and systemd_status == "failed":
                print("[ACTION] 正在重启服务...")
                if self.restart_service():
                    result["action_taken"] = "restarted"
                    print("[OK] 服务已重启")
                    
                    # 等待几秒再检查
                    time.sleep(3)
                    systemd_ok, systemd_status = self.check_systemd()
                    if systemd_ok:
                        print("[OK] 重启后服务运行正常")
                        result["systemd_ok"] = True
                        result["systemd_status"] = systemd_status
                        
                        # 发送恢复通知
                        if self.send_alert:
                            result["alert_sent"] = self.send_notification(
                                "Aeon Agent 已恢复",
                                f"服务已自动重启，当前状态: {systemd_status}",
                                level="info"
                            )
                else:
                    result["action_taken"] = "restart_failed"
                    print("[ERROR] 重启失败")
            
            # 发送故障告警（如果没有发送过恢复通知）
            if self.send_alert and not result["alert_sent"]:
                result["alert_sent"] = self.send_notification(
                    "Aeon Agent 故障告警",
                    f"Systemd: {systemd_status}\nHTTP: {result['http_ok']}",
                    level="critical" if systemd_status == "failed" else "error"
                )
                self.alert_sent = True
        else:
            # 服务正常，重置告警标记
            if self.alert_sent:
                self.alert_sent = False
        
        return result
    
    def run_daemon(self, interval: int = 60):
        """持续监控模式"""
        print(f"[Health Monitor] 持续监控模式启动，间隔 {interval} 秒")
        print(f"[Health Monitor] 按 Ctrl+C 停止")
        
        try:
            while True:
                result = self.check_once()
                status = "✅" if result["systemd_ok"] and result["http_ok"] else "❌"
                print(f"{status} {result['timestamp']} - systemd: {result['systemd_status']}, "
                      f"http: {'ok' if result['http_ok'] else 'fail'}")
                
                if result["action_taken"]:
                    print(f"   执行操作: {result['action_taken']}")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n[Health Monitor] 已停止")


def main():
    parser = argparse.ArgumentParser(description='Aeon Health Monitor')
    parser.add_argument('--daemon', '-d', action='store_true', help='持续监控模式')
    parser.add_argument('--interval', '-i', type=int, default=60, help='检查间隔（秒）')
    parser.add_argument('--restart', '-r', action='store_true', help='失败时自动重启')
    parser.add_argument('--alert', '-a', action='store_true', help='发送告警通知')
    parser.add_argument('--json', '-j', action='store_true', help='输出JSON格式')
    
    args = parser.parse_args()
    
    monitor = HealthMonitor(
        auto_restart=args.restart,
        send_alert=args.alert
    )
    
    if args.daemon:
        monitor.run_daemon(interval=args.interval)
    else:
        result = monitor.check_once()
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            status = "✅ HEALTHY" if result["systemd_ok"] and result["http_ok"] else "❌ UNHEALTHY"
            print(f"{status}")
            print(f"  Systemd: {result['systemd_status']}")
            print(f"  HTTP: {'ok' if result['http_ok'] else 'fail'}")
            if result["action_taken"]:
                print(f"  Action: {result['action_taken']}")
            if result["alert_sent"]:
                print(f"  Alert: sent")


if __name__ == '__main__':
    main()
