"""
Structured Logging - 结构化日志
核心特性:
- trace_id: 追踪完整请求链
- event_id: 当前事件ID
- task_id: 当前任务ID
- parent_id: 父事件/任务ID
- JSON格式，便于解析和查询
"""

import json
import time
import uuid
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextvars import ContextVar
from enum import Enum

logger = logging.getLogger(__name__)


# 上下文变量 (用于跨函数传递追踪ID)
current_trace_id: ContextVar[str] = ContextVar('trace_id', default=None)
current_event_id: ContextVar[str] = ContextVar('event_id', default=None)
current_task_id: ContextVar[str] = ContextVar('task_id', default=None)


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogEntry:
    """结构化日志条目"""
    
    def __init__(self,
                 level: LogLevel,
                 message: str,
                 trace_id: str = None,
                 event_id: str = None,
                 task_id: str = None,
                 parent_id: str = None,
                 component: str = None,
                 context: Dict[str, Any] = None):
        
        self.timestamp = datetime.now().isoformat()
        self.level = level.value if isinstance(level, LogLevel) else level
        self.message = message
        self.trace_id = trace_id or current_trace_id.get() or str(uuid.uuid4())
        self.event_id = event_id or current_event_id.get()
        self.task_id = task_id or current_task_id.get()
        self.parent_id = parent_id
        self.component = component
        self.context = context or {}
        self.thread_id = threading.current_thread().ident
        self.process_id = None  # 可以添加进程ID
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        entry = {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
            "trace_id": self.trace_id,
            "thread_id": self.thread_id,
        }
        
        # 可选字段
        if self.event_id:
            entry["event_id"] = self.event_id
        if self.task_id:
            entry["task_id"] = self.task_id
        if self.parent_id:
            entry["parent_id"] = self.parent_id
        if self.component:
            entry["component"] = self.component
        if self.context:
            entry["context"] = self.context
        
        return entry
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    def __str__(self) -> str:
        """格式化输出 (人类可读)"""
        parts = [
            f"[{self.timestamp}]",
            f"[{self.level}]",
            f"[trace:{self.trace_id[:8]}]"
        ]
        
        if self.event_id:
            parts.append(f"[evt:{self.event_id[:8]}]")
        if self.task_id:
            parts.append(f"[task:{self.task_id[:8]}]")
        if self.component:
            parts.append(f"[{self.component}]")
        
        parts.append(self.message)
        
        return " ".join(parts)


class StructuredLogger:
    """
    结构化日志记录器
    
    特性:
    - JSON格式输出
    - 自动追踪ID传递
    - 多目标输出 (文件 + 控制台)
    - 日志轮转
    """
    
    def __init__(self,
                 name: str = "agent",
                 log_dir: str = "/root/.openclaw/workspace/agent/logs",
                 level: LogLevel = LogLevel.INFO,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 max_files: int = 5):
        
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.level = level
        self.max_file_size = max_file_size
        self.max_files = max_files
        
        self._file_path = self.log_dir / f"{name}.log"
        self._json_path = self.log_dir / f"{name}.jsonl"
        self._lock = threading.Lock()
        
        # 初始化
        self._init_files()
    
    def _init_files(self):
        """初始化日志文件"""
        # 确保文件存在
        self._file_path.touch(exist_ok=True)
        self._json_path.touch(exist_ok=True)
    
    def _rotate_if_needed(self):
        """检查并轮转日志文件"""
        for file_path in [self._file_path, self._json_path]:
            if file_path.exists() and file_path.stat().st_size > self.max_file_size:
                self._rotate_file(file_path)
    
    def _rotate_file(self, file_path: Path):
        """轮转单个文件"""
        # 删除最旧的备份
        oldest_backup = file_path.parent / f"{file_path.name}.{self.max_files}"
        if oldest_backup.exists():
            oldest_backup.unlink()
        
        # 移动其他备份
        for i in range(self.max_files - 1, 0, -1):
            src = file_path.parent / f"{file_path.name}.{i}"
            dst = file_path.parent / f"{file_path.name}.{i + 1}"
            if src.exists():
                src.rename(dst)
        
        # 移动当前文件
        file_path.rename(file_path.parent / f"{file_path.name}.1")
    
    def _should_log(self, level: LogLevel) -> bool:
        """检查是否应该记录该级别"""
        levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, 
                  LogLevel.ERROR, LogLevel.CRITICAL]
        return levels.index(level) >= levels.index(self.level)
    
    def _write(self, entry: StructuredLogEntry):
        """写入日志"""
        with self._lock:
            self._rotate_if_needed()
            
            # 人类可读格式
            with open(self._file_path, 'a', encoding='utf-8') as f:
                f.write(str(entry) + '\n')
            
            # JSON格式 (便于解析)
            with open(self._json_path, 'a', encoding='utf-8') as f:
                f.write(entry.to_json() + '\n')
    
    def log(self, level: LogLevel, message: str, 
            component: str = None, context: Dict[str, Any] = None,
            trace_id: str = None, event_id: str = None, 
            task_id: str = None, parent_id: str = None):
        """记录日志"""
        if not self._should_log(level):
            return
        
        entry = StructuredLogEntry(
            level=level,
            message=message,
            trace_id=trace_id,
            event_id=event_id,
            task_id=task_id,
            parent_id=parent_id,
            component=component,
            context=context
        )
        
        self._write(entry)
        
        # 同时输出到标准logging
        log_func = getattr(logger, level.value.lower())
        log_func(str(entry))
    
    # 便捷方法
    def debug(self, message: str, **kwargs):
        self.log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self.log(LogLevel.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self.log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self.log(LogLevel.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self.log(LogLevel.CRITICAL, message, **kwargs)
    
    # 上下文管理
    def with_trace(self, trace_id: str = None):
        """创建追踪上下文"""
        return LogContext(trace_id=trace_id)
    
    def with_event(self, event_id: str, trace_id: str = None):
        """创建事件上下文"""
        return LogContext(trace_id=trace_id, event_id=event_id)
    
    def with_task(self, task_id: str, trace_id: str = None, parent_id: str = None):
        """创建任务上下文"""
        return LogContext(trace_id=trace_id, task_id=task_id, parent_id=parent_id)


class LogContext:
    """
    日志上下文管理器
    
    用法:
        with logger.with_trace() as ctx:
            logger.info("Event received", event_id="evt001")
            # 所有日志自动带trace_id
    """
    
    def __init__(self, trace_id: str = None, event_id: str = None, 
                 task_id: str = None, parent_id: str = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.event_id = event_id
        self.task_id = task_id
        self.parent_id = parent_id
        
        self._tokens = []
    
    def __enter__(self):
        # 设置上下文变量
        self._tokens.append(current_trace_id.set(self.trace_id))
        if self.event_id:
            self._tokens.append(current_event_id.set(self.event_id))
        if self.task_id:
            self._tokens.append(current_task_id.set(self.task_id))
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 恢复上下文变量
        for token in reversed(self._tokens):
            try:
                if token:
                    # 根据token类型恢复对应的上下文
                    if current_trace_id.get(None) == self.trace_id:
                        current_trace_id.reset(token)
            except:
                pass
    
    def child_event(self, event_id: str):
        """创建子事件上下文"""
        return LogContext(
            trace_id=self.trace_id,
            event_id=event_id,
            parent_id=self.event_id or self.task_id
        )
    
    def child_task(self, task_id: str):
        """创建子任务上下文"""
        return LogContext(
            trace_id=self.trace_id,
            task_id=task_id,
            parent_id=self.event_id or self.task_id
        )


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, jsonl_path: str):
        self.jsonl_path = Path(jsonl_path)
    
    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        """获取完整追踪链"""
        entries = []
        
        if not self.jsonl_path.exists():
            return entries
        
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('trace_id') == trace_id:
                        entries.append(entry)
                except:
                    continue
        
        # 按时间排序
        entries.sort(key=lambda x: x.get('timestamp', ''))
        return entries
    
    def get_event_chain(self, event_id: str) -> List[Dict[str, Any]]:
        """获取事件链 (包括父事件和子事件)"""
        # 先找到该事件
        target_event = None
        all_entries = []
        
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    all_entries.append(entry)
                    if entry.get('event_id') == event_id:
                        target_event = entry
                except:
                    continue
        
        if not target_event:
            return []
        
        trace_id = target_event.get('trace_id')
        
        # 获取同一trace的所有事件
        chain = [e for e in all_entries if e.get('trace_id') == trace_id]
        chain.sort(key=lambda x: x.get('timestamp', ''))
        
        return chain
    
    def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """获取日志统计"""
        from datetime import datetime, timedelta
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        stats = {
            "total": 0,
            "by_level": {},
            "by_component": {},
            "unique_traces": set(),
            "time_range": {"start": None, "end": None}
        }
        
        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    timestamp = entry.get('timestamp', '')
                    
                    if timestamp < cutoff:
                        continue
                    
                    stats["total"] += 1
                    
                    # 按级别统计
                    level = entry.get('level', 'UNKNOWN')
                    stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
                    
                    # 按组件统计
                    component = entry.get('component', 'unknown')
                    stats["by_component"][component] = stats["by_component"].get(component, 0) + 1
                    
                    # 追踪ID
                    trace_id = entry.get('trace_id')
                    if trace_id:
                        stats["unique_traces"].add(trace_id)
                    
                    # 时间范围
                    if not stats["time_range"]["start"] or timestamp < stats["time_range"]["start"]:
                        stats["time_range"]["start"] = timestamp
                    if not stats["time_range"]["end"] or timestamp > stats["time_range"]["end"]:
                        stats["time_range"]["end"] = timestamp
                    
                except:
                    continue
        
        stats["unique_traces"] = len(stats["unique_traces"])
        return stats


# 全局日志实例
_structured_logger: Optional[StructuredLogger] = None


def get_logger() -> StructuredLogger:
    """获取全局结构化日志记录器"""
    global _structured_logger
    if _structured_logger is None:
        _structured_logger = StructuredLogger()
    return _structured_logger


def set_logger(logger: StructuredLogger):
    """设置全局日志记录器"""
    global _structured_logger
    _structured_logger = logger


# 便捷函数
def log(level: str, message: str, **kwargs):
    """快速记录日志"""
    logger = get_logger()
    log_func = getattr(logger, level.lower())
    log_func(message, **kwargs)


def debug(message: str, **kwargs):
    get_logger().debug(message, **kwargs)


def info(message: str, **kwargs):
    get_logger().info(message, **kwargs)


def warning(message: str, **kwargs):
    get_logger().warning(message, **kwargs)


def error(message: str, **kwargs):
    get_logger().error(message, **kwargs)


def critical(message: str, **kwargs):
    get_logger().critical(message, **kwargs)