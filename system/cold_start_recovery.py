#!/usr/bin/env python3
"""
Cold Start Recovery - 冷启动恢复系统

Agent必须能从宕机、OOM、崩溃后恢复，继续执行：
  1. 读取 memory
  2. 读取 task queue
  3. 恢复 state machine
  4. 继续执行
"""
import json
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def get_logger():
    """延迟导入logger避免循环依赖"""
    try:
        from system.logger import logger
        return logger
    except ImportError:
        # 如果logger还没初始化，用print
        class DummyLogger:
            def info(self, msg): print(f"[INFO] {msg}")
            def warning(self, msg): print(f"[WARN] {msg}")
            def error(self, msg): print(f"[ERROR] {msg}")
        return DummyLogger()

class ColdStartRecovery:
    """
    冷启动恢复管理器
    
    在Agent启动时调用，恢复之前的状态
    """
    
    def __init__(self, agent_dir=None):
        self.agent_dir = Path(agent_dir) if agent_dir else AGENT_DIR
        self.state_file = self.agent_dir / "system" / "last_state.json"
        self.logger = get_logger()
    
    def save_state(self, state):
        """
        保存当前状态（定期调用或在关键操作后调用）
        
        Args:
            state: 要保存的状态字典
        """
        state_with_meta = {
            "timestamp": datetime.now().isoformat(),
            "state": state
        }
        
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_with_meta, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")
            return False
    
    def recover(self):
        """
        冷启动恢复流程
        
        Returns:
            dict: 恢复的状态信息
        """
        self.logger.info("=" * 50)
        self.logger.info("[COLD_START] 开始冷启动恢复...")
        self.logger.info("=" * 50)
        
        recovered = {
            "timestamp": datetime.now().isoformat(),
            "memory": None,
            "task_queue": None,
            "state_machine": None,
            "can_resume": False,
            "errors": []
        }
        
        # 1. 恢复记忆系统
        try:
            memory = self._recover_memory()
            recovered["memory"] = memory
            self.logger.info("[RECOVERY] ✓ Memory loaded")
        except Exception as e:
            recovered["errors"].append(f"memory: {e}")
            self.logger.error(f"[RECOVERY] ✗ Failed to load memory: {e}")
        
        # 2. 恢复任务队列
        try:
            task_queue = self._recover_task_queue()
            recovered["task_queue"] = task_queue
            self.logger.info(f"[RECOVERY] ✓ Task queue loaded: {task_queue.get('pending_count', 0)} pending")
        except Exception as e:
            recovered["errors"].append(f"task_queue: {e}")
            self.logger.error(f"[RECOVERY] ✗ Failed to load task queue: {e}")
        
        # 3. 恢复状态机
        try:
            state_machine = self._recover_state_machine()
            recovered["state_machine"] = state_machine
            self.logger.info("[RECOVERY] ✓ State machine loaded")
        except Exception as e:
            recovered["errors"].append(f"state_machine: {e}")
            self.logger.error(f"[RECOVERY] ✗ Failed to load state machine: {e}")
        
        # 4. 检查是否可以恢复执行
        recovered["can_resume"] = (
            recovered["task_queue"] is not None and
            recovered["task_queue"].get("pending_count", 0) > 0
        )
        
        if recovered["can_resume"]:
            self.logger.info("[RECOVERY] ✓ Agent can resume from previous state")
        else:
            self.logger.info("[RECOVERY] ℹ No pending tasks, starting fresh")
        
        self.logger.info("=" * 50)
        
        return recovered
    
    def _recover_memory(self):
        """恢复记忆系统"""
        memory_info = {}
        
        # 检查长期记忆文件
        long_term_file = self.agent_dir / "memory" / "long_term.md"
        if long_term_file.exists():
            with open(long_term_file, 'r', encoding='utf-8') as f:
                content = f.read()
                memory_info["long_term_size"] = len(content)
                memory_info["long_term_lines"] = len(content.split('\n'))
        
        # 检查日记文件
        diary_file = self.agent_dir / "memory" / "diary.md"
        if diary_file.exists():
            with open(diary_file, 'r', encoding='utf-8') as f:
                content = f.read()
                memory_info["diary_size"] = len(content)
                memory_info["diary_entries"] = content.count('## ')
        
        # 检查环境输入文件
        env_file = self.agent_dir / "environment.json"
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                env_data = json.load(f)
                memory_info["last_environment"] = env_data.get("timestamp")
        
        return memory_info
    
    def _recover_task_queue(self):
        """恢复任务队列"""
        queue_info = {
            "pending": [],
            "running": None,
            "finished": [],
            "pending_count": 0
        }
        
        # 读取待处理任务
        pending_file = self.agent_dir / "tasks" / "queue" / "pending.json"
        if pending_file.exists():
            with open(pending_file, 'r', encoding='utf-8') as f:
                queue_info["pending"] = json.load(f)
                queue_info["pending_count"] = len(queue_info["pending"])
        
        # 读取正在运行的任务
        running_file = self.agent_dir / "tasks" / "queue" / "running.json"
        if running_file.exists():
            with open(running_file, 'r', encoding='utf-8') as f:
                running = json.load(f)
                queue_info["running"] = running
                
                # 如果有运行中的任务，标记为中断
                if running:
                    self.logger.warning(f"[RECOVERY] Previous task {running.get('task_id', 'unknown')} was interrupted")
                    # 将中断的任务移到待处理队列头部
                    running["status"] = "interrupted"
                    running["interrupted_at"] = datetime.now().isoformat()
                    queue_info["pending"].insert(0, running)
                    queue_info["pending_count"] += 1
                    
                    # 保存更新后的pending
                    with open(pending_file, 'w', encoding='utf-8') as f:
                        json.dump(queue_info["pending"], f, indent=2)
                    
                    # 清空running
                    with open(running_file, 'w', encoding='utf-8') as f:
                        json.dump({}, f)
        
        return queue_info
    
    def _recover_state_machine(self):
        """恢复状态机"""
        state_file = self.agent_dir / "system" / "state.json"
        
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
    
    def resume_execution(self, recovered_state):
        """
        恢复执行
        
        Args:
            recovered_state: recover()返回的状态
            
        Returns:
            dict: 恢复执行的结果
        """
        if not recovered_state.get("can_resume"):
            self.logger.info("[RESUME] No tasks to resume, starting fresh")
            return {"status": "fresh_start"}
        
        task_queue = recovered_state.get("task_queue", {})
        pending = task_queue.get("pending", [])
        
        if not pending:
            return {"status": "no_tasks"}
        
        # 获取第一个任务
        next_task = pending[0]
        task_id = next_task.get("task_id", "unknown")
        goal = next_task.get("goal", "no goal")
        
        self.logger.info(f"[RESUME] Continuing with task: {task_id}")
        self.logger.info(f"[RESUME] Goal: {goal[:60]}...")
        
        return {
            "status": "resumed",
            "task": next_task,
            "total_pending": len(pending)
        }
    
    def quick_check(self):
        """快速检查是否可以恢复"""
        pending_file = self.agent_dir / "tasks" / "queue" / "pending.json"
        
        if not pending_file.exists():
            return False, 0
        
        try:
            with open(pending_file, 'r', encoding='utf-8') as f:
                pending = json.load(f)
                return len(pending) > 0, len(pending)
        except:
            return False, 0

if __name__ == "__main__":
    print("=== Cold Start Recovery Test ===\n")
    
    recovery = ColdStartRecovery()
    
    # 测试恢复
    print("1. 执行恢复...")
    state = recovery.recover()
    
    print(f"\n2. 恢复结果:")
    print(f"   可以恢复: {state['can_resume']}")
    print(f"   待处理任务: {state['task_queue']['pending_count'] if state['task_queue'] else 0}")
    print(f"   错误数: {len(state['errors'])}")
    
    print(f"\n3. 尝试恢复执行...")
    result = recovery.resume_execution(state)
    print(f"   结果: {result['status']}")
    
    print("\n✅ 冷启动恢复测试完成")
