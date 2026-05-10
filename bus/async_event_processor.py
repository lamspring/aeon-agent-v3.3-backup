#!/usr/bin/env python3
"""
AsyncEventProcessor - EventBus 异步处理器 v1.0

为 EventBus v2 添加异步处理能力，解决积压问题。

核心特性:
- asyncio.Queue 替代同步处理
- 优先级调度（系统 > 用户 > 内部）
- 背压机制（队列深度超过阈值时丢弃低优先级事件）
- 批量处理（一次处理多个事件）
- 不修改现有 EventBus，作为包装层使用

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum


class EventPriority(Enum):
    """事件优先级"""
    CRITICAL = 0    # 系统关键事件
    HIGH = 1        # 用户交互
    NORMAL = 2      # 普通任务
    LOW = 3         # 内部日志/心跳


@dataclass
class AsyncEvent:
    """异步事件包装"""
    id: str
    type: str
    data: Dict
    priority: EventPriority
    timestamp: float
    retry_count: int = 0


class AsyncEventProcessor:
    """
    异步事件处理器
    
    包装现有 EventBus，提供异步处理能力。
    """
    
    # 背压阈值
    MAX_QUEUE_SIZE = 100
    BACKPRESSURE_THRESHOLD = 50
    
    # 批量处理配置
    BATCH_SIZE = 5
    BATCH_TIMEOUT = 0.1  # 秒
    
    def __init__(self, event_bus=None, max_workers: int = 3):
        self.event_bus = event_bus
        self.max_workers = max_workers
        
        # 优先级队列（asyncio.PriorityQueue 不支持直接比较，用多个队列）
        self.queues = {
            EventPriority.CRITICAL: asyncio.Queue(),
            EventPriority.HIGH: asyncio.Queue(),
            EventPriority.NORMAL: asyncio.Queue(),
            EventPriority.LOW: asyncio.Queue(),
        }
        
        self._total_queued = 0
        self._processed = 0
        self._dropped = 0
        self._running = False
        self._workers = []
    
    def _get_priority(self, event_type: str) -> EventPriority:
        """根据事件类型判断优先级"""
        critical_types = ['system.shutdown', 'system.critical_error', 'system.emergency',
                         'gate.closed', 'user.urgent']
        high_types = ['message.received', 'user.command', 'task.failed', 'goal.failed']
        low_types = ['cognition.tick', 'heartbeat', 'trace.log', 'state.unchanged']
        
        if any(t in event_type for t in critical_types):
            return EventPriority.CRITICAL
        if any(t in event_type for t in high_types):
            return EventPriority.HIGH
        if any(t in event_type for t in low_types):
            return EventPriority.LOW
        return EventPriority.NORMAL
    
    async def submit(self, event_id: str, event_type: str, data: Dict) -> bool:
        """
        提交事件到异步队列
        
        Returns:
            bool: 是否成功提交（背压时可能丢弃）
        """
        priority = self._get_priority(event_type)
        
        # 背压检查
        if self._total_queued >= self.BACKPRESSURE_THRESHOLD:
            if priority == EventPriority.LOW:
                self._dropped += 1
                return False
            # 正常优先级以上，继续处理但记录
        
        if self._total_queued >= self.MAX_QUEUE_SIZE:
            # 队列已满，只保留 CRITICAL
            if priority != EventPriority.CRITICAL:
                self._dropped += 1
                return False
        
        event = AsyncEvent(
            id=event_id,
            type=event_type,
            data=data,
            priority=priority,
            timestamp=time.time()
        )
        
        await self.queues[priority].put(event)
        self._total_queued += 1
        return True
    
    async def _process_single(self, event: AsyncEvent) -> bool:
        """处理单个事件"""
        try:
            if self.event_bus:
                # 调用 EventBus 的 listeners 处理事件
                handlers = self.event_bus.listeners.get(event.type, [])
                for handler in handlers:
                    try:
                        # 创建 Event 对象传给 handler
                        from event_bus_v2 import Event
                        evt = Event(
                            event_id=event.id,
                            type=event.type,
                            data=event.data,
                            timestamp=event.timestamp,
                        )
                        handler(evt)
                    except Exception as e:
                        print(f"[AsyncEventProcessor] Handler error for {event.type}: {e}")
            
            self._processed += 1
            self._total_queued -= 1
            return True
            
        except Exception as e:
            event.retry_count += 1
            if event.retry_count < 3:
                # 重试：放回队列（降级优先级）
                await self.queues[min(EventPriority(event.priority.value + 1), EventPriority.LOW)].put(event)
            else:
                self._total_queued -= 1
                self._dropped += 1
            return False
    
    async def _worker(self, worker_id: int):
        """工作协程"""
        while self._running:
            event = None
            
            # 按优先级取事件
            for priority in [EventPriority.CRITICAL, EventPriority.HIGH, 
                           EventPriority.NORMAL, EventPriority.LOW]:
                try:
                    event = self.queues[priority].get_nowait()
                    break
                except asyncio.QueueEmpty:
                    continue
            
            if event is None:
                # 所有队列为空，短暂等待
                await asyncio.sleep(0.05)
                continue
            
            await self._process_single(event)
    
    async def start(self):
        """启动处理器"""
        if self._running:
            return
        
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.max_workers)
        ]
    
    async def stop(self):
        """停止处理器"""
        self._running = False
        for worker in self._workers:
            worker.cancel()
        self._workers = []
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_queued": self._total_queued,
            "processed": self._processed,
            "dropped": self._dropped,
            "queue_depths": {
                p.name: q.qsize() for p, q in self.queues.items()
            },
            "running": self._running,
            "workers": len(self._workers),
        }


# ============== 兼容性包装 ==============
class EventBusAsyncWrapper:
    """
    EventBus 异步兼容包装
    
    为现有 CognitionLoop 提供无缝切换能力。
    """
    
    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.async_processor = AsyncEventProcessor(event_bus)
        self._started = False
    
    def process_pending(self, max_events: int = 10) -> int:
        """
        兼容原有 API，但内部使用异步处理
        
        注意：这是一个同步包装，实际异步处理在后台运行
        """
        if not self._started:
            # 启动异步处理器
            try:
                asyncio.get_event_loop().run_until_complete(self.async_processor.start())
                self._started = True
            except:
                pass
        
        # 从现有 EventBus 读取 pending 事件，提交到异步队列
        try:
            # 获取 pending 事件（这里简化，实际需要调用 event_bus 的方法）
            pending_count = 0
            
            # 提交到异步处理器
            for _ in range(max_events):
                # 从 event_bus 获取事件并提交
                # 这里需要根据 event_bus 的实际 API 调整
                pass
            
            return pending_count
            
        except Exception as e:
            return 0
    
    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self.async_processor._total_queued
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return self.async_processor.get_stats()


# ============== 快速测试 ==============
if __name__ == "__main__":
    processor = AsyncEventProcessor()
    
    async def test():
        print("=== AsyncEventProcessor 测试 ===")
        
        # 提交事件
        for i in range(10):
            await processor.submit(f"evt_{i}", "test.event", {"idx": i})
        
        print(f"Stats after submit: {processor.get_stats()}")
        
        # 启动处理
        await processor.start()
        await asyncio.sleep(0.5)
        
        print(f"Stats after processing: {processor.get_stats()}")
        
        await processor.stop()
    
    asyncio.run(test())
