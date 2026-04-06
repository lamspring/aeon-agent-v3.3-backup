#!/usr/bin/env python3
"""
Task Generator - 任务生成器
AI思考并生成任务，写入pending队列
不直接执行任务，只负责生产
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

def generate_task(task_type, goal, priority=2, source="ai_thought"):
    """
    生成新任务
    
    Args:
        task_type: "research", "learn", "build", "explore"
        goal: 任务目标描述
        priority: 1-5, 5最高
        source: 任务来源
    """
    task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    task = {
        "task_id": task_id,
        "type": task_type,
        "goal": goal,
        "priority": priority,
        "created": datetime.now().isoformat(),
        "source": source
    }
    
    # 写入pending队列
    pending_file = AGENT_DIR / "tasks" / "queue" / "pending.json"
    pending = read_json(pending_file)
    pending.append(task)
    write_json(pending_file, pending)
    
    print(f"[GENERATOR] Task created: {task_id}")
    print(f"[GENERATOR] Type: {task_type}, Goal: {goal}, Priority: {priority}")
    
    return task

def ai_think_and_generate():
    """
    AI思考并生成任务
    基于当前状态和好奇心生成任务
    """
    print("[AI THINKING] 思考中...")
    
    # 这里可以接入真正的AI推理
    # 简化示例：基于优先级生成
    ideas = [
        ("research", "explore multi-agent collaboration patterns", 3),
        ("learn", "study vector databases for memory", 2),
        ("build", "create a simple web scraper", 3),
        ("explore", "test new OpenAI models", 4),
    ]
    
    import random
    task_type, goal, priority = random.choice(ideas)
    
    return generate_task(task_type, goal, priority, source="ai_curiosity")

if __name__ == "__main__":
    # 测试生成任务
    print("=== Task Generator Test ===")
    task = ai_think_and_generate()
    print(f"\nGenerated: {task}")
