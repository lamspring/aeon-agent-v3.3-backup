#!/usr/bin/env python3
"""
Watchdog - 任务超时监控

监控running任务，超时自动处理
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

class Watchdog:
    """任务超时监控器"""
    
    def __init__(self):
        self.config = read_json(AGENT_DIR / "system" / "watchdog.json")
    
    def is_enabled(self):
        return self.config.get("enabled", True)
    
    def check_timeout(self, running_task):
        """
        检查任务是否超时
        
        Returns:
            (is_timeout, elapsed_minutes, reason)
        """
        if not self.is_enabled():
            return False, 0, "watchdog_disabled"
        
        if not running_task or not running_task.get("task_id"):
            return False, 0, "no_running_task"
        
        started_at = running_task.get("started_at")
        if not started_at:
            return False, 0, "no_start_time"
        
        # 解析开始时间
        try:
            start_time = datetime.fromisoformat(started_at)
        except:
            return False, 0, "invalid_start_time"
        
        # 计算运行时间
        now = datetime.now()
        elapsed = now - start_time
        elapsed_minutes = elapsed.total_seconds() / 60
        
        timeout_minutes = self.config.get("timeout_minutes", 120)
        
        if elapsed_minutes > timeout_minutes:
            return True, elapsed_minutes, f"timeout_{timeout_minutes}min"
        
        return False, elapsed_minutes, "within_limit"
    
    def handle_timeout(self, running_task):
        """
        处理超时任务
        
        Returns:
            action_taken, new_status
        """
        if not running_task:
            return "no_action", None
        
        # 记录超时日志
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "task_id": running_task.get("task_id"),
            "action": "timeout_detected",
            "reason": f"Running > {self.config.get('timeout_minutes', 120)} minutes"
        }
        
        # 添加到timeout日志
        timeout_log_path = AGENT_DIR / "logs" / "timeout.log"
        try:
            with open(timeout_log_path, 'a') as f:
                f.write(f"[{log_entry['timestamp']}] Task {log_entry['task_id']}: {log_entry['reason']}\n")
        except:
            pass
        
        # 根据配置决定操作
        action = self.config.get("actions", {}).get("on_timeout", "kill_and_retry")
        
        if action == "kill_and_retry":
            # 检查重试次数
            retry_count = running_task.get("retry_count", 0)
            max_retries = self.config.get("max_retries", 3)
            
            if retry_count < max_retries:
                # 重试：重置step
                running_task["retry_count"] = retry_count + 1
                running_task["current_step"] = 0
                running_task["last_retry"] = datetime.now().isoformat()
                write_json(AGENT_DIR / "tasks" / "queue" / "running.json", running_task)
                return "retry", "retrying"
            else:
                # 超过重试次数，标记为error
                return "error", "max_retries_exceeded"
        
        elif action == "move_to_error":
            return "error", "timeout"
        
        return "kill", "killed"
    
    def get_status(self, running_task):
        """获取watchdog状态报告"""
        is_timeout, elapsed, reason = self.check_timeout(running_task)
        
        return {
            "enabled": self.is_enabled(),
            "timeout_minutes": self.config.get("timeout_minutes", 120),
            "elapsed_minutes": round(elapsed, 2),
            "is_timeout": is_timeout,
            "reason": reason,
            "status": "timeout" if is_timeout else "healthy"
        }

if __name__ == "__main__":
    print("=== Watchdog Test ===")
    
    wd = Watchdog()
    print(f"Enabled: {wd.is_enabled()}")
    print(f"Timeout: {wd.config.get('timeout_minutes')} minutes")
    
    # 测试正常任务
    normal_task = {
        "task_id": "task_normal",
        "started_at": datetime.now().isoformat()
    }
    is_timeout, elapsed, reason = wd.check_timeout(normal_task)
    print(f"\nNormal task: elapsed={elapsed:.1f}min, timeout={is_timeout}")
    
    # 测试超时任务
    old_time = datetime.now() - timedelta(minutes=150)
    timeout_task = {
        "task_id": "task_timeout",
        "started_at": old_time.isoformat()
    }
    is_timeout, elapsed, reason = wd.check_timeout(timeout_task)
    print(f"Old task: elapsed={elapsed:.1f}min, timeout={is_timeout}")
