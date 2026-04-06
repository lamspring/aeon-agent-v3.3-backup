#!/usr/bin/env python3
"""
State Machine Runner - 状态机执行脚本
"""
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/tasks')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
STATE_FILE = AGENT_DIR / "system" / "state.json"

def read_json(path):
    if not path.exists():
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def get_task_queue_status():
    """获取任务队列状态"""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("task_queue", "/root/.openclaw/workspace/agent/tasks/queue.py")
        task_queue_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(task_queue_module)
        TaskQueue = task_queue_module.TaskQueue
        
        queue = TaskQueue()
        pending = queue.get_pending()
        running = queue.get_running()
        
        return {
            "pending_count": len(pending),
            "running_count": len(running),
            "has_running": len(running) > 0,
            "current_task": running[0] if running else None
        }
    except Exception as e:
        print(f"[STATE] Error reading queue: {e}")
        return {"pending_count": 0, "running_count": 0, "has_running": False, "current_task": None}

def update_state():
    """更新状态机"""
    current_state = read_json(STATE_FILE)
    queue_status = get_task_queue_status()
    
    # 根据队列状态决定状态
    old_state = current_state.get("state", "idle")
    new_state = old_state
    
    if queue_status["has_running"]:
        new_state = "running"
        current_task = queue_status["current_task"]
        current_state["task"] = current_task.get("task_id") if current_task else None
        current_state["step"] = current_task.get("current_step", 0) if current_task else 0
    elif queue_status["pending_count"] > 0:
        new_state = "planning"
        current_state["task"] = None
        current_state["step"] = 0
    else:
        new_state = "idle"
        current_state["task"] = None
        current_state["step"] = 0
    
    # 更新状态
    current_state["state"] = new_state
    current_state["pending_count"] = queue_status["pending_count"]
    current_state["running_count"] = queue_status["running_count"]
    current_state["last_updated"] = datetime.now().isoformat()
    
    # 计算进度
    if queue_status["has_running"] and queue_status["current_task"]:
        task = queue_status["current_task"]
        total_steps = len(task.get("steps", []))
        current_step = task.get("current_step", 0)
        if total_steps > 0:
            current_state["progress"] = round((current_step / total_steps) * 100, 1)
        else:
            current_state["progress"] = 0.0
    else:
        current_state["progress"] = 0.0
    
    # 保存状态
    write_json(STATE_FILE, current_state)
    
    # 输出日志
    status_icon = {
        "idle": "😴",
        "planning": "📝",
        "running": "▶️"
    }.get(new_state, "❓")
    
    print(f"[STATE] {status_icon} State: {old_state} → {new_state}")
    print(f"[STATE] Pending: {queue_status['pending_count']}, Running: {queue_status['running_count']}")
    print(f"[STATE] Progress: {current_state['progress']}%")
    
    return current_state

if __name__ == "__main__":
    update_state()
