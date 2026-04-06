#!/usr/bin/env python3
"""
Goal Generator - 目标生成器
从日常目标池中生成具体可执行的目标
"""
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

class GoalGenerator:
    """目标生成器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.state = self._load_state()
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "daily_goals.json"
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _load_state(self):
        """加载状态"""
        state_path = AGENT_DIR / "system" / "goal_generator_state.json"
        if state_path.exists():
            with open(state_path, 'r') as f:
                return json.load(f)
        return {
            "today_goals": [],
            "last_goal_time": None,
            "goal_history": [],
            "daily_stats": {}
        }
    
    def _save_state(self):
        """保存状态"""
        state_path = AGENT_DIR / "system" / "goal_generator_state.json"
        with open(state_path, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def _check_conditions(self, goal, current_state):
        """检查目标生成条件"""
        conditions = goal.get("conditions", {})
        
        # 检查最小空闲时间
        if "min_idle_time" in conditions:
            last_time = self.state.get("last_goal_time")
            if last_time:
                last = datetime.fromisoformat(last_time)
                min_interval = self._parse_time(conditions["min_idle_time"])
                if datetime.now() - last < min_interval:
                    return False
        
        # 检查每日最大次数
        if "max_per_day" in conditions:
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = sum(1 for g in self.state.get("today_goals", [])
                           if g.get("date") == today and g.get("id") == goal["id"])
            if today_count >= conditions["max_per_day"]:
                return False
        
        # 检查完成后任务数
        if "min_completed_tasks" in conditions:
            # 简化：检查finished队列
            try:
                from queue import TaskQueue
                queue = TaskQueue()
                finished = queue.get_finished()
                if len(finished) < conditions["min_completed_tasks"]:
                    return False
            except:
                pass
        
        # 检查是否在错误后
        if "when" in conditions and conditions["when"] == "after_error":
            # 检查最近是否有错误
            recent_errors = [g for g in self.state.get("today_goals", [])
                           if g.get("status") == "error"]
            if not recent_errors:
                return False
        
        return True
    
    def _parse_time(self, time_str):
        """解析时间字符串"""
        if time_str.endswith("m"):
            return timedelta(minutes=int(time_str[:-1]))
        elif time_str.endswith("h"):
            return timedelta(hours=int(time_str[:-1]))
        return timedelta(minutes=30)
    
    def should_generate_goal(self, current_state):
        """判断是否应该生成新目标"""
        if not self.config.get("enabled", True):
            return False
        
        rules = self.config.get("generation_rules", {})
        
        # 检查是否有运行中的任务
        if rules.get("no_goal_if_running") and current_state.get("running"):
            return False
        
        # 检查是否有待处理任务
        if rules.get("no_goal_if_pending"):
            try:
                from queue import TaskQueue
                queue = TaskQueue()
                if queue.get_pending():
                    return False
            except:
                pass
        
        # 检查最小间隔
        if rules.get("min_interval_between_goals") and self.state.get("last_goal_time"):
            last = datetime.fromisoformat(self.state["last_goal_time"])
            min_interval = self._parse_time(rules["min_interval_between_goals"])
            if datetime.now() - last < min_interval:
                return False
        
        return True
    
    def select_goal(self, current_state):
        """从目标池中选择目标"""
        goals = self.config.get("goals", [])
        
        # 过滤符合条件的目标
        eligible = [g for g in goals if self._check_conditions(g, current_state)]
        
        if not eligible:
            return None
        
        # 加权随机选择
        weights = [g.get("weight", 0.2) for g in eligible]
        selected = random.choices(eligible, weights=weights, k=1)[0]
        
        return selected
    
    def generate_task_from_goal(self, goal):
        """将目标转换为具体任务"""
        category = goal.get("category", "general")
        text = goal.get("text", "unknown goal")
        
        # 根据类别生成不同步骤
        steps_map = {
            "learning": ["find_resources", "study_materials", "take_notes", "summarize"],
            "maintenance": ["identify_issues", "fix_problems", "test_fixes", "document"],
            "reflection": ["review_history", "identify_patterns", "suggest_improvements"],
            "exploration": ["research_topic", "try_examples", "document_findings"],
            "optimization": ["measure_performance", "identify_bottlenecks", "implement_fixes", "verify"]
        }
        
        steps = steps_map.get(category, ["step1", "step2", "step3", "step4"])
        
        task = {
            "type": category,
            "goal": text,
            "priority": goal.get("priority", 3),
            "steps": steps,
            "source": f"daily_goal:{goal.get('id')}",
            "created": datetime.now().isoformat()
        }
        
        return task
    
    def generate(self, current_state=None):
        """
        主生成函数
        
        Returns:
            task or None
        """
        if current_state is None:
            current_state = {}
        
        if not self.should_generate_goal(current_state):
            return None
        
        goal = self.select_goal(current_state)
        if not goal:
            return None
        
        task = self.generate_task_from_goal(goal)
        
        # 记录
        self.state["today_goals"].append({
            "id": goal["id"],
            "text": goal["text"],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().isoformat(),
            "task_id": task.get("task_id", "pending")
        })
        self.state["last_goal_time"] = datetime.now().isoformat()
        self._save_state()
        
        return task
    
    def get_stats(self):
        """获取统计信息"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_goals = [g for g in self.state.get("today_goals", []) if g.get("date") == today]
        
        return {
            "today_count": len(today_goals),
            "max_per_day": self.config.get("max_goals_per_day", 3),
            "last_goal": self.state.get("last_goal_time"),
            "available_goals": len(self.config.get("goals", []))
        }

if __name__ == "__main__":
    generator = GoalGenerator()
    
    print("=== Goal Generator Test ===")
    print(f"Enabled: {generator.config.get('enabled')}")
    print(f"Stats: {generator.get_stats()}")
    
    # 测试生成
    task = generator.generate()
    if task:
        print(f"\n✅ Generated task:")
        print(f"  Goal: {task['goal']}")
        print(f"  Type: {task['type']}")
        print(f"  Steps: {task['steps']}")
    else:
        print("\n❌ No goal generated (conditions not met)")
