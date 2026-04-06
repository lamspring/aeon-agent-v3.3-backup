#!/usr/bin/env python3
"""
Agent Heartbeat - 任务队列架构版

Flow:
  Heartbeat → Gate → Risk → Queue Check → Worker → Memory → Sleep

如果 running 存在: 继续执行
如果 running 为空: 从 pending 取任务 → 开始执行
"""
import json
import sys
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR / "tasks"))

from queue import TaskQueue
from worker import TaskWorker

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

# ==================== Risk Controller ====================
class RiskController:
    def __init__(self):
        self.config = read_json(AGENT_DIR / "risk" / "config.json")
    
    def check(self):
        if not self.config.get("enabled", True):
            return True, "disabled"
        return True, "ok"

# ==================== Main Loop ====================
def heartbeat():
    """
    心跳主循环 - 任务队列架构
    """
    log("=" * 60)
    log("[HEARTBEAT] Triggered")
    log("=" * 60)
    
    # Step 1: Gate Check
    log("[STEP 1/6] Gate Check...")
    gate = read_json(AGENT_DIR / "system" / "gate.json")
    if not gate.get("agent_enabled"):
        log("[GATE] ❌ Closed")
        return {"status": "exit", "reason": "gate_closed"}
    log("[GATE] ✅ Open")
    
    # Step 2: Risk Check
    log("[STEP 2/6] Risk Check...")
    risk = RiskController()
    risk_ok, risk_msg = risk.check()
    
    # Step 3: State Check
    log("[STEP 3/6] State Check...")
    state = read_json(AGENT_DIR / "system" / "state.json")
    log(f"[STATE] Current: {state.get('state', 'idle')}")
    if not risk_ok:
        log(f"[RISK] ❌ {risk_msg}")
        return {"status": "exit", "reason": "risk"}
    log("[RISK] ✅ OK")
    
    # Step 3: Queue Check (核心逻辑)
    log("[STEP 3/6] Queue Check...")
    queue = TaskQueue()
    worker = TaskWorker()
    
    if queue.has_running_task():
        # 有正在运行的任务，继续执行
        log("[QUEUE] Found running task")
        running = queue.get_running()
        current_step = running.get('current_step', 0)
        log(f"[QUEUE] Task: {running['task_id']}, Step: {current_step}/{running['total_steps']}")
        
        # 执行下一步
        log("[STEP 4/6] Continue Task...")
        result = worker.execute_step(current_step)
        
        if result["finished"]:
            log("[WORKER] ✅ Task finished")
            # 移动到finished队列
            queue.move_to_finished(running, status="done")
            goal = f"Complete: {running['goal']}"
        else:
            log(f"[WORKER] Progress: {result['progress']:.0%}")
            goal = f"Continue: {running['goal']}"
        
        action = f"Execute step {running['current_step'] + 1}"
        result_msg = result["output"]
        
    else:
        # 没有运行任务，从pending取新任务
        log("[QUEUE] No running task")
        log("[QUEUE] Checking pending queue...")
        
        task = queue.pop_next_task()
        
        if task:
            log(f"[QUEUE] ✅ Got task: {task['task_id']}")
            log(f"[QUEUE] Type: {task['type']}, Priority: {task['priority']}")
            
            # 设置running状态
            log("[STEP 4/6] Start New Task...")
            running = queue.set_running(task)
            
            # 执行第一步
            result = worker.execute_step(0)
            
            goal = f"Start: {task['goal']}"
            action = "Initialize and execute step 1"
            result_msg = f"Task started: {task['task_id']}"
            
        else:
            log("[QUEUE] No pending tasks")
            log("[AI] Thinking about new tasks...")
            
            # AI生成新任务
            from generator import ai_think_and_generate
            new_task = ai_think_and_generate()
            
            goal = "Generate new task"
            action = "AI thinking and task generation"
            result_msg = f"Created: {new_task['task_id']}"
    
    # Step 5: Memory Update
    log("[STEP 5/6] Memory Update...")
    thoughts_file = AGENT_DIR / "logs" / "inner_thoughts.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    entry = f"""\n---\ntimestamp: {timestamp}\ngoal: {goal}\naction: {action}\nresult: {result_msg}\nreflection: Task queue processing complete\n---\n"""
    
    with open(thoughts_file, 'a') as f:
        f.write(entry)
    log("[MEMORY] ✅ Thought recorded")
    
    # Step 6: Sleep
    log("[STEP 6/6] Sleep...")
    log("[SLEEP] 💤 Next wake in 15 minutes")
    log("=" * 60)
    
    return {
        "status": "ok",
        "action": "continue" if queue.has_running_task() else "new_task"
    }

if __name__ == "__main__":
    result = heartbeat()
    print("\n", json.dumps(result, indent=2))
