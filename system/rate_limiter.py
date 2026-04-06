#!/usr/bin/env python3
"""
Rate Limiter - 限流器
防止Agent疯狂调用API和创建任务
"""
import json
import time
from pathlib import Path
from datetime import datetime, timedelta

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

class RateLimiter:
    """API和任务创建限流器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.state = self._load_state()
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "rate_limiter.json"
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _load_state(self):
        """加载状态"""
        state_path = AGENT_DIR / "system" / "rate_limiter_state.json"
        if state_path.exists():
            with open(state_path, 'r') as f:
                return json.load(f)
        return {
            "api_calls": [],  # 时间戳列表
            "tasks_created": [],
            "last_reset": datetime.now().isoformat()
        }
    
    def _save_state(self):
        """保存状态"""
        state_path = AGENT_DIR / "system" / "rate_limiter_state.json"
        with open(state_path, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _count_in_window(self, timestamps, window_seconds):
        """计算时间窗口内的数量"""
        now = datetime.now()
        cutoff = now - timedelta(seconds=window_seconds)
        return sum(1 for ts in timestamps if datetime.fromisoformat(ts) > cutoff)
    
    def check_api_call(self, action="generic"):
        """
        检查是否可以进行API调用
        
        Returns:
            (allowed, reason, remaining)
        """
        if not self.config.get("enabled", True):
            return True, "Rate limiter disabled", -1
        
        limits = self.config.get("limits", {})
        
        # 清理旧记录
        now = datetime.now()
        self.state["api_calls"] = [
            ts for ts in self.state["api_calls"]
            if datetime.fromisoformat(ts) > now - timedelta(hours=1)
        ]
        
        # 检查每分钟限制
        per_minute = limits.get("api_calls_per_minute", 10)
        calls_in_minute = self._count_in_window(self.state["api_calls"], 60)
        if calls_in_minute >= per_minute:
            return False, f"API rate limit exceeded: {calls_in_minute}/{per_minute} per minute", 0
        
        # 检查每小时限制
        per_hour = limits.get("api_calls_per_hour", 100)
        calls_in_hour = self._count_in_window(self.state["api_calls"], 3600)
        if calls_in_hour >= per_hour:
            return False, f"API rate limit exceeded: {calls_in_hour}/{per_hour} per hour", 0
        
        # 记录本次调用
        self.state["api_calls"].append(now.isoformat())
        self._save_state()
        
        remaining_minute = per_minute - calls_in_minute - 1
        remaining_hour = per_hour - calls_in_hour - 1
        
        return True, "OK", min(remaining_minute, remaining_hour)
    
    def check_task_creation(self, task_type="generic", parent_depth=0):
        """
        检查是否可以创建任务
        
        Returns:
            (allowed, reason)
        """
        if not self.config.get("enabled", True):
            return True, "Rate limiter disabled"
        
        limits = self.config.get("limits", {})
        
        # 检查pending任务总数
        try:
            from queue import TaskQueue
            queue = TaskQueue()
            pending_count = len(queue.get_pending())
            max_pending = limits.get("max_pending_tasks", 20)
            if pending_count >= max_pending:
                return False, f"Too many pending tasks: {pending_count}/{max_pending}"
        except:
            pass
        
        # 检查树深度
        max_depth = limits.get("max_tree_depth", 3)
        if parent_depth >= max_depth:
            return False, f"Max tree depth reached: {max_depth}"
        
        # 记录任务创建
        now = datetime.now()
        self.state["tasks_created"] = [
            ts for ts in self.state["tasks_created"]
            if datetime.fromisoformat(ts) > now - timedelta(hours=1)
        ]
        self.state["tasks_created"].append(now.isoformat())
        self._save_state()
        
        return True, "OK"
    
    def check_subtask_spawn(self, parent_task):
        """
        检查是否可以产生子任务
        
        Returns:
            (allowed, reason)
        """
        limits = self.config.get("limits", {})
        max_subtasks = limits.get("subtasks_per_task", 5)
        
        current_children = len(parent_task.get("children", []))
        if current_children >= max_subtasks:
            return False, f"Max subtasks per task reached: {current_children}/{max_subtasks}"
        
        depth = parent_task.get("depth", 0)
        return self.check_task_creation("subtask", depth)
    
    def get_stats(self):
        """获取当前限流统计"""
        stats = {
            "api_calls_last_minute": self._count_in_window(self.state["api_calls"], 60),
            "api_calls_last_hour": self._count_in_window(self.state["api_calls"], 3600),
            "tasks_created_last_hour": self._count_in_window(self.state["tasks_created"], 3600),
            "limits": self.config.get("limits", {})
        }
        return stats
    
    def reset(self):
        """重置计数器 (危险操作)"""
        self.state = {
            "api_calls": [],
            "tasks_created": [],
            "last_reset": datetime.now().isoformat()
        }
        self._save_state()

if __name__ == "__main__":
    limiter = RateLimiter()
    
    print("=== Rate Limiter Test ===")
    print(f"Enabled: {limiter.config.get('enabled')}")
    print(f"Limits: {limiter.config.get('limits')}")
    
    # 测试API调用检查
    allowed, reason, remaining = limiter.check_api_call("test")
    print(f"\nAPI Call Check: {allowed} ({reason})")
    print(f"Remaining: {remaining}")
    
    # 测试任务创建检查
    allowed, reason = limiter.check_task_creation("research")
    print(f"\nTask Creation Check: {allowed} ({reason})")
    
    # 显示统计
    print(f"\nStats: {limiter.get_stats()}")
