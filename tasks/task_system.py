"""
Task System - 任务系统
核心特性:
- Task Watchdog (故障检测)
- 状态机 (pending/running/finished/failed)
- 心跳机制
- 自动重试
- 超时处理
"""

import json
import time
import sqlite3
import threading
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Callable, Optional, Any
from pathlib import Path
from enum import Enum
from datetime import datetime
import logging

# 导入事件总线
import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')
from bus.event_bus import get_event_bus, Event, EventType
from utils.structured_log import get_logger, LogContext

logger = get_logger()


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"


@dataclass
class Task:
    """任务对象"""
    action: str
    params: Dict[str, Any]
    task_id: str = None
    status: str = TaskStatus.PENDING.value
    description: str = ""
    
    # 执行控制
    retry_count: int = 0
    max_retries: int = 3
    timeout: int = 300  # 5分钟默认超时
    
    # 依赖
    depends_on: List[str] = None
    
    # 时间戳
    created_at: float = None
    started_at: float = None
    finished_at: float = None
    last_heartbeat: float = None
    
    # 执行信息
    worker_id: str = None
    trace_id: str = None
    parent_task_id: str = None
    
    # 结果
    result: Any = None
    error: str = None
    failure_reason: str = None
    
    def __post_init__(self):
        if self.task_id is None:
            self.task_id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = time.time()
        if self.depends_on is None:
            self.depends_on = []
        # 确保状态是字符串
        if isinstance(self.status, TaskStatus):
            self.status = self.status.value
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "action": self.action,
            "params": self.params,
            "status": self.status,
            "description": self.description,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
            "depends_on": self.depends_on,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "last_heartbeat": self.last_heartbeat,
            "worker_id": self.worker_id,
            "trace_id": self.trace_id,
            "parent_task_id": self.parent_task_id,
            "result": self.result,
            "error": self.error,
            "failure_reason": self.failure_reason
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Task':
        """从字典创建"""
        return cls(
            action=d["action"],
            params=d.get("params", {}),
            task_id=d.get("task_id"),
            status=d.get("status", TaskStatus.PENDING.value),
            description=d.get("description", ""),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 3),
            timeout=d.get("timeout", 300),
            depends_on=d.get("depends_on", []),
            created_at=d.get("created_at"),
            started_at=d.get("started_at"),
            finished_at=d.get("finished_at"),
            last_heartbeat=d.get("last_heartbeat"),
            worker_id=d.get("worker_id"),
            trace_id=d.get("trace_id"),
            parent_task_id=d.get("parent_task_id"),
            result=d.get("result"),
            error=d.get("error"),
            failure_reason=d.get("failure_reason")
        )
    
    def is_timed_out(self) -> bool:
        """检查是否超时"""
        if self.status != TaskStatus.RUNNING.value or not self.started_at:
            return False
        elapsed = time.time() - self.started_at
        return elapsed > self.timeout
    
    def is_stale(self, heartbeat_timeout: int = 300) -> bool:
        """检查是否无响应 (stale)"""
        if self.status != TaskStatus.RUNNING.value:
            return False
        
        # 有最后心跳
        if self.last_heartbeat:
            elapsed = time.time() - self.last_heartbeat
            return elapsed > heartbeat_timeout
        
        # 没有心跳，用开始时间
        if self.started_at:
            elapsed = time.time() - self.started_at
            return elapsed > self.timeout
        
        return False
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.max_retries


class TaskPersistence:
    """任务持久化"""
    
    def __init__(self, db_path: str = "/root/.openclaw/workspace/agent/db/tasks.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    params TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    description TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    timeout INTEGER DEFAULT 300,
                    depends_on TEXT,
                    created_at REAL,
                    started_at REAL,
                    finished_at REAL,
                    last_heartbeat REAL,
                    worker_id TEXT,
                    trace_id TEXT,
                    parent_task_id TEXT,
                    result TEXT,
                    error TEXT,
                    failure_reason TEXT
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace ON tasks(trace_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON tasks(created_at)")
            
            conn.commit()
    
    def store(self, task: Task):
        """存储任务"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tasks VALUES 
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id,
                    task.action,
                    json.dumps(task.params),
                    task.status,
                    task.description,
                    task.retry_count,
                    task.max_retries,
                    task.timeout,
                    json.dumps(task.depends_on) if task.depends_on else '[]',
                    task.created_at,
                    task.started_at,
                    task.finished_at,
                    task.last_heartbeat,
                    task.worker_id,
                    task.trace_id,
                    task.parent_task_id,
                    json.dumps(task.result) if task.result else None,
                    task.error,
                    task.failure_reason
                )
            )
            conn.commit()
    
    def get(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_task(row)
            return None
    
    def get_by_status(self, status: str) -> List[Task]:
        """按状态获取任务"""
        tasks = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at",
                (status,)
            )
            
            for row in cursor.fetchall():
                tasks.append(self._row_to_task(row))
        
        return tasks
    
    def get_running_tasks(self) -> List[Task]:
        """获取运行中的任务"""
        return self.get_by_status(TaskStatus.RUNNING.value)
    
    def get_pending_tasks(self) -> List[Task]:
        """获取待处理任务"""
        return self.get_by_status(TaskStatus.PENDING.value)
    
    def _row_to_task(self, row) -> Task:
        """行转任务对象"""
        return Task(
            task_id=row[0],
            action=row[1],
            params=json.loads(row[2]),
            status=row[3],
            description=row[4] or "",
            retry_count=row[5] or 0,
            max_retries=row[6] or 3,
            timeout=row[7] or 300,
            depends_on=json.loads(row[8]) if row[8] else [],
            created_at=row[9],
            started_at=row[10],
            finished_at=row[11],
            last_heartbeat=row[12],
            worker_id=row[13],
            trace_id=row[14],
            parent_task_id=row[15],
            result=json.loads(row[16]) if row[16] else None,
            error=row[17],
            failure_reason=row[18]
        )
    
    def update_status(self, task_id: str, status: str):
        """更新状态"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?",
                (status, task_id)
            )
            conn.commit()
    
    def update_heartbeat(self, task_id: str):
        """更新心跳"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET last_heartbeat = ? WHERE task_id = ?",
                (time.time(), task_id)
            )
            conn.commit()
    
    def cleanup_old(self, days: int = 7):
        """清理旧任务"""
        cutoff = time.time() - (days * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM tasks WHERE status IN ('finished', 'failed') AND finished_at < ?",
                (cutoff,)
            )
            conn.commit()


class TaskWatchdog:
    """
    任务看门狗
    
    职责:
    - 监控运行中的任务
    - 检测超时/stale任务
    - 自动重试或标记失败
    """
    
    def __init__(self, 
                 check_interval: int = 60,
                 heartbeat_timeout: int = 300):
        self.check_interval = check_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.persistence = TaskPersistence()
        self.event_bus = get_event_bus()
        self._running = False
        self._thread = None
    
    def start(self):
        """启动看门狗"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        
        logger.info("TaskWatchdog started", component="TaskWatchdog")
    
    def stop(self):
        """停止看门狗"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _watch_loop(self):
        """监控循环"""
        while self._running:
            try:
                self.check_tasks()
            except Exception as e:
                logger.error(f"Watchdog error: {e}", component="TaskWatchdog")
            
            time.sleep(self.check_interval)
    
    def check_tasks(self):
        """检查任务状态"""
        running_tasks = self.persistence.get_running_tasks()
        
        for task in running_tasks:
            # 检查是否超时
            if task.is_timed_out():
                self._handle_timeout(task)
            # 检查是否stale (无心跳)
            elif task.is_stale(self.heartbeat_timeout):
                self._handle_stale(task)
    
    def _handle_timeout(self, task: Task):
        """处理超时任务"""
        logger.warning(
            f"Task {task.task_id} timeout ({task.timeout}s)",
            task_id=task.task_id,
            trace_id=task.trace_id,
            component="TaskWatchdog"
        )
        
        task.status = TaskStatus.TIMEOUT.value
        task.failure_reason = "timeout"
        self.persistence.store(task)
        
        # 尝试重试
        self._try_retry(task)
    
    def _handle_stale(self, task: Task):
        """处理无响应任务"""
        elapsed = time.time() - (task.last_heartbeat or task.started_at)
        
        logger.warning(
            f"Task {task.task_id} stale (no heartbeat for {elapsed:.0f}s)",
            task_id=task.task_id,
            trace_id=task.trace_id,
            component="TaskWatchdog"
        )
        
        task.status = TaskStatus.FAILED.value
        task.failure_reason = "no_heartbeat"
        self.persistence.store(task)
        
        # 尝试重试
        self._try_retry(task)
    
    def _try_retry(self, task: Task):
        """尝试重试"""
        if task.can_retry():
            # 重试
            task.retry_count += 1
            task.status = TaskStatus.RETRYING.value
            task.started_at = None
            task.last_heartbeat = None
            task.worker_id = None
            task.error = None
            task.failure_reason = None
            
            self.persistence.store(task)
            
            logger.info(
                f"Task {task.task_id} retry {task.retry_count}/{task.max_retries}",
                task_id=task.task_id,
                trace_id=task.trace_id,
                component="TaskWatchdog"
            )
            
            # 发布重试事件
            self.event_bus.publish_simple(
                EventType.TASK_RETRY.value,
                {
                    "task_id": task.task_id,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries
                },
                trace_id=task.trace_id
            )
            
            # 将任务重新加入队列
            task.status = TaskStatus.PENDING.value
            self.persistence.store(task)
            
        else:
            # 超过重试次数，标记最终失败
            task.status = TaskStatus.FAILED.value
            task.finished_at = time.time()
            task.failure_reason = task.failure_reason or "max_retries_exceeded"
            
            self.persistence.store(task)
            
            logger.error(
                f"Task {task.task_id} failed after {task.max_retries} retries",
                task_id=task.task_id,
                trace_id=task.trace_id,
                component="TaskWatchdog"
            )
            
            # 发布失败事件
            self.event_bus.publish_simple(
                EventType.TASK_FAILED.value,
                {
                    "task_id": task.task_id,
                    "reason": "max_retries_exceeded",
                    "retry_count": task.retry_count
                },
                trace_id=task.trace_id
            )


class Worker:
    """
    任务执行器
    
    职责:
    - 从队列获取任务
    - 执行任务
    - 发送心跳
    - 报告结果
    """
    
    def __init__(self, worker_id: str = None):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.persistence = TaskPersistence()
        self.event_bus = get_event_bus()
        self.handlers: Dict[str, Callable] = {}
        self._stop_event = threading.Event()
        self._heartbeat_threads: Dict[str, threading.Thread] = {}
    
    def register_handler(self, action: str, handler: Callable):
        """注册动作处理器"""
        self.handlers[action] = handler
    
    def execute_task(self, task: Task) -> Any:
        """执行任务"""
        handler = self.handlers.get(task.action)
        
        if not handler:
            raise ValueError(f"No handler for action: {task.action}")
        
        # 执行任务
        result = handler(task.params)
        return result
    
    def run_task(self, task: Task):
        """
        运行任务 (带心跳)
        """
        # 更新任务状态
        task.status = TaskStatus.RUNNING.value
        task.started_at = time.time()
        task.worker_id = self.worker_id
        self.persistence.store(task)
        
        # 发布开始事件
        self.event_bus.publish_simple(
            EventType.TASK_STARTED.value,
            {
                "task_id": task.task_id,
                "worker_id": self.worker_id,
                "action": task.action
            },
            trace_id=task.trace_id
        )
        
        logger.info(
            f"Task {task.task_id} started: {task.action}",
            task_id=task.task_id,
            trace_id=task.trace_id,
            component="Worker"
        )
        
        # 启动心跳线程
        stop_heartbeat = threading.Event()
        
        def heartbeat_loop():
            while not stop_heartbeat.is_set():
                self.persistence.update_heartbeat(task.task_id)
                time.sleep(30)  # 每30秒心跳
        
        heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        self._heartbeat_threads[task.task_id] = stop_heartbeat
        
        try:
            # 执行任务
            with LogContext(trace_id=task.trace_id, task_id=task.task_id):
                result = self.execute_task(task)
            
            # 成功
            task.status = TaskStatus.FINISHED.value
            task.finished_at = time.time()
            task.result = result
            self.persistence.store(task)
            
            # 发布完成事件
            self.event_bus.publish_simple(
                EventType.TASK_FINISHED.value,
                {
                    "task_id": task.task_id,
                    "result": result,
                    "duration": task.finished_at - task.started_at
                },
                trace_id=task.trace_id,
                parent_id=task.parent_task_id
            )
            
            logger.info(
                f"Task {task.task_id} finished",
                task_id=task.task_id,
                trace_id=task.trace_id,
                component="Worker"
            )
            
        except Exception as e:
            # 失败
            task.status = TaskStatus.FAILED.value
            task.finished_at = time.time()
            task.error = str(e)
            self.persistence.store(task)
            
            # 发布失败事件
            self.event_bus.publish_simple(
                EventType.TASK_FAILED.value,
                {
                    "task_id": task.task_id,
                    "error": str(e),
                    "duration": task.finished_at - task.started_at
                },
                trace_id=task.trace_id
            )
            
            logger.error(
                f"Task {task.task_id} failed: {e}",
                task_id=task.task_id,
                trace_id=task.trace_id,
                component="Worker"
            )
            
            raise
        
        finally:
            # 停止心跳
            stop_heartbeat.set()
            if task.task_id in self._heartbeat_threads:
                del self._heartbeat_threads[task.task_id]
    
    def stop(self):
        """停止 Worker，清理所有心跳线程"""
        self._stop_event.set()
        
        # 停止所有心跳线程
        for task_id, stop_event in list(self._heartbeat_threads.items()):
            stop_event.set()
            self._heartbeat_threads.pop(task_id, None)
        
        logger.info(f"Worker {self.worker_id} stopped", component="Worker")


class TaskQueue:
    """
    任务队列
    
    职责:
    - 管理任务生命周期
    - 协调Worker
    - 处理依赖关系
    """
    
    def __init__(self):
        self.persistence = TaskPersistence()
        self.event_bus = get_event_bus()
        self.workers: List[Worker] = []
        self._lock = threading.Lock()
    
    def add_task(self, task: Task) -> str:
        """添加任务"""
        task.status = TaskStatus.PENDING.value
        self.persistence.store(task)
        
        logger.info(
            f"Task {task.task_id} added: {task.action}",
            task_id=task.task_id,
            trace_id=task.trace_id,
            component="TaskQueue"
        )
        
        # 发布创建事件
        self.event_bus.publish_simple(
            EventType.TASK_CREATED.value,
            {
                "task_id": task.task_id,
                "action": task.action,
                "description": task.description
            },
            trace_id=task.trace_id
        )
        
        return task.task_id
    
    def get_next_task(self) -> Optional[Task]:
        """获取下一个可执行的任务"""
        pending = self.persistence.get_pending_tasks()
        
        for task in pending:
            # 检查依赖
            if task.depends_on:
                all_deps_finished = True
                for dep_id in task.depends_on:
                    dep = self.persistence.get(dep_id)
                    if not dep or dep.status != TaskStatus.FINISHED.value:
                        all_deps_finished = False
                        break
                
                if not all_deps_finished:
                    continue
            
            return task
        
        return None
    
    def register_worker(self, worker: Worker):
        """注册Worker"""
        with self._lock:
            self.workers.append(worker)
    
    def process_next(self) -> bool:
        """处理下一个任务"""
        task = self.get_next_task()
        
        if not task:
            return False
        
        # 找一个可用的Worker
        with self._lock:
            if not self.workers:
                return False
            
            # 简单轮询，实际可以用更复杂的调度
            worker = self.workers[0]
        
        # 执行任务
        try:
            worker.run_task(task)
            return True
        except Exception as e:
            logger.error(f"Failed to process task {task.task_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """获取队列统计"""
        return {
            "pending": len(self.persistence.get_pending_tasks()),
            "running": len(self.persistence.get_running_tasks()),
            "workers": len(self.workers)
        }