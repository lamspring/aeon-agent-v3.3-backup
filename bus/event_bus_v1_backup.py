"""
Event Bus - 中央神经系统
核心特性:
- 唯一调度中心
- Rate Limiter (防Event Storm)
- Event TTL (60秒过期)
- Deduplication (5秒去重窗口)
- Persistence (SQLite双队列)
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
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型"""
    # 记忆事件
    MEMORY_UPDATED = "memory.updated"
    MEMORY_ACCESSED = "memory.accessed"
    
    # 任务事件
    TASK_CREATED = "task.created"
    TASK_PLANNED = "task.planned"
    TASK_STARTED = "task.started"
    TASK_FINISHED = "task.finished"
    TASK_FAILED = "task.failed"
    TASK_RETRY = "task.retry"
    
    # 消息事件
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_SENT = "message.sent"
    
    # 状态事件
    STATE_CHANGED = "state.changed"
    GATE_OPENED = "gate.opened"
    GATE_CLOSED = "gate.closed"
    
    # 系统事件
    SYSTEM_STARTED = "system.started"
    SYSTEM_SHUTDOWN = "system.shutdown"
    COGNITION_TICK = "cognition.tick"
    
    # 认知事件
    COGNITION_PLAN = "cognition.plan"
    COGNITION_REFLECT = "cognition.reflect"


@dataclass
class Event:
    """事件对象"""
    type: str
    data: Dict[str, Any]
    event_id: str = None
    timestamp: float = None
    ttl: int = 60  # 默认60秒过期
    trace_id: str = None
    parent_id: str = None
    source: str = None
    
    def __post_init__(self):
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.trace_id is None:
            self.trace_id = str(uuid.uuid4())
        if self.ttl is None:
            self.ttl = 60
    
    def is_expired(self) -> bool:
        """检查事件是否过期"""
        if self.timestamp is None or self.ttl is None:
            return False  # 无时间戳或TTL的事件不过期
        return time.time() - self.timestamp > self.ttl
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "event_id": self.event_id,
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'Event':
        """从字典创建"""
        ttl = d.get("ttl", 60)
        if ttl is None:
            ttl = 60
        return cls(
            type=d["type"],
            data=d["data"],
            event_id=d.get("event_id"),
            timestamp=d.get("timestamp"),
            ttl=ttl,
            trace_id=d.get("trace_id"),
            parent_id=d.get("parent_id"),
            source=d.get("source")
        )
    
    def get_hash(self) -> int:
        """生成事件指纹(用于去重)"""
        content = f"{self.type}:{json.dumps(self.data, sort_keys=True)}"
        return hash(content)


class RateLimiter:
    """速率限制器"""
    
    DEFAULT_LIMITS = {
        "memory.updated": 10,
        "task.created": 20,
        "cognition.tick": 1,
        "memory.accessed": 50,
        "default": 30
    }
    
    def __init__(self, limits: Dict[str, int] = None):
        self.limits = limits or self.DEFAULT_LIMITS
        self.counters: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
    
    def check(self, event_type: str) -> bool:
        """检查是否允许处理该事件"""
        limit = self.limits.get(event_type, self.limits["default"])
        
        with self._lock:
            now = time.time()
            
            # 初始化计数器
            if event_type not in self.counters:
                self.counters[event_type] = []
            
            # 清理1秒前的记录
            self.counters[event_type] = [
                t for t in self.counters[event_type] 
                if now - t < 1.0
            ]
            
            # 检查是否超限
            if len(self.counters[event_type]) >= limit:
                logger.warning(f"Rate limit exceeded for {event_type}: {len(self.counters[event_type])}/{limit}")
                return False
            
            # 记录本次
            self.counters[event_type].append(now)
            return True
    
    def should_process(self, event_type: str, source: str) -> bool:
        """防递归规则"""
        # cognition 不监听 memory.updated
        if source == "cognition" and event_type == EventType.MEMORY_UPDATED.value:
            return False
        return True


class Deduplicator:
    """去重器"""
    
    def __init__(self, window_seconds: int = 5):
        self.window = window_seconds
        self.recent_events: Dict[int, float] = {}
        self._lock = threading.Lock()
    
    def is_duplicate(self, event: Event) -> bool:
        """检查是否是重复事件"""
        event_hash = event.get_hash()
        now = time.time()
        
        with self._lock:
            # 清理过期记录
            cutoff = now - self.window
            self.recent_events = {
                k: v for k, v in self.recent_events.items() 
                if v > cutoff
            }
            
            # 检查重复
            if event_hash in self.recent_events:
                logger.debug(f"Duplicate event {event.type}, ignoring")
                return True
            
            # 记录新事件
            self.recent_events[event_hash] = now
            return False


class EventPersistence:
    """事件持久化 (SQLite)"""
    
    def __init__(self, db_path: str = "/root/.openclaw/workspace/agent/db/events.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    ttl INTEGER DEFAULT 60,
                    trace_id TEXT,
                    parent_id TEXT,
                    source TEXT,
                    processed BOOLEAN DEFAULT FALSE,
                    retry_count INTEGER DEFAULT 0
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_processed ON events(processed)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trace ON events(trace_id)")
            
            conn.commit()
    
    def store(self, event: Event):
        """存储事件"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO events 
                   (event_id, type, data, timestamp, ttl, trace_id, parent_id, source, processed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.type,
                    json.dumps(event.data),
                    event.timestamp,
                    event.ttl,
                    event.trace_id,
                    event.parent_id,
                    event.source,
                    False
                )
            )
            conn.commit()
    
    def get_unprocessed(self) -> List[Event]:
        """获取未处理的事件"""
        events = []
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM events WHERE processed = FALSE ORDER BY timestamp"
            )
            
            for row in cursor.fetchall():
                event = Event(
                    event_id=row[0],
                    type=row[1],
                    data=json.loads(row[2]),
                    timestamp=row[3] or time.time(),  # 修复: 处理 NULL 值
                    ttl=row[4] or 60,  # 修复: 处理 NULL 值
                    trace_id=row[5],
                    parent_id=row[6],
                    source=row[7]
                )
                
                # 跳过过期事件
                if event.is_expired():
                    conn.execute(
                        "DELETE FROM events WHERE event_id = ?",
                        (event.event_id,)
                    )
                    continue
                
                events.append(event)
        
        return events
    
    def mark_processed(self, event_id: str):
        """标记事件已处理"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE events SET processed = TRUE WHERE event_id = ?",
                (event_id,)
            )
            conn.commit()
    
    def cleanup_old(self, days: int = 7):
        """清理旧事件"""
        cutoff = time.time() - (days * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM events WHERE processed = TRUE AND timestamp < ?",
                (cutoff,)
            )
            conn.commit()


class EventBus:
    """
    事件总线 - 中央神经系统
    
    特性:
    - Rate Limiter (防Event Storm)
    - TTL (过期丢弃)
    - Deduplication (去重)
    - Persistence (持久化)
    - Structured Logging (trace_id)
    """
    
    def __init__(self, 
                 db_path: str = "/root/.openclaw/workspace/agent/db/events.db",
                 enable_persistence: bool = True):
        self.listeners: Dict[str, List[Callable]] = {}
        self.rate_limiter = RateLimiter()
        self.deduplicator = Deduplicator()
        self.persistence = EventPersistence(db_path) if enable_persistence else None
        self._lock = threading.Lock()
        
        logger.info("EventBus initialized")
    
    def subscribe(self, event_type: str, handler: Callable, source: str = None):
        """订阅事件"""
        with self._lock:
            if event_type not in self.listeners:
                self.listeners[event_type] = []
            
            # 检查防递归规则
            if source and not self.rate_limiter.should_process(event_type, source):
                logger.warning(f"Recursive subscription blocked: {source} -> {event_type}")
                return
            
            self.listeners[event_type].append(handler)
            logger.debug(f"Handler subscribed to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self.listeners:
                self.listeners[event_type] = [
                    h for h in self.listeners[event_type] if h != handler
                ]
    
    def publish(self, event: Event) -> bool:
        """
        发布事件
        
        Returns:
            bool: 是否成功发布
        """
        # 1. 检查过期
        if event.is_expired():
            logger.warning(f"Event {event.event_id} expired, dropping")
            return False
        
        # 2. 检查速率限制
        if not self.rate_limiter.check(event.type):
            return False
        
        # 3. 检查去重
        if self.deduplicator.is_duplicate(event):
            return False
        
        # 4. 持久化
        if self.persistence:
            try:
                self.persistence.store(event)
            except Exception as e:
                logger.error(f"Failed to persist event: {e}")
        
        # 5. 分发到监听器
        handlers = self.listeners.get(event.type, [])
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Handler error for {event.type}: {e}")
        
        # 6. 标记已处理
        if self.persistence:
            try:
                self.persistence.mark_processed(event.event_id)
            except Exception as e:
                logger.error(f"Failed to mark event processed: {e}")
        
        logger.debug(f"Event {event.type} processed ({len(handlers)} handlers)")
        return True
    
    def publish_simple(self, event_type: str, data: Dict, 
                       trace_id: str = None, parent_id: str = None) -> bool:
        """简化发布"""
        event = Event(
            type=event_type,
            data=data,
            trace_id=trace_id,
            parent_id=parent_id
        )
        return self.publish(event)
    
    def restore_unprocessed(self):
        """恢复未处理的事件 (启动时调用)"""
        if not self.persistence:
            return 0
        
        events = self.persistence.get_unprocessed()
        
        if events:
            logger.info(f"Restoring {len(events)} unprocessed events")
            
            for event in events:
                # 重新发布
                self.publish(event)
        
        return len(events) if events else 0
    
    def cleanup(self, days: int = 7):
        """清理旧数据"""
        if self.persistence:
            self.persistence.cleanup_old(days)
            logger.info(f"Cleaned up events older than {days} days")


# 全局事件总线实例
_bus_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventBus()
    return _bus_instance


def set_event_bus(bus: EventBus):
    """设置全局事件总线"""
    global _bus_instance
    _bus_instance = bus


# 装饰器语法糖
def listener(event_type: str, source: str = None):
    """事件监听器装饰器"""
    def decorator(func: Callable):
        bus = get_event_bus()
        bus.subscribe(event_type, func, source)
        return func
    return decorator