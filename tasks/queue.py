#!/usr/bin/env python3
"""
Task Queue - 任务队列管理
管理pending/running/finished三个队列
"""
import json
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

class TaskQueue:
    """任务队列管理器"""
    
    def __init__(self):
        self.queue_dir = AGENT_DIR / "tasks" / "queue"
    
    def get_pending(self):
        """获取待处理队列"""
        return read_json(self.queue_dir / "pending.json")
    
    def get_running(self):
        """获取正在运行的任务"""
        return read_json(self.queue_dir / "running.json")
    
    def get_finished(self):
        """获取已完成队列"""
        return read_json(self.queue_dir / "finished.json")
    
    def pop_next_task(self):
        """
        从pending队列取出最高优先级的任务
        返回: task or None
        """
        pending = self.get_pending()
        
        if not pending:
            return None
        
        # 按优先级排序 (5最高)
        pending.sort(key=lambda x: x.get("priority", 0), reverse=True)
        
        # 取出第一个
        task = pending.pop(0)
        
        # 保存更新后的pending
        write_json(self.queue_dir / "pending.json", pending)
        
        return task
    
    def add_task(self, task, parent_id=None):
        """添加任务到pending队列，支持任务树"""
        # 先检查限流
        from system.rate_limiter import RateLimiter
        limiter = RateLimiter()
        
        parent_depth = 0
        if parent_id:
            parent_depth = self._get_task_depth(parent_id)
        
        allowed, reason = limiter.check_task_creation(
            task.get("type", "generic"),
            parent_depth
        )
        
        if not allowed:
            print(f"[RATE_LIMIT] Task creation blocked: {reason}")
            return None
        
        pending = self.get_pending()
        
        # 确保任务有必要的字段
        if "task_id" not in task:
            from datetime import datetime
            task["task_id"] = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if "steps" not in task:
            task["steps"] = ["step1", "step2", "step3", "step4"]
        if "created" not in task:
            from datetime import datetime
            task["created"] = datetime.now().isoformat()
        
        # 任务树字段
        task["parent_id"] = parent_id
        task["children"] = []
        task["depth"] = 0 if parent_id is None else parent_depth + 1
        
        pending.append(task)
        write_json(self.queue_dir / "pending.json", pending)
        
        # 如果有父任务，更新父任务的children
        if parent_id:
            self._add_child_to_parent(parent_id, task["task_id"])
        
        return task
    
    def _get_task_depth(self, task_id):
        """获取任务深度"""
        # 在pending中查找
        for task in self.get_pending():
            if task.get("task_id") == task_id:
                return task.get("depth", 0)
        # 在running中查找
        running = self.get_running()
        if running.get("task_id") == task_id:
            return running.get("depth", 0)
        # 在finished中查找
        for task in self.get_finished():
            if task.get("task_id") == task_id:
                return task.get("depth", 0)
        return 0
    
    def _add_child_to_parent(self, parent_id, child_id):
        """添加子任务到父任务"""
        # 更新pending中的父任务
        pending = self.get_pending()
        for task in pending:
            if task.get("task_id") == parent_id:
                if "children" not in task:
                    task["children"] = []
                task["children"].append(child_id)
                write_json(self.queue_dir / "pending.json", pending)
                return
        
        # 更新running中的父任务
        running = self.get_running()
        if running.get("task_id") == parent_id:
            if "children" not in running:
                running["children"] = []
            running["children"].append(child_id)
            write_json(self.queue_dir / "running.json", running)
            return
        
        # 更新finished中的父任务
        finished = self.get_finished()
        for task in finished:
            if task.get("task_id") == parent_id:
                if "children" not in task:
                    task["children"] = []
                task["children"].append(child_id)
                write_json(self.queue_dir / "finished.json", finished)
                return
    
    def get_task_tree(self, root_task_id=None):
        """获取任务树结构"""
        all_tasks = {}
        
        # 收集所有任务
        for task in self.get_pending():
            all_tasks[task.get("task_id")] = task
        running = self.get_running()
        if running.get("task_id"):
            all_tasks[running["task_id"]] = running
        for task in self.get_finished():
            all_tasks[task.get("task_id")] = task
        
        if root_task_id and root_task_id in all_tasks:
            return self._build_tree_node(all_tasks, root_task_id)
        
        # 返回所有根任务
        roots = []
        for task_id, task in all_tasks.items():
            if not task.get("parent_id"):
                roots.append(self._build_tree_node(all_tasks, task_id))
        return roots
    
    def _build_tree_node(self, all_tasks, task_id, visited=None):
        """递归构建树节点"""
        if visited is None:
            visited = set()
        
        if task_id in visited or task_id not in all_tasks:
            return None
        
        visited.add(task_id)
        task = all_tasks[task_id]
        
        node = {
            "task_id": task_id,
            "goal": task.get("goal", "unknown"),
            "status": self._get_task_status(task),
            "depth": task.get("depth", 0),
            "children": []
        }
        
        for child_id in task.get("children", []):
            child_node = self._build_tree_node(all_tasks, child_id, visited)
            if child_node:
                node["children"].append(child_node)
        
        return node
    
    def _get_task_status(self, task):
        """获取任务状态"""
        if "status" in task:
            return task["status"]
        if task.get("task_id") == self.get_running().get("task_id"):
            return "running"
        return "pending"
    
    def spawn_subtask(self, parent_task, subtask_goal, subtask_type="subtask"):
        """从父任务产生子任务"""
        from datetime import datetime
        import time
        
        # 检查限流
        from system.rate_limiter import RateLimiter
        limiter = RateLimiter()
        allowed, reason = limiter.check_subtask_spawn(parent_task)
        
        if not allowed:
            print(f"[RATE_LIMIT] Subtask spawn blocked: {reason}")
            return None
        
        # 检查深度限制
        max_depth = 3
        try:
            config = read_json(AGENT_DIR / "system" / "task_tree.json")
            max_depth = config.get("max_depth", 3)
        except:
            pass
        
        current_depth = parent_task.get("depth", 0)
        if current_depth >= max_depth:
            print(f"[RATE_LIMIT] Max depth reached: {max_depth}")
            return None
        
        # 使用毫秒时间戳确保唯一性
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S') + f"_{int(time.time()*1000)%1000}"
        parent_short = parent_task['task_id'][:8]
        
        subtask = {
            "task_id": f"subtask_{timestamp}_{parent_short}",
            "type": subtask_type,
            "goal": subtask_goal,
            "priority": parent_task.get("priority", 2),
            "parent_id": parent_task["task_id"],
            "depth": current_depth + 1,
            "children": [],
            "created": datetime.now().isoformat(),
            "steps": ["step1", "step2", "step3", "step4"]
        }
        
        return self.add_task(subtask, parent_id=parent_task["task_id"])
    
    def print_task_tree(self, node=None, prefix="", is_last=True):
        """打印任务树"""
        if node is None:
            roots = self.get_task_tree()
            for i, root in enumerate(roots):
                self.print_task_tree(root, "", i == len(roots) - 1)
            return
        
        # 打印当前节点
        connector = "└── " if is_last else "├── "
        status_icon = {
            "pending": "⏳",
            "running": "▶️",
            "done": "✅",
            "error": "❌"
        }.get(node["status"], "⚪")
        
        indent = "    " if is_last else "│   "
        print(f"{prefix}{connector}{status_icon} {node['goal']}")
        
        # 打印子节点
        children = node.get("children", [])
        for i, child in enumerate(children):
            self.print_task_tree(child, prefix + indent, i == len(children) - 1)
    
    def set_running(self, task):
        """设置当前运行任务"""
        steps = task.get("steps", ["step1", "step2", "step3", "step4"])
        running = {
            "task_id": task["task_id"],
            "type": task["type"],
            "goal": task["goal"],
            "steps": steps,
            "current_step": 0,
            "total_steps": len(steps),
            "progress": 0.0,
            "started_at": task.get("created")
        }
        write_json(self.queue_dir / "running.json", running)
        return running
    
    def clear_running(self):
        """清空running状态"""
        empty = {
            "task_id": None,
            "type": None,
            "goal": None,
            "step": 0,
            "total_steps": 0,
            "progress": 0.0,
            "started_at": None
        }
        write_json(self.queue_dir / "running.json", empty)
    
    def move_to_finished(self, running_task, status="done"):
        """将任务移动到finished队列"""
        finished = self.get_finished()
        
        from datetime import datetime
        completed_task = {
            "task_id": running_task["task_id"],
            "type": running_task["type"],
            "goal": running_task["goal"],
            "status": status,
            "completed": datetime.now().isoformat(),
            "result": "success" if status == "done" else status
        }
        
        finished.append(completed_task)
        write_json(self.queue_dir / "finished.json", finished)
        
        # 清空running
        self.clear_running()
        
        return completed_task
    
    def has_running_task(self):
        """检查是否有正在运行的任务"""
        running = self.get_running()
        return running.get("task_id") is not None
    
    def update_progress(self, step, total_steps):
        """更新任务进度"""
        running = self.get_running()
        running["step"] = step
        running["total_steps"] = total_steps
        running["progress"] = step / total_steps if total_steps > 0 else 0.0
        write_json(self.queue_dir / "running.json", running)
        return running

if __name__ == "__main__":
    print("=== Task Queue Test ===")
    queue = TaskQueue()
    
    print(f"Has running: {queue.has_running_task()}")
    print(f"Pending count: {len(queue.get_pending())}")
    print(f"Finished count: {len(queue.get_finished())}")
