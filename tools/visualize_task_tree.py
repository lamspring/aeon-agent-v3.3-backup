#!/usr/bin/env python3
"""
Task Tree Visualizer - 任务树可视化工具

示例输出:
research ai agents
├── ⏳ search papers
├── ⏳ compare frameworks
└── ⏳ write summary
"""
import json
import sys
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR / "tasks"))

from queue import TaskQueue

def main():
    queue = TaskQueue()
    
    print("=" * 60)
    print("🌳 Task Tree Visualization")
    print("=" * 60)
    print()
    
    # 打印所有任务树
    roots = queue.get_task_tree()
    
    if not roots:
        print("No tasks found.")
        return
    
    for i, root in enumerate(roots):
        print(f"Tree {i+1}:")
        queue.print_task_tree(root)
        print()
    
    # 统计信息
    pending = queue.get_pending()
    running = queue.get_running()
    finished = queue.get_finished()
    
    print("=" * 60)
    print("📊 Statistics:")
    print(f"  Pending:  {len(pending)}")
    print(f"  Running:  {1 if running.get('task_id') else 0}")
    print(f"  Finished: {len(finished)}")
    
    # 统计树深度
    max_depth = 0
    all_tasks = pending + ([running] if running.get('task_id') else []) + finished
    for task in all_tasks:
        if isinstance(task, dict):
            max_depth = max(max_depth, task.get('depth', 0))
    
    print(f"  Max Depth: {max_depth}")
    print("=" * 60)

if __name__ == "__main__":
    main()
