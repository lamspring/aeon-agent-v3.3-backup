"""
Aeon Launcher v2.1 - 集成高优先级保护组件

新增:
- EventBus v2 (重试机制 + TTL)
- GoalManager (启动恢复)
- Cognition Loop v2.1 (Trace 日志 + World Input)
- Health Server (HTTP端点)
- Log Rotator (日志轮转)
- Alert System (告警通知)
- Cold Start Recovery (冷启动恢复)
- Memory Guard (内存保护)
- Health Checker (独立健康检查)
"""

import sys
import os
import time
import signal
import atexit
import argparse
import json
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

# v2: 使用新的 EventBus
from bus.event_bus_v2 import get_event_bus, EventBus, EventType

# v2: GoalManager
from goals import GoalManager, get_goal_manager

# v2.1: Cognition Loop (with World Input)
from cognition.cognition_loop_v2 import get_cognition

# v2: Health Server
from health_server import HealthServer

# v2: Config
from config import get_config

# v2: Log Rotator
from log_rotator import LogRotator

# v2: Alert System
from alert import AlertManager, get_alert_manager

# v2.1: 高优先级保护组件
from system.cold_start_recovery import ColdStartRecovery
from system.memory_guard import MemoryGuard
from system.health_check import HealthChecker

# v2.2: 中优先级能力组件
from system.goal_generator import GoalGenerator
from system.reflection_engine import ReflectionEngine
from system.life_rhythm_guard import LifeRhythmGuard

# v2.3: 治理增强组件
from system.design_manager import DesignManager
from system.action_approval import ActionApproval

from tasks.task_system import TaskQueue, TaskWatchdog, Worker
from tasks.action_handlers import register_standard_handlers
from tasks.task_planner import RuleBasedPlanner
from memory.memory_index import get_memory_index
from memory.memory_buffer import get_memory_buffer

logger = get_logger()


class AeonLauncher:
    """Aeon 系统启动器 v2.1"""
    
    def __init__(self):
        self.components = {}
        self.running = False
        self.shutdown_requested = False
        
        # v2.1: 高优先级保护组件
        self.cold_start_recovery = None
        self.memory_guard = None
        self.health_checker = None
        
        # v2.2: 中优先级能力组件
        self.goal_generator = None
        self.reflection_engine = None
        self.life_rhythm_guard = None
        
        # v2.3: 治理增强组件
        self.design_manager = None
        self.action_approval = None
        
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
        
        # 5. v2: 停止 Health Server
        if 'health_server' in self.components:
            try:
                self.components['health_server'].stop()
                logger.info("Health server stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping health server: {e}", component="Launcher")
        
        # 6. v2: 停止 Log Rotator
        if 'log_rotator' in self.components:
            try:
                self.components['log_rotator'].stop()
                logger.info("Log rotator stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping log rotator: {e}", component="Launcher")
        
        # v2.1: 停止保护组件
        if self.memory_guard:
            try:
                self.memory_guard.stop()
                logger.info("Memory Guard stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping memory guard: {e}", component="Launcher")
        
        if self.health_checker:
            try:
                self.health_checker.stop()
                logger.info("Health Checker stopped", component="Launcher")
            except Exception as e:
                logger.error(f"Error stopping health checker: {e}", component="Launcher")
        
        # v2.2: 清理中优先级组件
        if self.goal_generator:
            logger.info("Goal Generator state preserved", component="Launcher")
        
        if self.reflection_engine:
            logger.info("Reflection Engine state preserved", component="Launcher")
        
        if self.life_rhythm_guard:
            logger.info("Life Rhythm Guard stopped", component="Launcher")
        
        # v2.3: 清理治理增强组件
        if self.design_manager:
            logger.info("Design Manager state preserved", component="Launcher")
        
        if self.action_approval:
            logger.info("Action Approval state preserved", component="Launcher")
        
        # 7. v2: 发送停止告警通知
        try:
            alert = get_alert_manager()
            alert.on_system_stop()
        except Exception:
            pass  # 停止时忽略告警错误
        
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
            'version': '3.3',  # v2.3: 版本标记
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
        logger.info("Aeon Agent v3.3 - Starting...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        # 1. 初始化目录
        self.init_directories()
        
        # v2.1: 冷启动恢复 (在告警之前，确保状态正确)
        logger.info("=" * 50, component="Launcher")
        logger.info("v2.1: Cold Start Recovery...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        try:
            self.cold_start_recovery = ColdStartRecovery()
            recovery_result = self.cold_start_recovery.recover()
            
            if recovery_result.get('can_resume'):
                logger.info("✓ Cold start recovery successful, can resume operations", component="Launcher")
            else:
                logger.info("! Cold start recovery partial, some components need reinitialization", component="Launcher")
            
            if recovery_result.get('errors'):
                for error in recovery_result['errors']:
                    logger.warning(f"Recovery error: {error}", component="Launcher")
                    
        except Exception as e:
            logger.error(f"Cold start recovery failed: {e}", component="Launcher")
            self.cold_start_recovery = None
        
        # 1.5 v2: 尽早初始化告警系统
        try:
            logger.info("Initializing Alert System...", component="Launcher")
            from alert import get_alert_manager
            alert = get_alert_manager()
            self.components['alert'] = alert
            logger.info("Alert System ready", component="Launcher")
        except Exception as e:
            logger.warning(f"Failed to initialize Alert System early: {e}", component="Launcher")
        
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
        
        # 12. v2: 启动 Health Server (使用配置)
        config = get_config()
        health_cfg = config.health_server
        
        if health_cfg.enabled:
            logger.info("Starting Health HTTP Server...", component="Launcher")
            health_server = HealthServer(host=health_cfg.host, port=health_cfg.port)
            health_server.start()
            self.components['health_server'] = health_server
            
            logger.info(f"Health API: http://localhost:{health_cfg.port}/health", component="Launcher")
            logger.info(f"Metrics: http://localhost:{health_cfg.port}/metrics", component="Launcher")
        
        # v2.1: 启动 Memory Guard (内存保护)
        logger.info("=" * 50, component="Launcher")
        logger.info("v2.1: Starting protection components...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        try:
            self.memory_guard = MemoryGuard(max_memory_gb=2, check_interval=60)
            self.memory_guard.start()
            logger.info("✓ Memory Guard started (max=2GB, interval=60s)", component="Launcher")
        except Exception as e:
            logger.error(f"Failed to start Memory Guard: {e}", component="Launcher")
            self.memory_guard = None
        
        # v2.1: 启动 Health Checker (独立健康检查)
        try:
            self.health_checker = HealthChecker(
                interval=60,
                heartbeat_file="/tmp/agent_heartbeat",
                save_state_callback=self.save_state
            )
            self.health_checker.start()
            logger.info("✓ Health Checker started (interval=60s)", component="Launcher")
        except Exception as e:
            logger.error(f"Failed to start Health Checker: {e}", component="Launcher")
            self.health_checker = None
        
        # v2.2: 启动中优先级能力组件
        logger.info("=" * 50, component="Launcher")
        logger.info("v2.2: Starting capability components...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        # v2.2: Goal Generator (目标生成器)
        try:
            self.goal_generator = GoalGenerator()
            logger.info("✓ Goal Generator initialized", component="Launcher")
        except Exception as e:
            logger.error(f"Failed to initialize Goal Generator: {e}", component="Launcher")
            self.goal_generator = None
        
        # v2.2: Reflection Engine (反思引擎)
        try:
            self.reflection_engine = ReflectionEngine()
            logger.info("✓ Reflection Engine initialized", component="Launcher")
        except Exception as e:
            logger.error(f"Failed to initialize Reflection Engine: {e}", component="Launcher")
            self.reflection_engine = None
        
        # v2.2: Life Rhythm Guard (生活节律守护)
        try:
            self.life_rhythm_guard = LifeRhythmGuard()
            # 启动时执行一次完整检查
            check_result = self.life_rhythm_guard.check_all()
            logger.info(f"✓ Life Rhythm Guard initialized", component="Launcher")
            logger.info(f"  Gate: {'✓' if check_result.get('gate') else '✗'}, "
                       f"Governance: {'✓' if check_result.get('governance') else '✗'}, "
                       f"Approval: {'✓' if check_result.get('approval') else '✗'}", 
                       component="Launcher")
        except Exception as e:
            logger.error(f"Failed to initialize Life Rhythm Guard: {e}", component="Launcher")
            self.life_rhythm_guard = None
        
        # v2.3: 启动治理增强组件
        logger.info("=" * 50, component="Launcher")
        logger.info("v2.3: Starting governance components...", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        # v2.3: Design Manager (设计文档管理)
        try:
            self.design_manager = DesignManager()
            # 列出当前设计
            designs = self.design_manager.list_designs()
            design_count = len(designs) if designs else 0
            logger.info(f"✓ Design Manager initialized ({design_count} designs)", component="Launcher")
        except Exception as e:
            logger.error(f"Failed to initialize Design Manager: {e}", component="Launcher")
            self.design_manager = None
        
        # v2.3: Action Approval (操作审批系统)
        try:
            self.action_approval = ActionApproval()
            config = self.action_approval.config
            enabled = config.get('enabled', False)
            high_risk_count = len(config.get('high_risk_actions', []))
            medium_risk_count = len(config.get('medium_risk_actions', []))
            
            if enabled:
                logger.info(f"✓ Action Approval initialized", component="Launcher")
                logger.info(f"  High risk: {high_risk_count}, Medium risk: {medium_risk_count}", component="Launcher")
            else:
                logger.info("⚠ Action Approval disabled", component="Launcher")
        except Exception as e:
            logger.error(f"Failed to initialize Action Approval: {e}", component="Launcher")
            self.action_approval = None
        
        # 13. 保存状态
        self.running = True
        self.save_state()
        
        # 14. 发布系统启动事件
        bus.publish_simple(
            "system.started",
            {
                'restart': is_restart,
                'version': '3.3',
                'recovered_goals': goal_result if recover else None,
                'recovered_tasks': task_count if recover else 0,
                'queue_size': queue_size if recover else 0,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        logger.info("=" * 50, component="Launcher")
        logger.info("Aeon Agent v3.3 - Started successfully!", component="Launcher")
        logger.info("Protection: ColdStartRecovery + MemoryGuard + HealthChecker", component="Launcher")
        logger.info("Capabilities: GoalGenerator + ReflectionEngine + LifeRhythmGuard", component="Launcher")
        logger.info("Governance: DesignManager + ActionApproval", component="Launcher")
        logger.info("=" * 50, component="Launcher")
        
        if recover:
            logger.info(
                f"Recovery: goal={goal_result.get('status')}, "
                f"tasks={task_count}, queue={queue_size}",
                component="Launcher"
            )
        
        # v2: 打印 Goal 状态
        goal_manager.print_status()
        
        # 15. v2: 启动日志轮转
        logger.info("Starting Log Rotator...", component="Launcher")
        log_rotator = LogRotator(
            log_dir="/root/.openclaw/workspace/agent/logs",
            retention_days=7,
            check_interval=3600
        )
        log_rotator.start()
        self.components['log_rotator'] = log_rotator
        
        stats = log_rotator.get_stats()
        logger.info(
            f"Log rotation: {stats['file_count']} files, "
            f"{stats['total_size_mb']}MB, retention={stats['retention_days']}d",
            component="Launcher"
        )
        
        # 16. v2: 发送启动告警通知
        try:
            alert = get_alert_manager()
            alert.on_system_start(
                version='3.3',
                recover=recover
            )
            logger.info("Startup alert sent", component="Launcher")
        except Exception as e:
            logger.warning(f"Failed to send startup alert: {e}", component="Launcher")
        
        return self.components
    
    def run_forever(self):
        """
        保持运行 - systemd 推荐模式
        
        特点:
        - 永不退出（除非收到信号或手动停止）
        - tick级异常捕获，单点故障不导致崩溃
        - systemd直接管理，崩溃自动重启
        """
        logger.info("Running forever (systemd mode)...", component="Launcher")
        
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        try:
            while self.running and not self.shutdown_requested:
                try:
                    # 处理队列任务
                    if 'queue' in self.components:
                        self.components['queue'].process_next()
                    
                    # 每分钟保存状态
                    if int(time.time()) % 60 == 0:
                        self.save_state()
                    
                    # 成功执行，重置错误计数
                    consecutive_errors = 0
                    
                    time.sleep(1)
                    
                except Exception as tick_error:
                    # 单个tick失败，记录但不退出
                    consecutive_errors += 1
                    logger.error(
                        f"Tick error ({consecutive_errors}/{max_consecutive_errors}): {tick_error}",
                        component="Launcher"
                    )
                    
                    # 连续错误过多，主动退出让systemd重启
                    if consecutive_errors >= max_consecutive_errors:
                        logger.critical(
                            f"Too many consecutive errors ({consecutive_errors}), exiting for restart",
                            component="Launcher"
                        )
                        raise SystemExit(1)
                    
                    time.sleep(1)  # 错误后短暂暂停
                
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
    """
    主函数 - systemd 推荐模式 (foreground, 永不退出)
    
    systemd 配置:
        Type=simple
        ExecStart=/usr/bin/python3 launcher.py
        Restart=always
    
    特点:
    - 不daemonize，直接在前台运行
    - systemd直接管理进程生命周期
    - 崩溃时自动重启
    """
    parser = argparse.ArgumentParser(description='Aeon Agent Launcher v3.3')
    parser.add_argument('--no-recover', action='store_true', help='Skip recovery')
    args = parser.parse_args()
    
    launcher = AeonLauncher()
    
    # 启动并永远运行 (systemd 推荐模式)
    try:
        components = launcher.start(recover=not args.no_recover)
        launcher.run_forever()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...", component="Launcher")
        launcher.stop()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", component="Launcher")
        
        # 发送崩溃告警
        try:
            from alert import get_alert_manager
            alert = get_alert_manager()
            alert.on_service_crash(
                error=f"{type(e).__name__}: {str(e)}",
                component="Launcher"
            )
        except:
            pass
        
        # 异常退出，systemd会负责重启
        raise SystemExit(1)


if __name__ == "__main__":
    main()
