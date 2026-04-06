#!/usr/bin/env python3
"""
Reflection Engine Runner - 反思引擎执行脚本
"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/tasks')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

from reflection_engine import ReflectionEngine
from queue import TaskQueue

def main():
    engine = ReflectionEngine()
    queue = TaskQueue()
    
    if not engine.config.get('enabled', True):
        print('[REFLECTION] Engine disabled')
        return
    
    # 获取运行中任务
    running = queue.get_running()
    
    if running:
        task = running[0]
        task_state = {
            'finished': False,
            'has_result': task.get('current_step', 0) > 0
        }
        
        print(f'[REFLECTION] Checking task: {task["task_id"]}')
        
        # 检查是否应该反思
        should_reflect, reason = engine.should_reflect(task, task_state)
        
        if should_reflect:
            print(f'[REFLECTION] 🔄 Triggered: {reason}')
            
            # 执行反思
            result = engine.reflect(task, task_state)
            decision = result['decision']
            
            print(f'[REFLECTION] Decision: {decision}')
            print(f'[REFLECTION] Progress: {result["progress_status"]}')
            print(f'[REFLECTION] Strategy: {result["strategy_status"]}')
            
            # 应用决策
            new_task, should_continue = engine.apply_decision(task, decision, queue)
            
            if should_continue:
                print(f'[REFLECTION] ✅ Task will continue')
            else:
                print(f'[REFLECTION] ❌ Task stopped')
        else:
            print(f'[REFLECTION] ⏭️  No reflection needed: {reason}')
    else:
        # 没有运行中任务，检查是否需要定期反思
        engine.counter['heartbeat_count'] = engine.counter.get('heartbeat_count', 0) + 1
        
        periodic_interval = engine.config.get('periodic_interval', 5)
        
        if engine.counter['heartbeat_count'] >= periodic_interval:
            print(f'[REFLECTION] 🔄 Periodic reflection (every {periodic_interval} cycles)')
            
            # 检查待处理任务
            pending = queue.get_pending()
            if pending:
                print(f'[REFLECTION] {len(pending)} pending tasks waiting')
            
            engine.counter['heartbeat_count'] = 0
            engine.counter['last_reflection'] = __import__('datetime').datetime.now().isoformat()
        else:
            print(f'[REFLECTION] ⏭️  Periodic check ({engine.counter["heartbeat_count"]}/{periodic_interval})')
        
        engine._save_counter()

if __name__ == "__main__":
    main()
