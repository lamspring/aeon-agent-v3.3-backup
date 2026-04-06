"""
Aeon Launcher - 系统启动器

处理系统启动时的初始化、状态恢复、服务管理
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
from bus.event_bus import get_event_bus, EventType
from tasks.task_system import TaskQueue, TaskWatchdog, Worker
from tasks.action_handlers import register_standard_handlers
from cognition.cognition_loop import get_cognition
from tasks.task_planner import RuleBasedPlanner
from memory.memory_index import get_memory_index
from memory.memory_buffer import get_memory_buffer

logger = get_logger()


class AeonLauncher:
    """Aeon 系统启动器"""
    
    def __init__(self):
        self.components = {}
        self.running = False
        self.shutdown_requested = False
        
        # 设置信号处理
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # 注册退出处理
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
        """检查状态文件，判断是否是重启"""
        state_file = Path('/root/.openclaw/workspace/agent/state/system.state')
        
        if state_file.exists():
            try:
                import json
                state = json.loads(state_file.read_text())
                last_run = state.get('last_run')
                pid = state.get('pid')
                
                logger.info(
                    f"Previous state found: last_run={last_run}, pid={pid}",
                    component="Launcher"
                )
                
                return True, state
            except Exception as e:
                logger.warning(f"Failed to read state file: {e}", component="Launcher")
        
        return False, {}
    
    def save_state(self):
        """保存当前状态"""
        state_file = Path('/root/.openclaw/workspace/agent/state/system.state')
        
        # 读取现有状态以更新启动计数
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
            'start_count': start_count + 1
        }
        
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.error(f"Failed to save state: {e}", component="Launcher")
    
    def recover_pending_tasks(self):
        """恢复未完成的任务"""
        logger.info("Recovering pending tasks...", component="Launcher")
        
        # 从数据库加载 PENDING 和 RUNNING 状态的任务
        try:
            from tasks.task_system import TaskPersistence
            persistence = TaskPersistence()
            
            # 恢复 PENDING 任务
            pending_tasks = persistence.get_pending_tasks()
            if pending_tasks:
                logger.info(f"Found {len(pending_tasks)} pending tasks to recover", component="Launcher")
                for task in pending_tasks:
                    logger.info(f"  - Task {task.task_id}: {task.action}", component="Launcher")
            
            # 恢复 RUNNING 任务 (标记为失败，等待重试)
            running_tasks = persistence.get_running_tasks()
            if running_tasks:
                logger.warning(f"Found {len(running_tasks)} running tasks (will retry)", component="Launcher")
                for task in running_tasks:
                    task_id = task.task_id
                    # 标记为需要重试
                    persistence.update_task_status(task_id, 'pending', {
                        'retry_reason': 'system_restart'
                    })
                    logger.info(f"  - Task {task_id} marked for retry", component="Launcher")
            
            return len(pending_tasks) + len(running_tasks)
            
        except Exception as e:
            logger.error(f"Failed to recover tasks: {e}", component="Launcher")
            return 0
    
    def recover_unprocessed_events(self):
        """恢复未处理的事件"""
        logger.info("Recovering unprocessed events...", component="Launcher")
        
        try:
            bus = get_event_bus()
            count = bus.restore_unprocessed()
            
            if count > 0:
                logger.info(f"Restored {count} unprocessed events", component="Launcher")
            
            return count
            
        except Exception as e:
            import traceback
            logger.error(f"Failed to recover events: {e}", component="Launcher")
            logger.error(f"Traceback: {traceback.format_exc()}", component="Launcher")
            return 0
    
    def start(self, recover=True):
        """启动系统"""
        logger.info("=" * 50, component="Launcher")
        logger.info("Aeon Agent v3.0 - Starting...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        # 1. 初始化目录
        self.init_directories()
        
        # 2. 运行 Boot Check
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
        
        # 3. 检查是否是重启
        is_restart, prev_state = self.check_state_file()
        
        if is_restart:
            logger.info("System restart detected, initiating recovery...", component="Launcher")
        
        # 3. 初始化日志
        logger.info("Initializing logger...", component="Launcher")
        self.components['logger'] = logger
        
        # 4. 初始化事件总线
        logger.info("Initializing event bus...", component="Launcher")
        bus = get_event_bus()
        self.components['bus'] = bus
        
        # 5. 恢复未处理事件
        if recover:
            event_count = self.recover_unprocessed_events()
        
        # 6. 初始化记忆系统
        logger.info("Initializing memory system...", component="Launcher")
        memory_index = get_memory_index()
        memory_buffer = get_memory_buffer()
        self.components['memory_index'] = memory_index
        self.components['memory_buffer'] = memory_buffer
        
        # 7. 初始化任务系统
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
        
        # 8. 恢复未完成任务
        if recover:
            task_count = self.recover_pending_tasks()
        
        # 9. 初始化任务规划器
        logger.info("Initializing task planner...", component="Launcher")
        from tasks.task_planner import get_planner
        planner = get_planner()
        self.components['planner'] = planner
        
        # 10. 初始化认知循环
        logger.info("Initializing cognition loop...", component="Launcher")
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
        
        # 11. 保存状态
        self.running = True
        self.save_state()
        
        # 12. 发布系统启动事件
        bus.publish_simple(
            EventType.SYSTEM_STARTED.value,
            {
                'restart': is_restart,
                'recovered_events': event_count if recover else 0,
                'recovered_tasks': task_count if recover else 0,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        logger.info("=" * 50, component="Launcher")
        logger.info("Aeon Agent v3.0 - Started successfully!", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        if recover:
            logger.info(f"Recovery summary: {event_count} events, {task_count} tasks", component="Launcher")
        
        return self.components
    
    def run_forever(self):
        """保持运行直到收到停止信号"""
        logger.info("Running forever (waiting for tasks)...", component="Launcher")
        
        try:
            while self.running and not self.shutdown_requested:
                # 处理队列中的任务
                if 'queue' in self.components:
                    self.components['queue'].process_next()
                
                # 保存状态 (每60秒)
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
        
        # 清理资源 (通过 atexit)
        self._cleanup()
        
        # 更新状态文件
        self.save_state()
        
        logger.info("Aeon Agent stopped", component="Launcher")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Aeon Agent Launcher')
    parser.add_argument('--no-recover', action='store_true', help='Skip recovery on startup')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    args = parser.parse_args()
    
    launcher = AeonLauncher()
    
    try:
        # 启动系统
        components = launcher.start(recover=not args.no_recover)
        
        if args.daemon:
            # 守护模式：持续运行
            launcher.run_forever()
        else:
            # 前台模式：直接返回组件
            logger.info("Running in foreground mode (use --daemon for background)", component="Launcher")
            return components
            
    except Exception as e:
        logger.error(f"Failed to start: {e}", component="Launcher")
        raise


if __name__ == "__main__":
    main()