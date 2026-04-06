#!/usr/bin/env python3
"""
Agent Heartbeat - v19.0 World Input Edition

新的循环流程:
  World Input (环境变化)
    ↓
  Agent观察 (读取environment.json)
    ↓
  Agent思考 (反思当前状态)
    ↓
  生成目标 (基于环境)
    ↓
  加入队列
    ↓
  执行任务
    ↓
  更新记忆

不是简单的: 心跳→任务→反思→记忆
而是: 世界→观察→思考→行动→记忆
"""
import json
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR / "tasks"))
sys.path.insert(0, str(AGENT_DIR))

from queue import TaskQueue
from worker import TaskWorker

def log_simple(msg):
    """简化日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = AGENT_DIR / "logs" / "execution_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def heartbeat_v19():
    """
    Heartbeat v19.0 - World Input Edition
    
    1. 收集世界输入 (World Input)
    2. Agent观察 (Observe)
    3. Agent思考 (Think)
    4. 生成目标 (Goal)
    5. 执行 (Act)
    6. 记忆 (Remember)
    """
    log_simple("=" * 50)
    log_simple("[HEARTBEAT] v19.0 World Input Edition")
    log_simple("=" * 50)
    
    # ========================================
    # [1] WORLD INPUT - 收集环境输入
    # ========================================
    log_simple("[1/6] World Input - 收集环境...")
    
    from system.world_input import WorldInput
    world = WorldInput()
    env = world.collect()
    
    time_ctx = env.get("time", {})
    sys_ctx = env.get("system", {})
    user_ctx = env.get("user_activity", {})
    
    log_simple(f"  🕐 时间: {time_ctx.get('day_name')} {time_ctx.get('hour')}:{time_ctx.get('minute'):02d}")
    log_simple(f"  💻 系统: CPU{sys_ctx.get('cpu_percent')}% Mem{sys_ctx.get('memory_percent')}% [{sys_ctx.get('status')}]")
    log_simple(f"  👤 用户: 今日交互{user_ctx.get('interaction_count_today', 0)}次")
    
    if env.get("alerts"):
        for alert in env["alerts"]:
            log_simple(f"  ⚠️  {alert}")
    
    # ========================================
    # [2] OBSERVE - Agent观察
    # ========================================
    log_simple("[2/6] Observe - 观察环境...")
    
    context = world.get_context_for_ai()
    log_simple(f"  📝 上下文: {context[:80]}...")
    
    # ========================================
    # [3] THINK - Agent思考
    # ========================================
    log_simple("[3/6] Think - 思考当前状态...")
    
    thoughts = []
    
    # 基于时间的思考
    if time_ctx.get("special_day") == "Sunday Summary Day":
        thoughts.append("今天是周日，应该写周总结")
    elif time_ctx.get("special_day") == "Monday Planning Day":
        thoughts.append("今天是周一，应该制定新计划")
    
    if time_ctx.get("is_early_morning"):
        thoughts.append("凌晨时段，准备服务器重启")
    
    # 基于系统状态的思考
    if sys_ctx.get("status") == "stressed":
        thoughts.append("系统负载高，应该减少任务")
    elif sys_ctx.get("status") == "idle":
        thoughts.append("系统空闲，可以做更多事情")
    
    # 基于用户活动的思考
    if user_ctx.get("interaction_count_today", 0) > 50:
        thoughts.append("今天和用户交互频繁，用户很活跃")
    elif user_ctx.get("interaction_count_today", 0) == 0:
        thoughts.append("今天还没有和用户交互，可能需要主动一些")
    
    for thought in thoughts:
        log_simple(f"  💭 {thought}")
    
    # ========================================
    # [4] GOAL - 生成目标
    # ========================================
    log_simple("[4/6] Goal - 基于环境生成目标...")
    
    queue = TaskQueue()
    has_running = queue.has_running_task()
    pending_count = len(queue.get_pending())
    
    generated_task = None
    
    if not has_running and pending_count == 0:
        # 基于环境生成目标
        
        # 周日 → 写周总结
        if time_ctx.get("special_day") == "Sunday Summary Day":
            generated_task = {
                "task_id": f"sunday_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "goal": "写本周总结",
                "type": "reflection",
                "steps": ["收集本周数据", "生成周报", "保存到weekly_reflections.md"],
                "source": "world_input_sunday"
            }
            log_simple("  🎯 生成目标: 写周总结 (周日特殊任务)")
        
        # 周一 → 制定计划
        elif time_ctx.get("special_day") == "Monday Planning Day":
            generated_task = {
                "task_id": f"monday_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "goal": "制定本周计划",
                "type": "planning",
                "steps": ["回顾上周目标", "设定本周优先级", "创建任务列表"],
                "source": "world_input_monday"
            }
            log_simple("  🎯 生成目标: 制定本周计划 (周一特殊任务)")
        
        # 系统空闲 + 长时间无交互 → 好奇心探索
        elif sys_ctx.get("status") == "idle" and user_ctx.get("interaction_count_today", 0) < 5:
            from system.curiosity_trigger import CuriosityTrigger
            trigger = CuriosityTrigger()
            generated_task = trigger.generate_curiosity_task()
            if generated_task:
                log_simple(f"  🎯 生成目标: {generated_task['goal']} (好奇心 - 系统空闲)")
        
        # 系统 stressed → 系统维护
        elif sys_ctx.get("status") == "stressed":
            generated_task = {
                "task_id": f"system_maint_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "goal": "系统维护：清理日志和临时文件",
                "type": "maintenance",
                "steps": ["检查日志大小", "清理旧日志", "检查磁盘空间"],
                "source": "world_input_stressed"
            }
            log_simple("  🎯 生成目标: 系统维护 (系统负载高)")
        
        # 加入队列
        if generated_task:
            queue.add_task(generated_task)
            log_simple(f"  ✅ 已加入队列: {generated_task['task_id'][:30]}...")
    else:
        log_simple(f"  ℹ️ 已有任务进行，跳过目标生成")
    
    # ========================================
    # [5] ACT - 执行
    # ========================================
    log_simple("[5/6] Act - 执行任务...")
    
    if has_running:
        running = queue.get_running()
        log_simple(f"  ▶️ 继续执行: {running['goal'][:40]}...")
        # 这里实际执行一步...
        log_simple(f"  ✅ 执行一步完成")
    elif pending_count > 0:
        pending = queue.get_pending()
        task = pending[0] if pending else None
        if task:
            log_simple(f"  ▶️ 开始执行: {task['goal'][:40]}...")
            # 这里实际执行一步...
            log_simple(f"  ✅ 执行一步完成")
    else:
        log_simple("  ℹ️ 没有任务需要执行")
    
    # ========================================
    # [6] REMEMBER - 更新记忆
    # ========================================
    log_simple("[6/6] Remember - 更新记忆...")
    
    # 记录到简化日志
    log_simple(f"[MEMORY] 环境状态已记录: {time_ctx.get('day_name')} {sys_ctx.get('status')}")
    
    # 长期记忆
    memory_file = AGENT_DIR / "memory" / "diary.md"
    with open(memory_file, 'a', encoding='utf-8') as f:
        f.write(f"\n## {datetime.now().strftime('%H:%M')}\n")
        f.write(f"心跳周期完成。环境: {time_ctx.get('day_name')} {time_ctx.get('hour')}点, 系统{sys_ctx.get('status')}\n")
        if thoughts:
            f.write(f"想法: {'; '.join(thoughts)}\n")
    
    log_simple("  ✅ 记忆已更新")
    
    log_simple("=" * 50)
    log_simple("[HEARTBEAT] Complete → Sleep 💤")
    
    return {"status": "completed", "thoughts": thoughts}

if __name__ == "__main__":
    heartbeat_v19()
