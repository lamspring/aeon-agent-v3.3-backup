#!/usr/bin/env python3
"""
Agent Heartbeat - v14.0 生活节律版

Growth Loop + Life Rhythm:
  Perception → Life Rhythm → Goal Generation → Planning → Action → Reflection → Memory

像人一样有生活规律:
  早晨(6-12): 学习研究
  下午(12-18): 执行任务  
  晚上(18-23): 反思总结
  深夜(23-6): 休息
"""
import json
import sys
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR / "tasks"))
sys.path.insert(0, str(AGENT_DIR))

from queue import TaskQueue
from worker import TaskWorker

# 简化日志
from system.simple_logger import log as file_log

def log(msg):
    timestamp = f"[{datetime.now().strftime('%H:%M:%S')}]"
    print(f"{timestamp} {msg}")
    # 同时写入文件
    file_log(msg)

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

# ==================== Main Loop ====================
def heartbeat():
    """
    心跳主循环 - 成长循环版
    Perception → Goal Generation → Planning → Action → Reflection → Memory
    """
    log("=" * 60)
    log("[HEARTBEAT] Growth Loop v13.0")
    log("=" * 60)
    
    # ========================================
    # [1] PERCEPTION - 感知
    # ========================================
    log("[1/7] Perception - 感知当前状态...")
    from system.perception import Perception
    perception = Perception()
    perceived_state = perception.perceive()
    
    log(f"  System: {perceived_state['system_state'].get('gate', 'unknown')}")
    log(f"  Tasks: {perceived_state['task_state'].get('pending_count', 0)} pending, " + 
        f"running={perceived_state['task_state'].get('has_running', False)}")
    log(f"  Resources: API {perceived_state['resource_state'].get('api_calls_last_hour', 0)}/100")
    log(f"  📋 {perception.summarize()}")
    
    # [2/7] Gate Check - 门控检查
    log("[2/7] Gate Check...")
    gate = read_json(AGENT_DIR / "system" / "gate.json")
    if not gate.get("agent_enabled"):
        log("[GATE] ❌ Closed - 仅响应用户消息")
        return {"status": "blocked"}
    log("[GATE] ✅ Open")
    
    # [2.5/7] Life Rhythm - 生活节律
    log("[2.5/7] Life Rhythm - 生活节律...")
    from system.life_rhythm import LifeRhythm
    rhythm = LifeRhythm()
    current_cycle = rhythm.get_current_cycle()
    
    log(f"  🌅 当前: {current_cycle['display_name']}")
    log(f"  📝 焦点: {current_cycle['description']}")
    log(f"  💭 心境: {current_cycle['mood']}")
    log(f'  💬 格言: "{current_cycle["quote"]}"')
    
    # 检查特殊阶段
    special = rhythm.is_special_phase()
    if special and special.get("is_preparation_phase"):
        log("⚠️  [SPECIAL] 进入准备重启阶段 (2:00-4:00)")
        log("💾 [SPECIAL] 保存所有状态...")
        
        # 保存任务队列状态
        queue = TaskQueue()
        if queue.has_running_task():
            running = queue.get_running()
            log(f"💾 [SAVE] 保存运行中任务: {running['task_id'][:20]}...")
            # 标记为待恢复
            running['pre_restart_save'] = True
            running['saved_at'] = datetime.now().isoformat()
            write_json(AGENT_DIR / "tasks" / "queue" / "running.json", running)
        
        # 保存系统状态
        state = read_json(AGENT_DIR / "system" / "state.json")
        state['pre_restart_checkpoint'] = {
            'time': datetime.now().isoformat(),
            'pending_tasks': len(queue.get_pending()),
            'has_running': queue.has_running_task()
        }
        write_json(AGENT_DIR / "system" / "state.json", state)
        
        # 记录到日记
        diary_file = AGENT_DIR / "memory" / "diary.md"
        with open(diary_file, 'a') as f:
            f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n服务器即将重启(4:00)，已保存所有状态。\n")
        
        log("💾 [SPECIAL] 状态保存完成，准备休眠...")
        log("🌙 [SPECIAL] 等待服务器重启...")
        return {"status": "pre_restart_saved"}
    
    elif special and special.get("is_recovery_phase"):
        log("🔄 [SPECIAL] 服务器重启后恢复阶段 (4:00-6:00)")
        log("🔄 [SPECIAL] 检查系统状态...")
        
        # 检查是否有中断的任务需要恢复
        state = read_json(AGENT_DIR / "system" / "state.json")
        checkpoint = state.get('pre_restart_checkpoint')
        
        if checkpoint:
            log(f"🔄 [RECOVER] 发现重启前检查点: {checkpoint['time']}")
            log(f"🔄 [RECOVER] 待恢复任务: {checkpoint.get('pending_tasks', 0)} pending")
            
            # 记录恢复
            with open(AGENT_DIR / "memory" / "diary.md", 'a') as f:
                f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n服务器已重启，正在恢复状态。\n")
            
            # 清除检查点
            state.pop('pre_restart_checkpoint', None)
            write_json(AGENT_DIR / "system" / "state.json", state)
            
            log("🔄 [RECOVER] 状态恢复完成")
        else:
            log("🔄 [RECOVER] 没有需要恢复的状态")
    
    # ========================================
    # [3] GOAL GENERATION - 目标生成 (考虑生活节律)
    # ========================================
    log("[3/7] Goal Generation - 目标生成...")
    
    queue = TaskQueue()
    has_running = queue.has_running_task()
    pending_count = len(queue.get_pending())
    
    # 如果没有任务在运行，也没有待处理任务，生成新目标
    if not has_running and pending_count == 0:
        # 根据生活节律选择生成策略
        focus = rhythm.get_focus()
        log(f"[GOAL] 没有活跃任务，当前节律: {focus}")
        
        if focus == "research_learning":
            # 早晨：优先学习和研究
            log("[GOAL] 🌅 晨间模式 - 优先学习研究类任务")
            from system.goal_generator import GoalGenerator
            goal_gen = GoalGenerator()
            new_task = goal_gen.generate(current_state=perceived_state)
            
            if not new_task:
                # 日常目标未生成，尝试好奇心（学习类）
                log("[GOAL] ℹ️ 日常目标未生成，尝试好奇心...")
                from system.curiosity_trigger import CuriosityTrigger
                curiosity = CuriosityTrigger()
                should_trigger, reason = curiosity.should_trigger(perceived_state['task_state'])
                if should_trigger:
                    new_task = curiosity.generate_curiosity_task()
            
        elif focus == "execute_tasks":
            # 下午：优先执行任务
            log("[GOAL] ☀️ 工作模式 - 优先执行任务")
            # 检查是否有待执行的日常任务
            from system.goal_generator import GoalGenerator
            goal_gen = GoalGenerator()
            new_task = goal_gen.generate(current_state=perceived_state)
            
        elif focus == "reflection_summarizing":
            # 晚上：优先反思和总结
            log("[GOAL] 🌙 反思模式 - 优先复盘总结")
            # 生成反思类任务
            new_task = {
                "task_id": f"reflection_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "goal": "复盘今天的工作和学习",
                "type": "reflection",
                "category": "evening_reflection",
                "priority": 4,
                "steps": ["review_completed_tasks", "check_diary", "summarize_lessons", "plan_tomorrow"],
                "created_at": datetime.now().isoformat(),
                "source": "life_rhythm_evening"
            }
            log(f"[GOAL] 🌙 生成晚间反思任务")
            
        else:
            # 其他情况：默认行为
            log("[GOAL] 没有活跃任务，从日常目标生成...")
            from system.goal_generator import GoalGenerator
            goal_gen = GoalGenerator()
            new_task = goal_gen.generate(current_state=perceived_state)
        
        if new_task:
            log(f"[GOAL] ✅ 生成新目标: {new_task['goal'][:50]}...")
            log(f"[GOAL] 类型: {new_task['type']}, 优先级: {new_task['priority']}")
            
            # 添加到队列
            queue.add_task(new_task)
            log(f"[GOAL] 已加入任务队列")
        else:
            log("[GOAL] ℹ️ 条件不满足，暂不生成目标")
            
        # 继续执行，让下次心跳处理这个新任务
    else:
        log(f"[GOAL] ℹ️ 已有任务在进行中，跳过目标生成")
    
    # ========================================
    # [4] PLANNING - 规划
    # ========================================
    log("[4/7] Planning - 规划...")
    
    if not queue.has_running_task():
        # 没有运行任务，从pending取
        task = queue.pop_next_task()
        if task:
            log(f"[PLAN] 从队列取出: {task['task_id'][:20]}...")
            log(f"[PLAN] 目标: {task['goal'][:40]}...")
            log(f"[PLAN] 步骤: {task.get('steps', ['step1', 'step2', 'step3', 'step4'])}")
            queue.set_running(task)
        else:
            log("[PLAN] 队列为空，本次心跳无任务执行")
            log("[HEARTBEAT] Complete (idle)")
            return {"status": "idle"}
    
    running = queue.get_running()
    current_step = running.get('current_step', 0)
    total_steps = running.get('total_steps', 4)
    
    log(f"[PLAN] 当前任务: {running['task_id'][:20]}...")
    log(f"[PLAN] 进度: Step {current_step+1}/{total_steps}")
    
    # [5/7] ACTION - 执行
    log("[5/7] Action - 执行...")
    worker = TaskWorker()
    
    # 执行一步
    step_result = worker.execute_step(current_step)
    log(f"[ACTION] ✅ Step {current_step+1} completed")
    
    # 更新进度
    running['current_step'] = current_step + 1
    running['progress'] = (current_step + 1) / total_steps
    write_json(AGENT_DIR / "tasks" / "queue" / "running.json", running)
    
    # 检查是否完成
    if running['current_step'] >= total_steps:
        log("[ACTION] Task completed!")
        queue.move_to_finished(running, status="done")
        
        # 更新状态
        state = read_json(AGENT_DIR / "system" / "state.json")
        state['state'] = "idle"
        write_json(AGENT_DIR / "system" / "state.json", state)
    
    # ========================================
    # [6] REFLECTION - 反思
    # ========================================
    log("[6/7] Reflection - 反思...")
    from system.reflection_engine import ReflectionEngine
    
    reflection = ReflectionEngine()
    should_reflect, trigger_reason = reflection.should_reflect(running, {"finished": running['current_step'] >= total_steps})
    
    if should_reflect:
        log(f"[REFLECTION] 触发: {trigger_reason}")
        
        reflection_result = reflection.reflect_and_spawn(
            task=running,
            current_step=current_step,
            step_result=step_result,
            running_state=running,
            queue_manager=queue
        )
        
        log(f"[REFLECTION] 决策: {reflection_result['decision']}")
        log(f"[REFLECTION] 行动: {reflection_result['action'][:50]}...")
        
        # 记录反思
        progress_info = f"step {current_step+1}/{total_steps}"
        reflection.log_reflection(
            running['task_id'],
            current_step + 1,
            f"step{current_step+1}",
            progress_info,
            reflection_result
        )
        
        # 记录经验教训到日记
        if reflection_result.get('lesson'):
            diary_file = AGENT_DIR / "memory" / "diary.md"
            with open(diary_file, 'a') as f:
                f.write(f"\n- {reflection_result['lesson']}\n")
            log(f"[REFLECTION] 经验教训已记录: {reflection_result['lesson'][:40]}...")
        
        # 应用决策
        running, should_continue = reflection.apply_decision(
            reflection_result['decision'],
            running,
            queue
        )
        
        if not should_continue:
            log("[REFLECTION] 任务已停止")
    else:
        log("[REFLECTION] 跳过 (未触发)")
    
    # ========================================
    # [7] MEMORY UPDATE - 记忆更新
    # ========================================
    log("[7/7] Memory Update - 记忆更新...")
    
    # 写入思维流
    thoughts_file = AGENT_DIR / "memory" / "inner_thoughts.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    entry = f"""
---
time: {timestamp}
goal: {running.get('goal', 'unknown')[:50]}
action: step {current_step+1} execution
result: {step_result.get('status', 'unknown')}
reflection: {reflection_result.get('decision', 'none') if should_reflect else 'skipped'}
state: {perception.summarize()}
---
"""
    with open(thoughts_file, 'a') as f:
        f.write(entry)
    
    log("[MEMORY] ✅ 思维流已更新")
    
    # ========================================
    # SLEEP
    # ========================================
    log("=" * 60)
    log("[HEARTBEAT] Complete → Sleep 💤")
    log("=" * 60)
    
    return {"status": "ok"}

if __name__ == "__main__":
    result = heartbeat()
    print(f"\nResult: {result}")
