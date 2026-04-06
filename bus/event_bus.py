"""
Event Bus v2.0 - 支持重试机制和TTL的增强版事件总线

核心特性:
- Event Status: pending → processing → done/failed/dead
- Retry Mechanism: MAX_RETRY=3, RETRY_DELAY=60s
- TTL: 按事件类型配置过期时间
- Two-phase ACK: 处理前标记processing，成功后标记done
- Crash Recovery: 启动时重置processing状态

Migration from v1.0:
- 数据库自动迁移（添加新字段）
- API兼容（publish/publish_simple保持不变）
"""

import json
import time
import sqlite3
import threading
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Callable, Optional, Any, Set
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
    
    # Goal 事件 (v3.1 NEW)
    GOAL_CREATED = "goal.created"
    GOAL_ACTIVATED = "goal.activated"
    GOAL_COMPLETED = "goal.completed"
    GOAL_FAILED = "goal.failed"


class EventStatus(Enum):
    """事件状态 (v2.0 NEW)"""
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中
    DONE = "done"            # 完成
    FAILED = "failed"        # 失败（可重试）
    DEAD = "dead"           # 死信（超过重试阈值）
    EXPIRED = "expired"     # 已过期


class EventConfig:
    """事件配置 (v2.0 NEW)"""
    # 重试配置
    MAX_RETRY = 3           # 最大重试次数
    RETRY_DELAY = 60        # 重试间隔（秒）
    
    # TTL 配置（秒）- 按事件类型
    TTL_MAP = {
        # Critical - 长时间保留
        "system.shutdown": 3600,
        "system.critical_error": 86400,
        "system.emergency": 86400,
        
        # High - 中等时间
        "message.received": 300,
        "user.command": 300,
        "user.urgent": 300,
        "task.failed": 600,
        "goal.failed": 600,
        
        # Normal - 短时间
        "task.finished": 300,
        "task.created": 300,
        "task.started": 300,
        "cognition.plan": 120,
        "goal.created": 300,
        "goal.activated": 300,
        "goal.completed": 300,
        
        # Low - 很短时间
        "cognition.reflect": 60,
        "memory.updated": 60,
        "memory.accessed": 60,
        "state.changed": 60,
        
        # Background - 超短时间
        "cognition.tick": 30,
        "heartbeat": 30,
        "system.log": 30,
        
        # 默认
        "default": 300,
    }
    
    @classmethod
    def get_ttl(cls, event_type: str) -> float:
        """获取事件类型的TTL"""
        return cls.TTL_MAP.get(event_type, cls.TTL_MAP["default"])
    
    @classmethod
    def get_priority(cls, event_type: str) -> float:
        """获取事件优先级（用于attention scoring）"""
        priority_map = {
            # Critical (1.0)
            "system.shutdown": 1.0,
            "system.critical_error": 1.0,
            "system.emergency": 1.0,
            
            # High (0.8)
            "message.received": 0.8,
            "user.command": 0.8,
            "user.urgent": 0.8,
            "task.failed": 0.8,
            "task.timeout": 0.8,
            "goal.failed": 0.8,
            
            # Normal (0.5)
            "task.finished": 0.5,
            "task.created": 0.5,
            "task.started": 0.5,
            "cognition.plan": 0.5,
            "memory.created": 0.5,
            "goal.created": 0.5,
            "goal.activated": 0.5,
            "goal.completed": 0.5,
            
            # Low (0.2)
            "cognition.reflect": 0.2,
            "memory.updated": 0.2,
            "memory.accessed": 0.2,
            "state.changed": 0.2,
            
            # Background (0.1)
            "cognition.tick": 0.1,
            "heartbeat": 0.1,
            "system.log": 0.1,
        }
        return priority_map.get(event_type, 0.5)


@dataclass
class Event:
    """事件对象 (v2.0 enhanced)"""
    type: str
    data: Dict[str, Any]
    event_id: str = None
    timestamp: float = None
    ttl: int = 60
    trace_id: str = None
    parent_id: str = None
    source: str = None
    
    # v2.0 NEW fields
    status: str = None          # EventStatus value
    retry_count: int = 0        # 重试次数
    last_error: str = None      # 上次错误信息
    processed_at: float = None  # 处理时间戳
    processing_by: str = None   # 处理者worker_id
    expires_at: float = None    # TTL过期时间
    
    def __post_init__(self):
        if self.event_id is None:
            self.event_id = str(uuid.uuid4())
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.ttl is None:
            self.ttl = 60
        if self.trace_id is None:
            self.trace_id = str(uuid.uuid4())
        
        # v2.0: 自动计算 expires_at
        if self.expires_at is None:
            self.expires_at = self.timestamp + self.ttl
        
        # v2.0: 默认状态
        if self.status is None:
            self.status = EventStatus.PENDING.value
    
    def is_expired(self) -> bool:
        """检查事件是否过期（基于expires_at）"""
        return time.time() > self.expires_at
    
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
            "source": self.source,
            "status": self.status,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "processed_at": self.processed_at,
            "processing_by": self.processing_by,
            "expires_at": self.expires_at,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'Event':
        """从字典创建"""
        ttl = d.get("ttl", 60)
        if ttl is None:
            ttl = 60
        
        # v2.0: 从TTL计算expires_at
        timestamp = d.get("timestamp") or time.time()
        expires_at = d.get("expires_at", timestamp + ttl)
        
        return cls(
            type=d["type"],
            data=d["data"],
            event_id=d.get("event_id"),
            timestamp=timestamp,
            ttl=ttl,
            trace_id=d.get("trace_id"),
            parent_id=d.get("parent_id"),
            source=d.get("source"),
            status=d.get("status", EventStatus.PENDING.value),
            retry_count=d.get("retry_count", 0),
            last_error=d.get("last_error"),
            processed_at=d.get("processed_at"),
            processing_by=d.get("processing_by"),
            expires_at=expires_at,
        )
    
    @classmethod
    def from_db_row(cls, row: tuple) -> 'Event':
        """从数据库行创建"""
        return cls(
            event_id=row[0],
            type=row[1],
            data=json.loads(row[2]) if row[2] else {},
            timestamp=row[3] or time.time(),
            ttl=row[4] or 60,
            trace_id=row[5],
            parent_id=row[6],
            source=row[7],
            status=row[8] or EventStatus.PENDING.value,
            retry_count=row[9] or 0,
            last_error=row[10],
            processed_at=row[11],
            processing_by=row[12],
            expires_at=row[13] or (row[3] or time.time()) + (row[4] or 60),
        )
    
    def get_hash(self) -> int:
        """生成事件指纹(用于去重)"""
        content = f"{self.type}:{json.dumps(self.data, sort_keys=True)}"
        return hash(content)


class RateLimiter:
    """速率限制器（保持不变）"""
    
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
            
            if event_type not in self.counters:
                self.counters[event_type] = []
            
            self.counters[event_type] = [
                t for t in self.counters[event_type] 
                if now - t < 1.0
            ]
            
            if len(self.counters[event_type]) >= limit:
                logger.warning(f"Rate limit exceeded for {event_type}")
                return False
            
            self.counters[event_type].append(now)
            return True


class Deduplicator:
    """去重器（保持不变）"""
    
    def __init__(self, window_seconds: int = 5):
        self.window = window_seconds
        self.recent_events: Dict[int, float] = {}
        self._lock = threading.Lock()
    
    def is_duplicate(self, event: Event) -> bool:
        """检查是否是重复事件"""
        event_hash = event.get_hash()
        now = time.time()
        
        with self._lock:
            cutoff = now - self.window
            self.recent_events = {
                k: v for k, v in self.recent_events.items() 
                if v > cutoff
            }
            
            if event_hash in self.recent_events:
                logger.debug(f"Duplicate event {event.type}, ignoring")
                return True
            
            self.recent_events[event_hash] = now
            return False


class EventStore:
    """事件存储 (v2.0 enhanced with status + retry + TTL)"""
    
    def __init__(self, db_path: str = "/root/.openclaw/workspace/agent/db/events.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._lock = threading.Lock()
    
    def _init_db(self):
        """初始化数据库（v2.0 schema）"""
        with sqlite3.connect(self.db_path) as conn:
            # v2.0: 新schema，支持status/retry/TTL
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
                    status TEXT DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    processed_at REAL,
                    processing_by TEXT,
                    expires_at REAL
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_expires ON events(expires_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_retry ON events(retry_count)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id)")
            
            conn.commit()
            
        # 尝试迁移旧数据（如果存在旧表结构）
        self._migrate_if_needed()
    
    def _migrate_if_needed(self):
        """从v1.0迁移数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(events)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # 检查是否需要迁移（有processed字段但没有status字段）
            if "processed" in columns and "status" not in columns:
                logger.info("Migrating events table from v1.0 to v2.0...")
                
                # 添加新字段
                conn.execute("ALTER TABLE events ADD COLUMN status TEXT DEFAULT 'pending'")
                conn.execute("ALTER TABLE events ADD COLUMN last_error TEXT")
                conn.execute("ALTER TABLE events ADD COLUMN processing_by TEXT")
                conn.execute("ALTER TABLE events ADD COLUMN expires_at REAL")
                
                # 迁移数据
                conn.execute("""
                    UPDATE events SET 
                        status = CASE WHEN processed = 1 THEN 'done' ELSE 'pending' END,
                        expires_at = timestamp + ttl
                """)
                
                conn.commit()
                logger.info("Migration completed")
    
    def store(self, event: Event) -> str:
        """存储事件，返回event_id"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO events 
                       (event_id, type, data, timestamp, ttl, trace_id, parent_id, 
                        source, status, retry_count, last_error, processed_at, 
                        processing_by, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_id,
                        event.type,
                        json.dumps(event.data),
                        event.timestamp,
                        event.ttl,
                        event.trace_id,
                        event.parent_id,
                        event.source,
                        event.status,
                        event.retry_count,
                        event.last_error,
                        event.processed_at,
                        event.processing_by,
                        event.expires_at,
                    )
                )
                conn.commit()
        
        return event.event_id
    
    def get_pending_and_retryable(self, limit: int = 100) -> List[Event]:
        """
        获取待处理事件 + 可重试的失败事件
        只返回未过期的事件
        """
        now = time.time()
        retry_cutoff = now - EventConfig.RETRY_DELAY
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM events
                WHERE (status = 'pending'
                       OR (status = 'failed' 
                           AND retry_count < ?
                           AND processed_at < ?))
                  AND expires_at > ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (EventConfig.MAX_RETRY, retry_cutoff, now, limit))
            
            return [Event.from_db_row(row) for row in cursor.fetchall()]
    
    def get_pending_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取待处理事件（返回字典格式供 Attention System 使用）
        """
        events = self.get_pending_and_retryable(limit=limit)
        return [e.to_dict() for e in events]
    
    def count_pending(self) -> int:
        """统计待处理事件数（用于Trace日志）"""
        now = time.time()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM events
                WHERE status IN ('pending', 'failed')
                  AND expires_at > ?
            """, (now,))
            
            return cursor.fetchone()[0]
    
    def mark_processing(self, event_ids: List[str], worker_id: str):
        """标记为处理中（两阶段ACK的第一步）"""
        now = time.time()
        
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                for event_id in event_ids:
                    conn.execute("""
                        UPDATE events
                        SET status = 'processing',
                            processing_by = ?,
                            processed_at = ?
                        WHERE event_id = ?
                    """, (worker_id, now, event_id))
                conn.commit()
    
    def mark_done(self, event_id: str):
        """标记为完成（两阶段ACK的第二步 - 成功）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE events
                SET status = 'done',
                    processed_at = ?,
                    processing_by = NULL
                WHERE event_id = ?
            """, (time.time(), event_id))
            conn.commit()
    
    def mark_failed(self, event_id: str, error: str, retry_count: int):
        """标记为失败（可重试）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE events
                SET status = 'failed',
                    retry_count = ?,
                    last_error = ?,
                    processed_at = ?,
                    processing_by = NULL
                WHERE event_id = ?
            """, (retry_count, error, time.time(), event_id))
            conn.commit()
    
    def mark_dead(self, event_id: str, error: str, retry_count: int):
        """标记为死信（不再处理）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE events
                SET status = 'dead',
                    retry_count = ?,
                    last_error = ?,
                    processed_at = ?,
                    processing_by = NULL
                WHERE event_id = ?
            """, (retry_count, error, time.time(), event_id))
            conn.commit()
    
    def reset_processing_on_startup(self, worker_id: str = None):
        """
        启动时重置processing状态
        将本worker或所有processing事件重置为failed/dead
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                if worker_id:
                    # 只重置本worker的事件
                    conn.execute("""
                        UPDATE events
                        SET status = CASE 
                                WHEN retry_count >= ? THEN 'dead'
                                ELSE 'failed'
                             END,
                            processing_by = NULL,
                            retry_count = retry_count + 1
                        WHERE status = 'processing' AND processing_by = ?
                    """, (EventConfig.MAX_RETRY, worker_id))
                else:
                    # 重置所有processing（crash recovery）
                    conn.execute("""
                        UPDATE events
                        SET status = CASE 
                                WHEN retry_count >= ? THEN 'dead'
                                ELSE 'failed'
                             END,
                            processing_by = NULL,
                            retry_count = retry_count + 1
                        WHERE status = 'processing'
                    """, (EventConfig.MAX_RETRY,))
                
                updated = conn.total_changes
                conn.commit()
                
                if updated > 0:
                    logger.warning(f"Reset {updated} processing events on startup")
    
    def get_dead_letters(self, limit: int = 10) -> List[Event]:
        """获取死信事件（用于监控告警）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT * FROM events
                WHERE status = 'dead'
                ORDER BY processed_at DESC
                LIMIT ?
            """, (limit,))
            
            return [Event.from_db_row(row) for row in cursor.fetchall()]
    
    def cleanup(self, days_done: int = 30, days_dead: int = 7):
        """
        清理旧事件
        - done: 30天后删除
        - dead: 7天后删除
        - expired: 立即删除
        """
        now = time.time()
        done_cutoff = now - (days_done * 86400)
        dead_cutoff = now - (days_dead * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            # 清理expired
            c0 = conn.execute(
                "DELETE FROM events WHERE status = 'expired' OR expires_at < ?",
                (now,)
            )
            
            # 清理done
            c1 = conn.execute(
                "DELETE FROM events WHERE status = 'done' AND processed_at < ?",
                (done_cutoff,)
            )
            
            # 清理dead
            c2 = conn.execute(
                "DELETE FROM events WHERE status = 'dead' AND processed_at < ?",
                (dead_cutoff,)
            )
            
            conn.commit()
            
            total = c0.rowcount + c1.rowcount + c2.rowcount
            if total > 0:
                logger.info(
                    f"Cleanup: {c0.rowcount} expired + {c1.rowcount} done + "
                    f"{c2.rowcount} dead = {total} events deleted"
                )
            
            return total


class EventBus:
    """
    事件总线 v2.0
    
    特性:
    - Rate Limiter (防Event Storm)
    - Deduplication (去重)
    - Persistence (持久化 + 状态机)
    - Retry Mechanism (重试机制)
    - TTL (过期自动清理)
    - Two-phase ACK (两阶段确认)
    """
    
    def __init__(self, 
                 db_path: str = "/root/.openclaw/workspace/agent/db/events.db",
                 enable_persistence: bool = True,
                 worker_id: str = None):
        self.listeners: Dict[str, List[Callable]] = {}
        self.rate_limiter = RateLimiter()
        self.deduplicator = Deduplicator()
        self.store = EventStore(db_path) if enable_persistence else None
        self.worker_id = worker_id or str(uuid.uuid4())[:8]
        self._lock = threading.Lock()
        
        # 启动时恢复状态
        if self.store:
            self.store.reset_processing_on_startup()
        
        logger.info(f"EventBus v2.0 initialized (worker={self.worker_id})")
    
    def subscribe(self, event_type: str, handler: Callable):
        """订阅事件"""
        with self._lock:
            if event_type not in self.listeners:
                self.listeners[event_type] = []
            self.listeners[event_type].append(handler)
            logger.debug(f"Handler subscribed to {event_type}")
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """取消订阅"""
        with self._lock:
            if event_type in self.listeners:
                self.listeners[event_type] = [
                    h for h in self.listeners[event_type] if h != handler
                ]
    
    def publish(self, event: Event) -> str:
        """
        发布事件
        返回event_id
        """
        # 检查去重
        if self.deduplicator.is_duplicate(event):
            return event.event_id
        
        # 设置TTL（如果没有）
        if event.expires_at is None:
            event.ttl = EventConfig.get_ttl(event.type)
            event.expires_at = time.time() + event.ttl
        
        # 持久化
        if self.store:
            try:
                self.store.store(event)
            except Exception as e:
                logger.error(f"Failed to persist event: {e}")
        
        return event.event_id
    
    def publish_simple(self, event_type: str, data: Dict, 
                       trace_id: str = None, parent_id: str = None,
                       source: str = None) -> str:
        """简化发布"""
        ttl = EventConfig.get_ttl(event_type)
        event = Event(
            type=event_type,
            data=data,
            trace_id=trace_id,
            parent_id=parent_id,
            source=source,
            ttl=ttl,
            expires_at=time.time() + ttl,
        )
        return self.publish(event)
    
    def process_pending(self, max_events: int = 5) -> int:
        """
        处理待处理事件（由CognitionLoop调用）
        返回处理的事件数
        """
        if not self.store:
            return 0
        
        # 1. 获取待处理事件
        events = self.store.get_pending_and_retryable(limit=max_events)
        
        if not events:
            return 0
        
        # 2. 标记为processing（两阶段ACK）
        event_ids = [e.event_id for e in events]
        self.store.mark_processing(event_ids, self.worker_id)
        
        processed_count = 0
        
        # 3. 逐个处理
        for event in events:
            # 检查过期
            if event.is_expired():
                logger.debug(f"Event {event.event_id} expired, skipping")
                continue
            
            # 检查速率限制
            if not self.rate_limiter.check(event.type):
                logger.warning(f"Rate limit for {event.type}, deferring")
                continue
            
            try:
                # 分发到监听器
                handlers = self.listeners.get(event.type, [])
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception as e:
                        logger.error(f"Handler error for {event.type}: {e}")
                
                # 标记为done（成功）
                self.store.mark_done(event.event_id)
                processed_count += 1
                
            except Exception as e:
                # 处理失败，递增重试计数
                retry_count = (event.retry_count or 0) + 1
                
                if retry_count >= EventConfig.MAX_RETRY:
                    # 超过阈值，标记为dead
                    self.store.mark_dead(event.event_id, str(e), retry_count)
                    logger.error(
                        f"Event {event.event_id} marked as DEAD after "
                        f"{retry_count} retries: {e}"
                    )
                else:
                    # 可重试，标记为failed
                    self.store.mark_failed(event.event_id, str(e), retry_count)
                    logger.warning(
                        f"Event {event.event_id} failed, retry {retry_count}/"
                        f"{EventConfig.MAX_RETRY}: {e}"
                    )
        
        return processed_count
    
    def get_queue_size(self) -> int:
        """获取队列大小（用于Trace日志）"""
        if self.store:
            return self.store.count_pending()
        return 0
    
    def get_dead_letters(self, limit: int = 10) -> List[Event]:
        """获取死信事件"""
        if self.store:
            return self.store.get_dead_letters(limit)
        return []
    
    def cleanup(self, days_done: int = 30, days_dead: int = 7):
        """清理旧数据"""
        if self.store:
            self.store.cleanup(days_done, days_dead)


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
def listener(event_type: str):
    """事件监听器装饰器"""
    def decorator(func: Callable):
        bus = get_event_bus()
        bus.subscribe(event_type, func)
        return func
    return decorator


# 监控函数（用于告警）
def monitor_dead_letters(db_path: str = "/root/.openclaw/workspace/agent/db/events.db") -> List[Event]:
    """监控死信事件"""
    store = EventStore(db_path)
    dead_events = store.get_dead_letters(limit=10)
    
    if dead_events:
        logger.error(f"ALERT: {len(dead_events)} dead letter events detected!")
        for e in dead_events:
            logger.error(f"  Dead: {e.event_id} | {e.type} | {e.last_error}")
    
    return dead_events
