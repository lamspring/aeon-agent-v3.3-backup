#!/usr/bin/env python3
"""
Perception Module - 感知模块
感知当前系统状态和环境
"""
import json
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

class Perception:
    """感知模块 - 收集系统状态"""
    
    def __init__(self):
        self.perception_data = {}
    
    def perceive(self):
        """
        感知当前状态
        
        Returns:
            {
                "system_state": {},
                "task_state": {},
                "resource_state": {},
                "time_context": {}
            }
        """
        self.perception_data = {
            "timestamp": datetime.now().isoformat(),
            "system_state": self._perceive_system(),
            "task_state": self._perceive_tasks(),
            "resource_state": self._perceive_resources(),
            "time_context": self._perceive_time()
        }
        
        return self.perception_data
    
    def _perceive_system(self):
        """感知系统状态"""
        try:
            # 读取gate状态
            gate_path = AGENT_DIR / "system" / "gate.json"
            gate_status = "unknown"
            if gate_path.exists():
                with open(gate_path, 'r') as f:
                    gate = json.load(f)
                    gate_status = "open" if gate.get("agent_enabled") else "closed"
            
            # 读取状态机
            state_path = AGENT_DIR / "system" / "state.json"
            state = "unknown"
            if state_path.exists():
                with open(state_path, 'r') as f:
                    s = json.load(f)
                    state = s.get("state", "unknown")
            
            return {
                "gate": gate_status,
                "state": state,
                "health": self._check_health()
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _perceive_tasks(self):
        """感知任务状态"""
        try:
            from queue import TaskQueue
            queue = TaskQueue()
            
            pending = queue.get_pending()
            running = queue.get_running()
            finished = queue.get_finished()
            
            # 计算树结构
            tree_count = len([t for t in pending if t.get("parent_id")]) if pending else 0
            
            return {
                "pending_count": len(pending),
                "has_running": running.get("task_id") is not None,
                "running_task": running.get("goal") if running.get("task_id") else None,
                "finished_count": len(finished),
                "tree_tasks": tree_count,
                "workload": "high" if len(pending) > 10 else "medium" if len(pending) > 3 else "low"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _perceive_resources(self):
        """感知资源状态"""
        try:
            # 检查限流状态
            from system.rate_limiter import RateLimiter
            limiter = RateLimiter()
            rate_stats = limiter.get_stats()
            
            # 检查磁盘
            import shutil
            disk = shutil.disk_usage("/")
            disk_usage = (disk.used / disk.total) * 100
            
            return {
                "api_calls_last_hour": rate_stats.get("api_calls_last_hour", 0),
                "api_limit": rate_stats.get("limits", {}).get("api_calls_per_hour", 100),
                "disk_usage_percent": round(disk_usage, 1),
                "status": "ok" if disk_usage < 80 else "warning"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _perceive_time(self):
        """感知时间上下文"""
        now = datetime.now()
        hour = now.hour
        
        time_of_day = "night" if hour < 6 else \
                      "morning" if hour < 12 else \
                      "afternoon" if hour < 18 else "evening"
        
        return {
            "hour": hour,
            "time_of_day": time_of_day,
            "day_of_week": now.strftime("%A"),
            "date": now.strftime("%Y-%m-%d")
        }
    
    def _check_health(self):
        """检查系统健康状态"""
        # 简化检查
        return "healthy"
    
    def summarize(self):
        """生成感知摘要"""
        if not self.perception_data:
            self.perceive()
        
        task_state = self.perception_data.get("task_state", {})
        system_state = self.perception_data.get("system_state", {})
        time_context = self.perception_data.get("time_context", {})
        
        summary_parts = []
        
        # 时间
        summary_parts.append(f"It's {time_context.get('time_of_day', 'unknown')}")
        
        # 任务状态
        if task_state.get("has_running"):
            summary_parts.append(f"working on '{task_state.get('running_task', 'task')}'")
        elif task_state.get("pending_count", 0) > 0:
            summary_parts.append(f"have {task_state.get('pending_count')} tasks pending")
        else:
            summary_parts.append("idle")
        
        # 系统状态
        if system_state.get("gate") == "open":
            summary_parts.append("autonomy enabled")
        
        return ", ".join(summary_parts)

if __name__ == "__main__":
    perception = Perception()
    data = perception.perceive()
    
    print("=== Perception Module Test ===")
    print(json.dumps(data, indent=2))
    print(f"\n📋 Summary: {perception.summarize()}")
