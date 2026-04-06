#!/usr/bin/env python3
"""
Watchdog Runner - 看门狗执行脚本
"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/tasks')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

from watchdog import Watchdog
from queue import TaskQueue

def main():
    wd = Watchdog()
    queue = TaskQueue()
    
    # 获取运行中任务
    running = queue.get_running()
    
    if running:
        print(f'[WATCHDOG] Checking task: {running[0]["task_id"]}')
        is_timeout, elapsed, reason = wd.check_timeout(running[0])
        
        if is_timeout:
            print(f'[WATCHDOG] ⚠️ Task timeout! Elapsed: {elapsed:.1f}min')
            action, result = wd.handle_timeout(running[0])
            print(f'[WATCHDOG] Action: {action}, Result: {result}')
        else:
            print(f'[WATCHDOG] ✅ Task healthy, elapsed: {elapsed:.1f}min')
    else:
        print('[WATCHDOG] No running task to monitor')

if __name__ == "__main__":
    main()
