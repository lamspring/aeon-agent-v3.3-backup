#!/usr/bin/env python3
"""
Self-Reflection Engine - 自我反思引擎

反馈循环：
  任务执行 → 结果评估 → 反思总结 → 调整策略 → 继续任务

三种决策：
  continue - 继续当前任务
  adjust   - 调整策略/重新规划
  stop     - 终止任务

触发时机：
  - 任务完成
  - 任务卡住/超时
  - 每N次心跳
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

class ReflectionEngine:
    """自我反思引擎"""
    
    def __init__(self):
        self.config = read_json(AGENT_DIR / "system" / "reflection.json")
        self.counter = self._load_counter()
    
    def _load_counter(self):
        """加载心跳计数器"""
        counter_file = AGENT_DIR / "system" / "reflection_counter.json"
        if counter_file.exists():
            return read_json(counter_file)
        return {"heartbeat_count": 0, "last_reflection": None}
    
    def _save_counter(self):
        """保存心跳计数器"""
        counter_file = AGENT_DIR / "system" / "reflection_counter.json"
        write_json(counter_file, self.counter)
    
    def _save_experience(self, task, decision, progress_status, strategy_status):
        """
        保存经验到长期记忆
        反思时自动调用
        """
        experiences_path = AGENT_DIR / "memory" / "experiences.json"
        
        # 读取现有经验
        try:
            with open(experiences_path, 'r') as f:
                data = json.load(f)
        except:
            data = {
                "experiences": [],
                "lessons_learned": [],
                "success_patterns": [],
                "failure_patterns": []
            }
        
        # 构建经验记录
        experience = {
            "timestamp": datetime.now().isoformat(),
            "task": task.get('goal', 'unknown')[:100],
            "task_type": task.get('type', 'unknown'),
            "result": "successful" if decision == "continue" else "needs_improvement" if decision == "adjust" else "failed",
            "decision": decision,
            "progress_status": progress_status,
            "strategy_status": strategy_status,
            "lesson": self._generate_lesson(decision, progress_status, strategy_status)
        }
        
        # 添加到经验列表
        data["experiences"].append(experience)
        
        # 提取教训
        if experience["lesson"]:
            data["lessons_learned"].append({
                "timestamp": experience["timestamp"],
                "lesson": experience["lesson"],
                "context": experience["task"][:50]
            })
        
        # 记录成功/失败模式
        if decision == "continue" and progress_status == "good":
            data["success_patterns"].append({
                "timestamp": experience["timestamp"],
                "pattern": f"{task.get('type')} task with good progress",
                "factors": ["effective_strategy", "clear_goal"]
            })
        elif decision == "stop" or progress_status == "stuck":
            data["failure_patterns"].append({
                "timestamp": experience["timestamp"],
                "pattern": f"{task.get('type')} task stuck or failed",
                "factors": [strategy_status]
            })
        
        # 只保留最近100条经验
        data["experiences"] = data["experiences"][-100:]
        data["lessons_learned"] = data["lessons_learned"][-50:]
        
        # 保存
        with open(experiences_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return experience
    
    def _generate_lesson(self, decision, progress_status, strategy_status):
        """从反思中生成教训"""
        lessons = {
            ("continue", "good", "effective"): "清晰的目标 + 有效的策略 = 成功",
            ("continue", "moderate", "effective"): "稳步推进，保持当前节奏",
            ("adjust", "moderate", "needs_adjustment"): "策略需要微调，及时发现问题很重要",
            ("adjust", "slow", "struggling"): "遇到困难时应该尽早调整策略",
            ("stop", "stuck", "failing"): "反复失败后应该果断停止，避免资源浪费",
        }
        
        key = (decision, progress_status, strategy_status)
        return lessons.get(key, "")
    
    def should_reflect(self, running_task, action_result):
        """
        判断是否应该触发反思
        
        Returns:
            (should_reflect, trigger_reason)
        """
        if not self.config.get("enabled", True):
            return False, "disabled"
        
        triggers = self.config.get("trigger_on", {})
        
        # 1. 任务完成
        if triggers.get("task_complete") and action_result.get("finished"):
            return True, "task_complete"
        
        # 2. 任务卡住/超时
        if triggers.get("task_stuck") and action_result.get("timeout"):
            return True, "task_stuck"
        
        # 3. 每N次心跳
        n = triggers.get("every_n_heartbeats", 4)
        self.counter["heartbeat_count"] += 1
        self._save_counter()
        
        if self.counter["heartbeat_count"] >= n:
            self.counter["heartbeat_count"] = 0
            self._save_counter()
            return True, f"every_{n}_heartbeats"
        
        return False, "not_triggered"
    
    def reflect_and_spawn(self, task, current_step, step_result, running_state, queue_manager):
        """
        执行反思，可能产生子任务，保存经验
        
        Returns:
            {
                "decision": "continue" | "adjust" | "stop",
                "evaluation": "评估内容",
                "action": "具体行动描述",
                "spawned_tasks": [],
                "experience_saved": bool
            }
        """
        progress = running_state.get("progress", 0)
        retry_count = running_state.get("retry_count", 0)
        total_steps = running_state.get("total_steps", 4)
        spawned_tasks = []
        
        # === 问题1: 任务进展是否正常 ===
        if progress >= 0.75:
            progress_status = "good"
            progress_detail = "接近完成，进展顺利"
        elif progress >= 0.5:
            progress_status = "moderate"
            progress_detail = "过半完成，稳步推进"
        elif progress >= 0.25:
            progress_status = "slow"
            progress_detail = "进展较慢，需要关注"
        else:
            progress_status = "stuck"
            progress_detail = "进展停滞，需要调整"
        
        # === 问题2: 当前策略是否有效 ===
        if retry_count == 0:
            strategy_status = "effective"
            strategy_detail = "首次执行，策略有效"
        elif retry_count == 1:
            strategy_status = "needs_adjustment"
            strategy_detail = "首次重试，策略需微调"
        elif retry_count == 2:
            strategy_status = "struggling"
            strategy_detail = "多次重试，策略需要较大调整"
        else:
            strategy_status = "failing"
            strategy_detail = "反复失败，策略完全无效"
        
        # === 问题3: 决策 (continue/adjust/stop) + 可能产生子任务 ===
        if retry_count >= 3:
            decision = "stop"
            decision_reason = "已达最大重试次数，终止任务避免资源浪费"
            action = f"终止任务: {task.get('goal', 'unknown')}"
        elif retry_count >= 1 or progress_status == "stuck":
            decision = "adjust"
            decision_reason = "策略需要调整，重新规划执行方式"
            action = f"调整策略: 重置到step 1，第{retry_count + 1}次尝试"
            
            # 如果任务复杂，产生子任务
            if task.get("type") in ["research", "explore", "build"]:
                subtask_goal = f"深入分析: {task.get('goal', 'unknown')} - 找出失败原因"
                subtask = queue_manager.spawn_subtask(task, subtask_goal, "analysis")
                if subtask:
                    spawned_tasks.append(subtask)
                    action += f" (已产生子任务: {subtask['task_id']})"
        else:
            decision = "continue"
            decision_reason = "进展正常，继续执行"
            next_step = min(current_step + 1, total_steps - 1)
            action = f"继续执行: 进入step {next_step + 1}"
            
            # 如果完成了一大步，产生后续子任务
            if current_step == 1 and task.get("type") == "research":
                subtask_goal = f"整理并验证: {task.get('goal', 'unknown')} 的研究结果"
                subtask = queue_manager.spawn_subtask(task, subtask_goal, "validation")
                if subtask:
                    spawned_tasks.append(subtask)
                    action += f" (已产生验证子任务)"
        
        # 构建详细评估
        evaluation = f"""【进展评估】{progress_status} - {progress_detail}
【策略评估】{strategy_status} - {strategy_detail}
【决策理由】{decision_reason}"""
        
        # === 保存经验到长期记忆 ===
        experience = self._save_experience(task, decision, progress_status, strategy_status)
        
        result = {
            "decision": decision,
            "evaluation": evaluation,
            "action": action,
            "progress_status": progress_status,
            "strategy_status": strategy_status,
            "spawned_tasks": spawned_tasks,
            "experience_saved": True,
            "lesson": experience.get("lesson", "")
        }
        
        return result
    
    def log_reflection(self, task_id, step, step_name, progress_info, reflection_result):
        """记录反思到日志 - 详细格式"""
        log_file = AGENT_DIR / "logs" / "reflection_log.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 格式化evaluation，确保多行内容正确缩进
        evaluation = reflection_result['evaluation'].replace('\n', '\n  ')
        
        # 如果有经验教训，也记录下来
        lesson_note = ""
        if reflection_result.get("lesson"):
            lesson_note = f"\nlesson: {reflection_result['lesson']}\n"
        
        entry = f"""\n---\ntime: {timestamp}\ntask: {task_id}\n\nprogress:\nstep {step} completed: {step_name} ({progress_info})\n\nevaluation:\n  {evaluation}{lesson_note}\ndecision: {reflection_result['decision']}\naction: {reflection_result['action']}\n---\n"""
        
        with open(log_file, 'a') as f:
            f.write(entry)
    
    def apply_decision(self, decision, running_task, queue_manager):
        """
        应用反思决策
        
        Returns:
            new_state, should_continue
        """
        if decision == "continue":
            # 继续执行，不改变任何东西
            return running_task, True
        
        elif decision == "adjust":
            # 调整策略：增加重试计数，但继续
            running_task["retry_count"] = running_task.get("retry_count", 0) + 1
            running_task["last_adjustment"] = datetime.now().isoformat()
            write_json(AGENT_DIR / "tasks" / "queue" / "running.json", running_task)
            return running_task, True
        
        elif decision == "stop":
            # 停止任务：移动到finished，标记为error
            queue_manager.move_to_finished(running_task, status="error")
            return None, False
        
        return running_task, True

if __name__ == "__main__":
    print("=== Reflection Engine Test ===")
    
    engine = ReflectionEngine()
    print(f"Enabled: {engine.config.get('enabled')}")
    print(f"Triggers: {engine.config.get('trigger_on')}")
    
    # 测试触发判断
    test_task = {"task_id": "test_001"}
    should, reason = engine.should_reflect(test_task, {"finished": True})
    print(f"\nTask complete → reflect: {should}, reason: {reason}")
    
    should, reason = engine.should_reflect(test_task, {"finished": False})
    print(f"Task running → reflect: {should}, reason: {reason}")
