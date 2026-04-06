#!/usr/bin/env python3
"""
World Input - 世界输入系统

收集环境的各种输入，让Agent感知世界变化：
  1. 时间信息 - 几点、星期几、特殊日期
  2. 系统状态 - CPU、内存、磁盘、负载
  3. 网络信息 - 连通性、延迟、外部更新
  4. 用户活动 - 最近交互、当前项目、心情

结构: environment.json
"""
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
ENV_FILE = AGENT_DIR / "environment.json"

def read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

class WorldInput:
    """世界输入收集器"""
    
    def __init__(self):
        self.env_data = self._load_or_create()
    
    def _load_or_create(self):
        """加载或创建环境文件"""
        if ENV_FILE.exists():
            return read_json(ENV_FILE)
        return self._create_default()
    
    def _create_default(self):
        """创建默认环境"""
        return {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "time": {},
            "system": {},
            "network": {},
            "user_activity": {},
            "internet_updates": {"enabled": False},
            "world_events": [],
            "alerts": []
        }
    
    def _collect_time(self):
        """收集时间信息"""
        now = datetime.now()
        
        # 特殊日期检查
        special_days = {
            "2026-04-05": "Sunday Summary Day",
            "2026-04-06": "Monday Planning Day"
        }
        
        return {
            "hour": now.hour,
            "minute": now.minute,
            "day_of_week": now.weekday(),
            "day_name": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()],
            "date": now.strftime("%Y-%m-%d"),
            "is_weekend": now.weekday() >= 5,
            "is_working_hours": 9 <= now.hour < 18,
            "is_early_morning": 2 <= now.hour < 4,
            "special_day": special_days.get(now.strftime("%Y-%m-%d"))
        }
    
    def _collect_system(self):
        """收集系统状态"""
        try:
            import psutil
            
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            load = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
            
            # 判断系统状态
            status = "healthy"
            if cpu > 80 or mem.percent > 85:
                status = "stressed"
            elif cpu < 5 and mem.percent < 30:
                status = "idle"
            
            return {
                "cpu_percent": round(cpu, 1),
                "memory_percent": round(mem.percent, 1),
                "disk_percent": round(disk.percent, 1),
                "load_average": [round(x, 2) for x in load],
                "status": status
            }
        except:
            return {"status": "unknown"}
    
    def _collect_network(self):
        """收集网络状态"""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', '8.8.8.8'],
                capture_output=True
            )
            is_connected = result.returncode == 0
            
            return {
                "is_connected": is_connected,
                "timestamp": datetime.now().isoformat()
            }
        except:
            return {"is_connected": False}
    
    def _collect_user_activity(self):
        """收集用户活动信息"""
        # 从最近的日志推断
        log_file = AGENT_DIR / "logs" / "execution_log.txt"
        
        activity = {
            "last_interaction": None,
            "interaction_count_today": 0,
            "current_project": None,
            "recent_topics": [],
            "mood_hint": "unknown"
        }
        
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    today = datetime.now().strftime("%Y-%m-%d")
                    today_lines = [l for l in lines if today in l]
                    
                    activity["interaction_count_today"] = len(today_lines)
                    
                    if today_lines:
                        # 最后交互时间
                        last_line = today_lines[-1]
                        if '[' in last_line and ']' in last_line:
                            ts = last_line[1:20]
                            activity["last_interaction"] = ts
            except:
                pass
        
        return activity
    
    def _generate_alerts(self):
        """生成环境警报"""
        alerts = []
        
        # 系统警报
        sys_data = self.env_data.get("system", {})
        if sys_data.get("cpu_percent", 0) > 80:
            alerts.append("⚠️ 系统CPU使用率过高")
        if sys_data.get("memory_percent", 0) > 85:
            alerts.append("⚠️ 系统内存使用率过高")
        if sys_data.get("disk_percent", 0) > 90:
            alerts.append("⚠️ 磁盘空间不足")
        
        # 时间警报
        time_data = self.env_data.get("time", {})
        if time_data.get("is_early_morning"):
            alerts.append("💾 服务器即将重启时段")
        
        # 网络警报
        net_data = self.env_data.get("network", {})
        if not net_data.get("is_connected", True):
            alerts.append("❌ 网络连接中断")
        
        return alerts
    
    def collect(self):
        """
        收集所有环境输入
        
        Returns:
            dict: 完整的环境状态
        """
        self.env_data = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "time": self._collect_time(),
            "system": self._collect_system(),
            "network": self._collect_network(),
            "user_activity": self._collect_user_activity(),
            "internet_updates": self.env_data.get("internet_updates", {"enabled": False}),
            "world_events": self.env_data.get("world_events", []),
            "alerts": []
        }
        
        # 生成警报
        self.env_data["alerts"] = self._generate_alerts()
        
        # 保存
        write_json(ENV_FILE, self.env_data)
        
        return self.env_data
    
    def get_context_for_ai(self):
        """
        生成AI可读的上下文描述
        
        Returns:
            str: 自然语言描述的环境状态
        """
        self.collect()
        
        parts = []
        
        # 时间上下文
        time_data = self.env_data.get("time", {})
        if time_data:
            parts.append(f"现在是{time_data.get('day_name')} {time_data.get('hour')}点{time_data.get('minute')}分")
            
            if time_data.get("is_weekend"):
                parts.append("今天是周末")
            if time_data.get("special_day"):
                parts.append(f"特别的日子: {time_data['special_day']}")
        
        # 系统状态
        sys_data = self.env_data.get("system", {})
        if sys_data:
            status = sys_data.get("status", "unknown")
            if status == "healthy":
                parts.append("系统状态良好")
            elif status == "stressed":
                parts.append("系统负载较高")
            elif status == "idle":
                parts.append("系统处于空闲状态")
            
            parts.append(f"CPU使用率{sys_data.get('cpu_percent', '?')}%, 内存使用率{sys_data.get('memory_percent', '?')}%")
        
        # 网络状态
        net_data = self.env_data.get("network", {})
        if net_data:
            if net_data.get("is_connected"):
                parts.append("网络连接正常")
            else:
                parts.append("网络连接中断")
        
        # 用户活动
        user_data = self.env_data.get("user_activity", {})
        if user_data.get("interaction_count_today", 0) > 0:
            parts.append(f"今天和用户交互了{user_data['interaction_count_today']}次")
        
        # 警报
        if self.env_data.get("alerts"):
            parts.append("需要关注: " + "; ".join(self.env_data["alerts"]))
        
        return "。".join(parts) + "。"

if __name__ == "__main__":
    print("=== World Input Collection ===\n")
    
    world = WorldInput()
    env = world.collect()
    
    print("🌍 环境输入已收集:\n")
    print(json.dumps(env, indent=2, ensure_ascii=False))
    
    print("\n" + "="*50)
    print("\n📋 AI上下文描述:")
    print(world.get_context_for_ai())
