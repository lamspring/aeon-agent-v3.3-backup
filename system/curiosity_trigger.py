#!/usr/bin/env python3
"""
Curiosity Trigger - 好奇心触发器

当系统空闲时，主动探索新事物
触发条件：
  - 任务队列为空
  - 没有运行中的任务
  - 距离上次好奇心任务超过5分钟

好奇心任务池:
  - search_new_tools: 搜索新工具
  - review_old_tasks: 复盘旧任务
  - optimize_code: 优化代码
  - explore_topic: 探索话题
  - learn_technology: 学习技术
"""
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

class CuriosityTrigger:
    """好奇心触发器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.state = self._load_state()
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "curiosity_tasks.json"
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _load_state(self):
        """加载状态"""
        state_path = AGENT_DIR / "system" / "curiosity_state.json"
        if state_path.exists():
            with open(state_path, 'r') as f:
                return json.load(f)
        return {
            "today_count": 0,
            "last_trigger": None,
            "history": []
        }
    
    def _save_state(self):
        """保存状态"""
        state_path = AGENT_DIR / "system" / "curiosity_state.json"
        with open(state_path, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _is_new_day(self):
        """检查是否是新的一天"""
        if not self.state["last_trigger"]:
            return True
        last = datetime.fromisoformat(self.state["last_trigger"])
        now = datetime.now()
        return last.date() != now.date()
    
    def _can_trigger(self):
        """检查是否可以触发好奇心"""
        if not self.config.get("enabled", True):
            return False, "disabled"
        
        # 检查每日任务上限 (新限制)
        max_per_day = self.config.get("max_tasks_per_day", 20)
        if self.state.get("today_count", 0) >= max_per_day:
            return False, f"daily_task_limit_reached ({max_per_day})"
        
        # 检查每小时LLM调用上限 (新限制)
        max_llm_per_hour = self.config.get("max_llm_calls_per_hour", 30)
        llm_calls_last_hour = self._count_llm_calls_last_hour()
        if llm_calls_last_hour >= max_llm_per_hour:
            return False, f"hourly_llm_limit_reached ({max_llm_per_hour})"
        
        # 检查时间间隔
        min_interval = self.config.get("min_idle_time_before_trigger", "5m")
        minutes = int(min_interval.rstrip('m'))
        
        if self.state.get("last_trigger"):
            last = datetime.fromisoformat(self.state["last_trigger"])
            if datetime.now() - last < timedelta(minutes=minutes):
                return False, "too_soon"
        
        return True, "ok"
    
    def _count_llm_calls_last_hour(self):
        """统计最近一小时的LLM调用次数"""
        # 从简化日志中统计
        log_path = AGENT_DIR / "logs" / "execution_log.txt"
        if not log_path.exists():
            return 0
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        count = 0
        
        try:
            with open(log_path, 'r') as f:
                for line in f:
                    if '[LLM]' in line or 'LLM call' in line or 'api call' in line.lower():
                        # 尝试解析时间戳
                        if line.startswith('['):
                            try:
                                timestamp_str = line[1:20]  # [2026-04-05 20:48:04]
                                ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                if ts > one_hour_ago:
                                    count += 1
                            except:
                                pass
        except:
            pass
        
        return count
    
    def should_trigger(self, task_state):
        """
        判断是否应该触发好奇心
        
        Args:
            task_state: dict with pending_count, has_running
        
        Returns:
            (should_trigger, reason)
        """
        can_trigger, reason = self._can_trigger()
        if not can_trigger:
            return False, reason
        
        # 检查是否空闲
        if task_state.get("has_running"):
            return False, "task_running"
        
        if task_state.get("pending_count", 0) > 0:
            return False, "tasks_pending"
        
        return True, "idle_and_ready"
    
    def _weighted_choice(self, tasks):
        """加权随机选择"""
        weights = [t.get("weight", 1.0) for t in tasks]
        total = sum(weights)
        weights = [w / total for w in weights]
        
        return random.choices(tasks, weights=weights, k=1)[0]
    
    def _fill_template(self, task_template):
        """填充任务模板中的变量"""
        task = task_template.copy()
        
        # 如果topics存在，随机选择一个
        if "topics" in task:
            task["selected_topic"] = random.choice(task["topics"])
            task["text"] = f"{task['text']}: {task['selected_topic']}"
        
        # 如果technologies存在，随机选择一个
        if "technologies" in task:
            task["selected_tech"] = random.choice(task["technologies"])
            task["text"] = f"{task['text']}: {task['selected_tech']}"
        
        # 如果search_keywords存在，随机选择一个
        if "search_keywords" in task:
            task["search_query"] = random.choice(task["search_keywords"])
        
        return task
    
    def generate_curiosity_task(self):
        """
        生成好奇心任务
        
        Returns:
            task dict or None
        """
        can_trigger, reason = self._can_trigger()
        if not can_trigger:
            return None
        
        tasks = self.config.get("curiosity_tasks", [])
        if not tasks:
            return None
        
        # 加权随机选择
        selected = self._weighted_choice(tasks)
        
        # 填充变量
        filled = self._fill_template(selected)
        
        # 构建任务
        task = {
            "task_id": f"curiosity_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "goal": filled["text"],
            "type": filled["category"],
            "category": "curiosity",
            "priority": 3,
            "steps": filled.get("steps", ["explore", "document"]),
            "curiosity_id": filled["id"],
            "curiosity_details": {
                "description": filled.get("description", ""),
                "selected_topic": filled.get("selected_topic"),
                "selected_tech": filled.get("selected_tech"),
                "search_query": filled.get("search_query")
            },
            "created_at": datetime.now().isoformat(),
            "source": "curiosity_trigger"
        }
        
        # 更新状态
        if self._is_new_day():
            self.state["today_count"] = 0
            self.state["llm_calls_today"] = 0
        
        self.state["today_count"] = self.state.get("today_count", 0) + 1
        self.state["last_trigger"] = datetime.now().isoformat()
        self.state["history"].append({
            "timestamp": task["created_at"],
            "task_id": task["task_id"],
            "goal": task["goal"]
        })
        self._save_state()
        
        # 记录LLM调用到日志
        from system.simple_logger import log
        log(f"[LLM] Curiosity task generated: {task['task_id']}")
        
        return task
    
    def get_stats(self):
        """获取统计信息"""
        llm_last_hour = self._count_llm_calls_last_hour()
        return {
            "today_count": self.state.get("today_count", 0),
            "max_tasks_per_day": self.config.get("max_tasks_per_day", 20),
            "llm_calls_last_hour": llm_last_hour,
            "max_llm_per_hour": self.config.get("max_llm_calls_per_hour", 30),
            "last_trigger": self.state.get("last_trigger"),
            "total_history": len(self.state.get("history", [])),
            "available_tasks": len(self.config.get("curiosity_tasks", []))
        }

if __name__ == "__main__":
    print("=== Curiosity Trigger Test ===\n")
    
    trigger = CuriosityTrigger()
    
    print(f"Stats: {trigger.get_stats()}")
    print(f"\nConfig enabled: {trigger.config.get('enabled')}")
    print(f"Available tasks: {len(trigger.config.get('curiosity_tasks', []))}")
    
    # 测试空闲状态
    idle_state = {"pending_count": 0, "has_running": False}
    should, reason = trigger.should_trigger(idle_state)
    print(f"\nIdle state → should_trigger: {should}, reason: {reason}")
    
    # 测试忙碌状态
    busy_state = {"pending_count": 2, "has_running": True}
    should, reason = trigger.should_trigger(busy_state)
    print(f"Busy state → should_trigger: {should}, reason: {reason}")
    
    # 生成任务
    print("\n--- Generating Curiosity Task ---")
    task = trigger.generate_curiosity_task()
    if task:
        print(f"✅ Generated: {task['goal']}")
        print(f"   Type: {task['type']}")
        print(f"   Steps: {task['steps']}")
        if task['curiosity_details'].get('selected_topic'):
            print(f"   Topic: {task['curiosity_details']['selected_topic']}")
        if task['curiosity_details'].get('search_query'):
            print(f"   Search: {task['curiosity_details']['search_query']}")
    else:
        print("❌ No task generated")
    
    print(f"\nUpdated stats: {trigger.get_stats()}")
