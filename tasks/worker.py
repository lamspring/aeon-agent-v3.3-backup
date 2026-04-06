#!/usr/bin/env python3
"""
Task Worker - 任务执行器
负责执行running任务的具体步骤
"""
import json
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

class TaskWorker:
    """任务执行器"""
    
    def __init__(self):
        self.queue_dir = AGENT_DIR / "tasks" / "queue"
    
    def get_running(self):
        """获取当前运行任务"""
        return read_json(self.queue_dir / "running.json")
    
    def save_running(self, task):
        """保存运行状态"""
        write_json(self.queue_dir / "running.json", task)
    
    def execute_step(self, step_number):
        """
        执行一步任务
        从running.json中读取steps数组
        """
        running = self.get_running()
        
        # 检查是否有运行任务
        if not running.get("task_id"):
            return {"error": "No running task", "finished": True}
        
        task_type = running.get("type")
        goal = running.get("goal")
        steps = running.get("steps", [])
        
        print(f"[WORKER] Executing step {step_number} for {running['task_id']}")
        print(f"[WORKER] Type: {task_type}, Goal: {goal}")
        
        # 使用任务定义的steps
        if not steps:
            steps = ["step1", "step2", "step3", "step4"]
        
        if step_number >= len(steps):
            return {"finished": True, "output": "All steps completed"}
        
        step_name = steps[step_number]
        print(f"[WORKER] Step: {step_name}")
        
        # 执行步骤
        result = self._execute_step_logic(task_type, step_name)
        
        # 更新进度
        running["current_step"] = step_number + 1
        running["total_steps"] = len(steps)
        running["progress"] = (step_number + 1) / len(steps)
        self.save_running(running)
        
        return {
            "finished": False,
            "next_step": step_number + 1,
            "output": f"Step {step_number + 1} done: {step_name}",
            "progress": running["progress"]
        }
    
    def _generate_steps(self, task_type, goal):
        """根据任务类型生成步骤"""
        step_templates = {
            "research": ["search", "read", "analyze", "summarize"],
            "learn": ["find_resource", "study", "practice", "review"],
            "build": ["design", "code", "test", "deploy"],
            "explore": ["discover", "experiment", "evaluate", "report"]
        }
        return step_templates.get(task_type, ["step1", "step2", "step3", "step4"])
    
    def _execute_step_logic(self, task_type, step_name):
        """执行具体步骤逻辑"""
        # 这里将来可以接入实际的LLM或工具
        # 简化：模拟执行成功
        return {"status": "ok", "detail": f"Executed {step_name}"}
    
    def is_task_complete(self):
        """检查当前任务是否完成"""
        running = self.get_running()
        current = running.get("current_step", 0)
        total = running.get("total_steps", 4)
        return current >= total

if __name__ == "__main__":
    print("=== Task Worker Test ===")
    worker = TaskWorker()
    
    # 模拟执行一步
    result = worker.execute_step(0)
    print(f"Result: {result}")
