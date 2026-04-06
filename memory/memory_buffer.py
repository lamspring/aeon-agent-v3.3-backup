"""
Memory Write Buffer - 记忆批量写入
核心特性:
- 批量写入减少API调用
- 自动刷新 (时间/数量阈值)
- 系统关闭前强制刷新
"""

import time
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from memory.memory_index import MemoryEntry, MemoryIndex, get_memory_index
from utils.structured_log import get_logger

logger = get_logger()


@dataclass
class BufferedMemory:
    """缓冲的记忆项"""
    content: str
    metadata: Dict[str, Any]
    tags: List[str]
    added_at: float


class MemoryWriteBuffer:
    """
    记忆写入缓冲区
    
    批量处理记忆写入，减少API调用次数
    """
    
    def __init__(self,
                 memory_index: MemoryIndex = None,
                 flush_interval: int = 30,      # 30秒自动刷新
                 max_batch_size: int = 10,      # 最多10条批量写入
                 max_buffer_size: int = 100):   # 缓冲区最大容量
        
        self.memory_index = memory_index or get_memory_index()
        self.flush_interval = flush_interval
        self.max_batch_size = max_batch_size
        self.max_buffer_size = max_buffer_size
        
        self.buffer: List[BufferedMemory] = []
        self.last_flush = time.time()
        self._lock = threading.Lock()
        self._flush_thread = None
        self._stop_event = threading.Event()
        
        # 启动自动刷新线程
        self._start_auto_flush()
    
    def _start_auto_flush(self):
        """启动自动刷新线程"""
        self._flush_thread = threading.Thread(target=self._auto_flush_loop, daemon=True)
        self._flush_thread.start()
    
    def _auto_flush_loop(self):
        """自动刷新循环"""
        while not self._stop_event.is_set():
            time.sleep(5)  # 每5秒检查一次
            
            with self._lock:
                if self.buffer:
                    elapsed = time.time() - self.last_flush
                    if elapsed >= self.flush_interval:
                        self._flush_unlocked()
    
    def add(self, content: str, 
            metadata: Dict[str, Any] = None,
            tags: List[str] = None) -> bool:
        """
        添加记忆到缓冲区
        
        Returns:
            bool: 是否触发刷新
        """
        with self._lock:
            # 检查缓冲区是否已满
            if len(self.buffer) >= self.max_buffer_size:
                logger.warning(
                    f"Memory buffer full ({self.max_buffer_size}), forcing flush",
                    component="MemoryWriteBuffer"
                )
                self._flush_unlocked()
            
            # 添加到缓冲区
            self.buffer.append(BufferedMemory(
                content=content,
                metadata=metadata or {},
                tags=tags or [],
                added_at=time.time()
            ))
            
            buffer_size = len(self.buffer)
            
            # 检查是否达到批量阈值
            if buffer_size >= self.max_batch_size:
                self._flush_unlocked()
                return True
        
        return False
    
    def flush(self):
        """强制刷新缓冲区"""
        with self._lock:
            return self._flush_unlocked()
    
    def _flush_unlocked(self) -> int:
        """
        执行刷新 (已加锁)
        
        Returns:
            int: 写入的记忆数量
        """
        if not self.buffer:
            return 0
        
        count = len(self.buffer)
        
        logger.info(
            f"Flushing {count} memories to index",
            component="MemoryWriteBuffer"
        )
        
        # 批量计算嵌入
        contents = [m.content for m in self.buffer]
        embeddings = self.memory_index.embedding.encode_batch(contents)
        
        # 批量写入
        for i, buffered in enumerate(self.buffer):
            self.memory_index.store_episodic(
                content=buffered.content,
                metadata=buffered.metadata,
                tags=buffered.tags,
                embedding=embeddings[i]
            )
        
        # 清空缓冲区
        self.buffer = []
        self.last_flush = time.time()
        
        logger.info(
            f"Batch write complete: {count} memories",
            component="MemoryWriteBuffer",
            context={"count": count}
        )
        
        return count
    
    def force_flush(self):
        """强制刷新 (系统关闭前调用)"""
        logger.info("Force flushing memory buffer", component="MemoryWriteBuffer")
        return self.flush()
    
    def stop(self):
        """停止缓冲区"""
        logger.info("Stopping memory write buffer", component="MemoryWriteBuffer")
        self._stop_event.set()
        
        # 强制刷新剩余数据
        self.force_flush()
        
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓冲区统计"""
        with self._lock:
            return {
                "buffer_size": len(self.buffer),
                "max_batch_size": self.max_batch_size,
                "flush_interval": self.flush_interval,
                "last_flush": self.last_flush,
                "next_flush_in": max(0, self.flush_interval - (time.time() - self.last_flush))
            }


# 装饰器: 自动缓冲记忆
def buffered_memory(flush_interval: int = 30, max_batch_size: int = 10):
    """
    装饰器: 自动使用缓冲写入记忆
    
    用法:
        @buffered_memory(flush_interval=30)
        def on_message(event):
            return {
                "content": f"Message: {event['message']}",
                "tags": ["message"]
            }
    """
    def decorator(func):
        buffer = MemoryWriteBuffer(
            flush_interval=flush_interval,
            max_batch_size=max_batch_size
        )
        
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            if result:
                if isinstance(result, dict):
                    buffer.add(
                        content=result.get('content', ''),
                        metadata=result.get('metadata', {}),
                        tags=result.get('tags', [])
                    )
                elif isinstance(result, list):
                    for item in result:
                        buffer.add(
                            content=item.get('content', ''),
                            metadata=item.get('metadata', {}),
                            tags=item.get('tags', [])
                        )
            
            return result
        
        wrapper._buffer = buffer
        return wrapper
    
    return decorator


# 全局缓冲区实例
_buffer_instance: Optional[MemoryWriteBuffer] = None


def get_memory_buffer() -> MemoryWriteBuffer:
    """获取全局记忆写入缓冲区"""
    global _buffer_instance
    if _buffer_instance is None:
        _buffer_instance = MemoryWriteBuffer()
    return _buffer_instance


def set_memory_buffer(buffer: MemoryWriteBuffer):
    """设置全局记忆写入缓冲区"""
    global _buffer_instance
    _buffer_instance = buffer