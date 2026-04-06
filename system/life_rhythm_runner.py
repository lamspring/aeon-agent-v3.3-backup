#!/usr/bin/env python3
"""
Life Rhythm Runner - 生命周期节律执行脚本

根据当前时间判断处于哪个节律阶段，并执行相应的任务策略。
"""
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace/agent')
sys.path.insert(0, '/root/.openclaw/workspace/agent/system')

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
RHYTHM_FILE = AGENT_DIR / "system" / "life_rhythm.json"
STATE_FILE = AGENT_DIR / "system" / "state.json"
CURRENT_RHYTHM_FILE = AGENT_DIR / "temp" / "current_rhythm.json"

def read_json(path):
    if not path.exists():
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_current_rhythm():
    """根据当前时间获取当前节律"""
    config = read_json(RHYTHM_FILE)
    
    if not config.get('enabled', True):
        return None
    
    now = datetime.now()
    hour = now.hour
    
    cycles = config.get('cycles', [])
    
    for cycle in cycles:
        start = cycle.get('start_hour', 0)
        end = cycle.get('end_hour', 24)
        
        # 处理跨午夜的情况 (如 23-2)
        if start > end:
            if hour >= start or hour < end:
                return cycle
        else:
            if start <= hour < end:
                return cycle
    
    return None

def check_server_restart_approaching():
    """检查是否接近服务器重启时间"""
    config = read_json(RHYTHM_FILE)
    restart_config = config.get('server_restart', {})
    
    restart_time = restart_config.get('time', '04:00')
    preparation_start = restart_config.get('preparation_start', '02:00')
    
    now = datetime.now()
    restart_hour, restart_min = map(int, restart_time.split(':'))
    prep_hour, prep_min = map(int, preparation_start.split(':'))
    
    restart_dt = now.replace(hour=restart_hour, minute=restart_min, second=0, microsecond=0)
    prep_dt = now.replace(hour=prep_hour, minute=prep_min, second=0, microsecond=0)
    
    # 如果重启时间已过，算明天的
    if restart_dt < now:
        restart_dt += timedelta(days=1)
    if prep_dt < now:
        prep_dt += timedelta(days=1)
    
    minutes_to_restart = (restart_dt - now).total_seconds() / 60
    minutes_to_prep = (prep_dt - now).total_seconds() / 60
    
    return {
        'is_preparation_time': 0 <= minutes_to_prep <= 120,  # 准备阶段
        'is_imminent': 0 <= minutes_to_restart <= 30,  # 30分钟内重启
        'minutes_to_restart': minutes_to_restart,
        'minutes_to_prep': minutes_to_prep
    }

def generate_tasks_for_rhythm(cycle):
    """根据当前节律生成推荐任务"""
    if not cycle:
        return []
    
    preferred = cycle.get('preferred_tasks', [])
    tasks = []
    
    for task_type in preferred[:3]:  # 最多3个
        task = {
            'task_id': f"rhythm_{task_type}_{datetime.now().strftime('%H%M%S')}",
            'type': task_type,
            'goal': f"[生命周期] {cycle.get('display_name')} - {task_type}任务",
            'priority': 3,  # 中等优先级
            'source': 'life_rhythm',
            'rhythm_cycle': cycle.get('name'),
            'auto_generated': True
        }
        tasks.append(task)
    
    return tasks

def execute_rhythm_actions(cycle, restart_info):
    """执行当前节律的动作"""
    actions = []
    
    # 特殊阶段处理
    if cycle and cycle.get('special'):
        special = cycle['special']
        
        if special.get('is_preparation_phase'):
            # 准备重启阶段
            actions.append('save_state')
            actions.append('cleanup')
            actions.append('no_new_tasks')
            
        elif special.get('is_recovery_phase'):
            # 重启恢复阶段
            actions.append('health_check')
            actions.append('state_recovery')
            actions.append('warm_up')
    
    # 接近重启时的紧急处理
    if restart_info['is_imminent']:
        actions.append('urgent_save')
    
    return actions

def update_rhythm_state():
    """更新节律状态"""
    cycle = get_current_rhythm()
    restart_info = check_server_restart_approaching()
    
    rhythm_state = {
        'timestamp': datetime.now().isoformat(),
        'hour': datetime.now().hour,
        'current_cycle': cycle.get('name') if cycle else 'unknown',
        'display_name': cycle.get('display_name') if cycle else '未知',
        'focus': cycle.get('focus') if cycle else 'unknown',
        'mood': cycle.get('mood') if cycle else 'unknown',
        'quote': cycle.get('quote') if cycle else '',
        'restart_info': restart_info,
        'recommended_tasks': generate_tasks_for_rhythm(cycle),
        'actions': execute_rhythm_actions(cycle, restart_info)
    }
    
    # 保存当前节律状态
    write_json(CURRENT_RHYTHM_FILE, rhythm_state)
    
    # 同时更新到主状态文件
    main_state = read_json(STATE_FILE)
    main_state['life_rhythm'] = {
        'cycle': rhythm_state['current_cycle'],
        'focus': rhythm_state['focus'],
        'restart_approaching': restart_info['is_imminent']
    }
    write_json(STATE_FILE, main_state)
    
    # 输出日志
    icon = {
        'morning': '🌅',
        'afternoon': '☀️',
        'evening': '🌆',
        'night': '🌙',
        'pre_restart': '💾',
        'post_restart': '🌅'
    }.get(rhythm_state['current_cycle'], '⏰')
    
    print(f"[RHYTHM] {icon} Current: {rhythm_state['display_name']}")
    print(f"[RHYTHM] Focus: {rhythm_state['focus']}")
    print(f"[RHYTHM] Mood: {rhythm_state['mood']}")
    print(f"[RHYTHM] Quote: {rhythm_state['quote']}")
    
    if restart_info['is_imminent']:
        print(f"[RHYTHM] ⚠️ Server restart in {restart_info['minutes_to_restart']:.0f} minutes!")
    elif restart_info['is_preparation_time']:
        print(f"[RHYTHM] ⏰ Preparation phase: {restart_info['minutes_to_restart']:.0f} min to restart")
    
    if rhythm_state['recommended_tasks']:
        print(f"[RHYTHM] Recommended tasks: {len(rhythm_state['recommended_tasks'])}")
    
    if rhythm_state['actions']:
        print(f"[RHYTHM] Actions: {', '.join(rhythm_state['actions'])}")
    
    return rhythm_state

if __name__ == "__main__":
    update_rhythm_state()
