#!/usr/bin/env python3
"""
Message Checker Runner - 消息检查器执行脚本
"""
import sys
import os

# 添加路径
sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

# 先导入消息检查器
from message_checker import MessageChecker

# 再添加 tasks 目录并导入 TaskQueue
sys.path.insert(0, '/root/.openclaw/workspace/agent/tasks')
import importlib.util
spec = importlib.util.spec_from_file_location("task_queue", "/root/.openclaw/workspace/agent/tasks/queue.py")
task_queue_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task_queue_module)
TaskQueue = task_queue_module.TaskQueue

def main():
    checker = MessageChecker()
    queue = TaskQueue()
    
    if not checker.is_enabled():
        print('[MESSAGE] Checker disabled')
        return
    
    # 检查消息
    result = checker.check_messages()
    
    if result['has_messages']:
        print(f"[MESSAGE] 📬 Found {result['count']} unread messages")
        
        # 处理消息并生成任务
        tasks = checker.process_messages()
        
        if tasks:
            for task in tasks:
                print(f"[MESSAGE] ➕ Adding task: {task['goal'][:50]}...")
                queue.add_task(task)
            
            print(f"[MESSAGE] ✅ Added {len(tasks)} tasks to queue")
        else:
            print("[MESSAGE] ⚠️ No tasks generated from messages")
    else:
        print('[MESSAGE] 📭 No new messages')

if __name__ == "__main__":
    main()
