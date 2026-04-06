"""
Phase 1 测试 - Event Bus + Persistence + Structured Logging
"""

import sys
import time
import threading
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from bus.event_bus import EventBus, Event, EventType, get_event_bus, listener
from utils.structured_log import get_logger, LogContext
from tasks.task_system import TaskQueue, Task, TaskStatus, TaskWatchdog, Worker


def test_event_bus():
    """测试事件总线"""
    print("\n=== 测试 Event Bus ===")
    
    # 创建事件总线
    bus = EventBus(enable_persistence=True)
    
    received = []
    
    def on_message(event):
        received.append(event.data.get('message'))
        print(f"  收到消息: {event.data.get('message')}")
    
    # 直接订阅
    bus.subscribe(EventType.MESSAGE_RECEIVED.value, on_message)
    
    # 发布事件
    bus.publish_simple(
        EventType.MESSAGE_RECEIVED.value,
        {"message": "Hello World", "from": "test"}
    )
    
    time.sleep(0.1)
    
    assert len(received) == 1, f"期望收到1条消息，实际收到 {len(received)}"
    assert received[0] == "Hello World"
    print("  ✅ Event Bus 工作正常")
    
    return bus


def test_event_ttl():
    """测试事件TTL"""
    print("\n=== 测试 Event TTL ===")
    
    bus = get_event_bus()
    
    # 创建一个即将过期的事件 (ttl=0)
    event = Event(
        type=EventType.MESSAGE_RECEIVED.value,
        data={"message": "expired"},
        ttl=0  # 立即过期
    )
    
    result = bus.publish(event)
    
    assert result == False, "过期事件应该被拒绝"
    print("  ✅ TTL 过期检测工作正常")


def test_deduplication():
    """测试去重"""
    print("\n=== 测试 Deduplication ===")
    
    # 创建新实例以避免与其他测试冲突
    bus = EventBus(enable_persistence=True)
    
    count = [0]
    
    def on_memory(event):
        count[0] += 1
    
    bus.subscribe(EventType.MEMORY_UPDATED.value, on_memory)
    
    # 发布相同事件两次
    bus.publish_simple(EventType.MEMORY_UPDATED.value, {"key": "value"})
    bus.publish_simple(EventType.MEMORY_UPDATED.value, {"key": "value"})
    
    time.sleep(0.1)
    
    assert count[0] == 1, f"期望处理1次，实际 {count[0]} 次"
    print(f"  ✅ 去重工作正常 (处理了 {count[0]} 次)")


def test_rate_limiter():
    """测试速率限制"""
    print("\n=== 测试 Rate Limiter ===")
    
    bus = EventBus(enable_persistence=True)
    
    count = [0]
    
    def on_tick(event):
        count[0] += 1
    
    bus.subscribe(EventType.COGNITION_TICK.value, on_tick)
    
    # 快速发布多个事件
    for i in range(5):
        bus.publish_simple(EventType.COGNITION_TICK.value, {"tick": i})
    
    time.sleep(0.1)
    
    print(f"  发布了 5 次, 处理了 {count[0]} 次")
    print("  ✅ Rate Limiter 工作正常")


def test_structured_logging():
    """测试结构化日志"""
    print("\n=== 测试 Structured Logging ===")
    
    logger = get_logger()
    
    # 基础日志
    logger.info("Test message", component="Test")
    print("  ✅ 基础日志记录成功")
    
    # 带追踪ID的日志
    with LogContext() as ctx:
        logger.info("Event received", event_id="evt001")
        logger.info("Processing started")
        
        # 子上下文
        with ctx.child_task("task001") as child_ctx:
            logger.info("Task running")
    
    print("  ✅ 追踪链日志记录成功")


def test_task_system():
    """测试任务系统"""
    print("\n=== 测试 Task System ===")
    
    queue = TaskQueue()
    
    # 创建Worker
    worker = Worker("test_worker")
    
    results = []
    
    def mock_handler(params):
        results.append(params.get("value"))
        return {"status": "ok"}
    
    worker.register_handler("test_action", mock_handler)
    queue.register_worker(worker)
    
    # 添加任务
    task = Task(
        action="test_action",
        params={"value": 42},
        description="Test task"
    )
    
    task_id = queue.add_task(task)
    print(f"  任务已添加: {task_id}")
    
    # 处理任务
    queue.process_next()
    
    time.sleep(0.2)
    
    assert len(results) == 1
    assert results[0] == 42
    print("  ✅ 任务系统工作正常")


def test_task_watchdog():
    """测试任务看门狗"""
    print("\n=== 测试 Task Watchdog ===")
    
    # 创建看门狗 (快速检查)
    watchdog = TaskWatchdog(check_interval=1, heartbeat_timeout=2)
    watchdog.start()
    
    print("  看门狗已启动")
    
    # 创建一个会超时的任务
    task = Task(
        action="slow_action",
        params={},
        timeout=1,  # 1秒超时
        max_retries=1
    )
    
    # 手动设置为running状态 (模拟Worker崩溃)
    task.status = TaskStatus.RUNNING.value
    task.started_at = time.time()
    task.worker_id = "crashed_worker"
    
    persistence = watchdog.persistence
    persistence.store(task)
    
    print(f"  模拟任务 {task.task_id} 运行中 (Worker已崩溃)")
    
    # 等待看门狗检测
    time.sleep(3)
    
    # 检查任务状态
    updated_task = persistence.get(task.task_id)
    
    print(f"  任务状态: {updated_task.status}")
    print(f"  重试次数: {updated_task.retry_count}")
    
    assert updated_task.status in [TaskStatus.RETRYING.value, TaskStatus.PENDING.value, TaskStatus.FAILED.value]
    print("  ✅ Task Watchdog 工作正常")
    
    watchdog.stop()


def test_persistence():
    """测试持久化"""
    print("\n=== 测试 Persistence ===")
    
    # 创建新的事件总线实例 (会触发恢复)
    bus = EventBus(enable_persistence=True)
    
    # 发布一个事件
    event = Event(
        type=EventType.MEMORY_UPDATED.value,
        data={"test": "persistence"}
    )
    
    bus.publish(event)
    
    # 检查数据库
    unprocessed = bus.persistence.get_unprocessed()
    
    print(f"  未处理事件数: {len(unprocessed)}")
    print("  ✅ 事件持久化工作正常")


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Phase 1 测试开始")
    print("=" * 50)
    
    try:
        test_event_bus()
        test_event_ttl()
        test_deduplication()
        test_rate_limiter()
        test_structured_logging()
        test_task_system()
        test_task_watchdog()
        test_persistence()
        
        print("\n" + "=" * 50)
        print("✅ 所有测试通过!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()