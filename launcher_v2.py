"""
Aeon Launcher v2.0 - 集成 Goal & Attention System

新增:
- EventBus v2 (重试机制 + TTL)
- GoalManager (启动恢复)
- Cognition Loop v2 (Trace 日志)
"""

import sys
import os
import time
import signal
import atexit
import argparse
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

# v2: 使用新的 EventBus
from bus.event_bus_v2 import get_event_bus, EventBus, EventType

# v2: GoalManager
from goals import GoalManager, get_goal_manager

# v2: Cognition Loop
from cognition.cognition_loop_v2 import get_cognition

from tasks.task_system import TaskQueue, TaskWatchdog, Worker
from tasks.action_handlers import register_standard_handlers
from tasks.task_planner import RuleBasedPlanner
from memory.memory_index import get_memory_index
from memory.memory_buffer import get_memory_buffer

logger = get_logger()


class AeonLauncher:
    """Aeon 系统启动器 v2.0"""
    
    def __init__(self):
        self.components = {}
        self.running = False
        self.shutdown_requested = False
        
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
    
    def _signal_handler(self, signum, frame):
        """信号处理"""
        sig_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.info(f"Received {sig_name}, initiating graceful shutdown...", component="Launcher")
        self.shutdown_requested = True
        self.stop()
    
    def _cleanup(self):
        """清理资源"""
        if not self.components:
            return
        
        logger.info("Cleaning up resources...", component="Launcher")
        
        # 1. 停止认知循环
        if 'cognition' in self.components:
            try:
                self.components['cognition'].stop()
                logger.info("Cognition loop stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping cognition: {e}", component="Launcher")
        
        # 2. 刷新记忆缓冲区
        if 'memory_buffer' in self.components:
            try:
                self.components['memory_buffer'].force_flush()
                logger.info("Memory buffer flushed", component="Launcher")
            except Exception as e:
                logger.error(f"Error flushing memory buffer: {e}", component="Launcher")
        
        # 3. 停止看门狗
        if 'watchdog' in self.components:
            try:
                self.components['watchdog'].stop()
                logger.info("Task watchdog stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping watchdog: {e}", component="Launcher")
        
        # 4. 停止 Workers
        if 'worker' in self.components:
            try:
                self.components['worker'].stop()
                logger.info("Worker stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping worker: {e}", component="Launcher")
        
        logger.info("Cleanup complete", component="Launcher")
    
    def init_directories(self):
        """初始化目录"""
        dirs = [
            '/root/.openclaw/workspace/agent/logs',
            '/root/.openclaw/workspace/agent/db',
            '/root/.openclaw/workspace/agent/state',
        ]
        
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)
        
        logger.info("Directories initialized", component="Launcher")
    
    def check_state_file(self):
        """检查状态文件"""
        state_file = Path('/root/.openclaw/workspace/agent/state/system.state')
        
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                last_run = state.get('last_run')
                pid = state.get('pid')
                start_count = state.get('start_count', 0)
                
                logger.info(
                    f"Previous state: last_run={last_run}, pid={pid}, starts={start_count}",
                    component="Launcher"
                )
                
                return True, state
            except Exception as e:
                logger.warning(f"Failed to read state file: {e}", component="Launcher")
        
        return False, {}
    
    def save_state(self):
        """保存当前状态"""
        state_file = Path('/root/.openclaw/workspace/agent/state/system.state')
        
        start_count = 0
        if state_file.exists():
            try:
                existing = json.loads(state_file.read_text())
                start_count = existing.get('start_count', 0)
            except:
                pass
        
        state = {
            'last_run': datetime.now().isoformat(),
            'pid': os.getpid(),
            'status': 'running' if self.running else 'stopped',
            'start_count': start_count + 1,
            'version': '3.1',  # v2: 版本标记
        }
        
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error(f"Failed to save state: {e}", component="Launcher")
    
    def recover_goals(self):
        """
        v2 NEW: 恢复 Goal 状态
        """
        logger.info("Recovering goals...", component="Launcher")
        
        try:
            goal_manager = get_goal_manager()
            result = goal_manager.recover_on_startup()
            
            status = result.get('status')
            if status == 'resumed':
                logger.info(
                    f"Resumed active goal: {result['goal_id'][:8]}... '{result['description'][:40]}'",
                    component="Launcher"
                )
            elif status == 'activated':
                logger.info(
                    f"Activated pending goal: {result['goal_id'][:8]}... '{result['description'][:40]}'",
                    component="Launcher"
                )
            elif status == 'no_goals':
                logger.info("No goals to recover", component="Launcher")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to recover goals: {e}", component="Launcher")
            return {"status": "error", "error": str(e)}
    
    def recover_pending_tasks(self):
        """恢复未完成的任务"""
        logger.info("Recovering pending tasks...", component="Launcher")
        
        try:
            from tasks.task_system import TaskPersistence
            persistence = TaskPersistence()
            
            pending_tasks = persistence.get_pending_tasks()
            if pending_tasks:
                logger.info(f"Found {len(pending_tasks)} pending tasks", component="Launcher")
            
            running_tasks = persistence.get_running_tasks()
            if running_tasks:
                logger.warning(f"Found {len(running_tasks)} running tasks (will retry)", component="Launcher")
                for task in running_tasks:
                    persistence.update_task_status(task.task_id, 'pending', {
                        'retry_reason': 'system_restart'
                    })
            
            return len(pending_tasks) + len(running_tasks)
            
        except Exception as e:
            logger.error(f"Failed to recover tasks: {e}", component="Launcher")
            return 0
    
    def recover_events(self):
        """
        v2: EventBus v2 自动处理 crash recovery
        reset_processing_on_startup() 在 EventBus 初始化时调用
        """
        logger.info("EventBus v2: Processing crash recovery...", component="Launcher")
        
        try:
            bus = get_event_bus()
            # v2: 获取死信数量（用于告警）
            dead_count = len(bus.get_dead_letters(limit=100))
            if dead_count > 0:
                logger.warning(f"Found {dead_count} dead letter events", component="Launcher")
            
            queue_size = bus.get_queue_size()
            logger.info(f"Event queue size: {queue_size}", component="Launcher")
            
            return queue_size
            
        except Exception as e:
            logger.error(f"Failed to check events: {e}", component="Launcher")
            return 0
    
    def start(self, recover=True):
        """启动系统 v2.0"""
        logger.info("=" * 50, component="Launcher")
        logger.info("Aeon Agent v3.1 - Starting...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        # 1. 初始化目录
        self.init_directories()
        
        # 2. Boot Check
        logger.info("Running boot check...", component="Launcher")
        import subprocess
        result = subprocess.run(
            ['/usr/bin/python3', '/root/.openclaw/workspace/agent/boot_check.py'],
            capture_output=True,
            text=True
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logger.info(line, component="BootCheck")
        
        # 3. 检查重启
        is_restart, prev_state = self.check_state_file()
        if is_restart:
            logger.info("System restart detected", component="Launcher")
        
        # 4. 初始化日志
        self.components['logger'] = logger
        
        # 5. v2: 初始化 EventBus (自动处理 crash recovery)
        logger.info("Initializing EventBus v2...", component="Launcher")
        bus = get_event_bus()
        self.components['bus'] = bus
        
        # 6. v2: 初始化 GoalManager
        logger.info("Initializing GoalManager...", component="Launcher")
        goal_manager = get_goal_manager()
        self.components['goal_manager'] = goal_manager
        
        # 7. 恢复数据
        if recover:
            # v2: 恢复 Goals
            goal_result = self.recover_goals()
            
            # 恢复 Tasks
            task_count = self.recover_pending_tasks()
            
            # v2: 检查 Events
            queue_size = self.recover_events()
        
        # 8. 初始化记忆系统
        logger.info("Initializing memory system...", component="Launcher")
        memory_index = get_memory_index()
        memory_buffer = get_memory_buffer()
        self.components['memory_index'] = memory_index
        self.components['memory_buffer'] = memory_buffer
        
        # 9. 初始化任务系统
        logger.info("Initializing task system...", component="Launcher")
        queue = TaskQueue()
        worker = Worker("main_worker")
        register_standard_handlers(worker)
        queue.register_worker(worker)
        
        watchdog = TaskWatchdog(check_interval=60, heartbeat_timeout=300)
        watchdog.start()
        
        self.components['queue'] = queue
        self.components['worker'] = worker
        self.components['watchdog'] = watchdog
        
        # 10. 初始化规划器
        logger.info("Initializing task planner...", component="Launcher")
        from tasks.task_planner import get_planner
        planner = get_planner()
        self.components['planner'] = planner
        
        # 11. v2: 初始化 Cognition Loop
        logger.info("Initializing Cognition Loop v2...", component="Launcher")
        cognition = get_cognition()
        
        # 注册规则处理器
        def health_check_handler(observation):
            return RuleBasedPlanner.try_plan("检查系统健康状态")
        
        def backup_handler(observation):
            return RuleBasedPlanner.try_plan("备份工作目录")
        
        cognition.register_rule_handler("health_check", health_check_handler)
        cognition.register_rule_handler("backup", backup_handler)
        
        cognition.start()
        self.components['cognition'] = cognition
        
        # 12. 保存状态
        self.running = True
        self.save_state()
        
        # 13. 发布系统启动事件
        bus.publish_simple(
            "system.started",
            {
                'restart': is_restart,
                'version': '3.1',
                'recovered_goals': goal_result if recover else None,
                'recovered_tasks': task_count if recover else 0,
                'queue_size': queue_size if recover else 0,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        logger.info("=" * 50, component="Launcher")
        logger.info("Aeon Agent v3.1 - Started successfully!", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        if recover:
            logger.info(
                f"Recovery: goal={goal_result.get('status')}, "
                f"tasks={task_count}, queue={queue_size}",
                component="Launcher"
            )
        
        # v2: 打印 Goal 状态
        goal_manager.print_status()
        
        return self.components
    
    def run_forever(self):
        """保持运行"""
        logger.info("Running forever...", component="Launcher")
        
        try:
            while self.running and not self.shutdown_requested:
                if 'queue' in self.components:
                    self.components['queue'].process_next()
                
                # 每分钟保存状态
                if int(time.time()) % 60 == 0:
                    self.save_state()
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received", component="Launcher")
        finally:
            self.stop()
    
    def stop(self):
        """停止系统"""
        if not self.running:
            return
        
        logger.info("Stopping Aeon Agent...", component="Launcher")
        self.running = False
        self._cleanup()
        self.save_state()
        logger.info("Aeon Agent stopped", component="Launcher")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Aeon Agent Launcher v3.1')
    parser.add_argument('--no-recover', action='store_true', help='Skip recovery')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    args = parser.parse_args()
    
    launcher = AeonLauncher()
    
    try:
        components = launcher.start(recover=not args.no_recover)
        
        if args.daemon:
            launcher.run_forever()
        else:
            logger.info("Running in foreground mode", component="Launcher")
            return components
            
    except Exception as e:
        logger.error(f"Failed to start: {e}", component="Launcher")
        raise


if __name__ == "__main__":
    main()
