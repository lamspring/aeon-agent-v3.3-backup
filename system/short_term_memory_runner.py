#!/usr/bin/env python3
"""
Short-term Memory Runner - 短期记忆执行脚本

短期记忆包括：
- 当前会话上下文
- 最近的用户交互
- 正在进行的任务状态
- 临时变量和中间结果
"""
import sys
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
SHORT_TERM_FILE = AGENT_DIR / "temp" / "short_term_memory.json"
SESSIONS_FILE = Path("/root/.openclaw/plugins/kimi-claw/agents/main/sessions/sessions.json")

def read_json(path):
    if not path.exists():
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_recent_sessions():
    """获取最近会话信息"""
    try:
        if not SESSIONS_FILE.exists():
            return []
        
        data = read_json(SESSIONS_FILE)
        sessions = []
        
        for session_id, session_data in data.items():
            updated_at = session_data.get('updatedAt', 0)
            if updated_at:
                # 检查是否在24小时内
                updated_time = datetime.fromtimestamp(updated_at / 1000)
                if datetime.now() - updated_time < timedelta(hours=24):
                    sessions.append({
                        'id': session_id,
                        'updated_at': updated_time.isoformat(),
                        'message_count': len(session_data.get('messages', []))
                    })
        
        return sorted(sessions, key=lambda x: x['updated_at'], reverse=True)[:5]
    except Exception as e:
        print(f"[SHORT_TERM] Error reading sessions: {e}")
        return []

def get_current_context():
    """获取当前上下文"""
    context = {
        'timestamp': datetime.now().isoformat(),
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M'),
        'day_of_week': datetime.now().strftime('%A'),
        'hour': datetime.now().hour
    }
    
    # 判断时间段
    hour = context['hour']
    if 6 <= hour < 12:
        context['time_period'] = 'morning'
    elif 12 <= hour < 18:
        context['time_period'] = 'afternoon'
    elif 18 <= hour < 23:
        context['time_period'] = 'evening'
    else:
        context['time_period'] = 'night'
    
    return context

def get_active_tasks():
    """获取活跃任务"""
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
            'pending_count': len(pending),
            'running_count': len(running),
            'pending_tasks': [{'id': t.get('task_id'), 'goal': t.get('goal', '')[:50]} for t in list(pending)[:3]],
            'running_tasks': [{'id': t.get('task_id'), 'goal': t.get('goal', '')[:50], 'step': t.get('current_step', 0)} for t in list(running)[:2]]
        }
    except Exception as e:
        print(f"[SHORT_TERM] Error reading tasks: {e}")
        return {'pending_count': 0, 'running_count': 0, 'pending_tasks': [], 'running_tasks': []}

def update_short_term_memory():
    """更新短期记忆"""
    # 读取现有短期记忆
    memory = read_json(SHORT_TERM_FILE) if SHORT_TERM_FILE.exists() else {}
    
    # 更新各个部分
    memory['context'] = get_current_context()
    memory['recent_sessions'] = get_recent_sessions()
    memory['active_tasks'] = get_active_tasks()
    memory['last_updated'] = datetime.now().isoformat()
    
    # 保留一些临时变量（如果存在）
    if 'temp_vars' not in memory:
        memory['temp_vars'] = {}
    
    # 清理过期数据（保留最近24小时的交互记录）
    if 'interactions' in memory:
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        memory['interactions'] = [
            i for i in memory['interactions'] 
            if i.get('timestamp', '') > cutoff
        ][-20:]  # 只保留最近20条
    
    # 保存
    write_json(SHORT_TERM_FILE, memory)
    
    # 输出日志
    print(f"[SHORT_TERM] 💾 Memory updated at {memory['context']['time']}")
    print(f"[SHORT_TERM] Sessions: {len(memory['recent_sessions'])}, Tasks: {memory['active_tasks']['pending_count']} pending, {memory['active_tasks']['running_count']} running")
    
    return memory

def add_interaction(interaction_type, content):
    """添加交互记录（供其他模块调用）"""
    memory = read_json(SHORT_TERM_FILE) if SHORT_TERM_FILE.exists() else {}
    
    if 'interactions' not in memory:
        memory['interactions'] = []
    
    memory['interactions'].append({
        'timestamp': datetime.now().isoformat(),
        'type': interaction_type,
        'content': content[:200]  # 限制长度
    })
    
    write_json(SHORT_TERM_FILE, memory)

if __name__ == "__main__":
    update_short_term_memory()
