"""
Agent v30 初始化脚本
Phase 1+2+3: 完整系统
"""

import sys
import os

# 添加路径
sys.path.insert(0, '/root/.openclaw/workspace/agent')

def init_directories():
    """初始化目录结构"""
    dirs = [
        '/root/.openclaw/workspace/agent/bus',
        '/root/.openclaw/workspace/agent/cognition',
        '/root/.openclaw/workspace/agent/memory',
        '/root/.openclaw/workspace/agent/tasks',
        '/root/.openclaw/workspace/agent/utils',
        '/root/.openclaw/workspace/agent/logs',
        '/root/.openclaw/workspace/agent/db',
        '/root/.openclaw/workspace/agent/tests',
    ]
    
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    
    print("✅ 目录结构初始化完成")


def init_logger():
    """初始化日志系统"""
    from utils.structured_log import get_logger
    
    logger = get_logger()
    
    print("✅ 结构化日志初始化完成")
    
    return logger


def init_event_bus():
    """初始化事件总线"""
    from bus.event_bus import get_event_bus
    
    bus = get_event_bus()
    
    # 恢复未处理事件
    bus.restore_unprocessed()
    
    print("✅ 事件总线初始化完成")
    
    return bus


def init_memory():
    """初始化记忆系统"""
    from memory.memory_index import get_memory_index
    from memory.memory_buffer import get_memory_buffer
    
    # 初始化记忆索引
    memory_index = get_memory_index()
    
    # 初始化写入缓冲区
    memory_buffer = get_memory_buffer()
    
    print("✅ 记忆系统初始化完成")
    
    return memory_index, memory_buffer


def init_task_system():
    """初始化任务系统"""
    from tasks.task_system import TaskQueue, TaskWatchdog, Worker
    from tasks.action_handlers import register_standard_handlers
    
    queue = TaskQueue()
    
    # 创建Worker
    worker = Worker("main_worker")
    register_standard_handlers(worker)
    queue.register_worker(worker)
    
    # 启动看门狗
    watchdog = TaskWatchdog(check_interval=60, heartbeat_timeout=300)
    watchdog.start()
    
    print("✅ 任务系统初始化完成")
    
    return queue, watchdog, worker


def init_task_planner():
    """初始化任务规划器"""
    from tasks.task_planner import get_planner
    
    planner = get_planner()
    
    print("✅ 任务规划器初始化完成")
    
    return planner


def init_cognition():
    """初始化认知循环"""
    from cognition.cognition_loop import get_cognition
    from tasks.task_planner import RuleBasedPlanner
    
    cognition = get_cognition()
    
    # 注册规则处理器 (高频，无需LLM)
    def health_check_handler(observation):
        return RuleBasedPlanner.try_plan("检查系统健康状态")
    
    def backup_handler(observation):
        return RuleBasedPlanner.try_plan("备份工作目录")
    
    cognition.register_rule_handler("health_check", health_check_handler)
    cognition.register_rule_handler("backup", backup_handler)
    
    # 启动认知循环
    cognition.start()
    
    print("✅ 认知循环初始化完成")
    
    return cognition


def main():
    """主函数"""
    print("=" * 50)
    print("Agent v30 - 完整系统初始化")
    print("=" * 50)
    
    # 1. 目录
    init_directories()
    
    # 2. 日志
    logger = init_logger()
    
    # 3. 事件总线
    bus = init_event_bus()
    
    # 4. 记忆系统
    memory_index, memory_buffer = init_memory()
    
    # 5. 任务系统
    queue, watchdog, worker = init_task_system()
    
    # 6. 任务规划器
    planner = init_task_planner()
    
    # 7. 认知循环
    cognition = init_cognition()
    
    print("\n" + "=" * 50)
    print("✅ 完整系统初始化完成!")
    print("=" * 50)
    print("\n已启用模块:")
    print("  [Phase 1]")
    print("  • Event Bus (Rate Limiter + TTL + Deduplication)")
    print("  • Event Persistence (SQLite双队列)")
    print("  • Structured Logging (trace_id/event_id/task_id)")
    print("  • Task System (Watchdog + 状态机 + 心跳)")
    print("  [Phase 2]")
    print("  • Cognition Loop (OODA + IDLE + Context Cache)")
    print("  • Task Planner (Schema校验 + Plan Cache)")
    print("  • Action Handlers (10种标准动作)")
    print("  [Phase 3]")
    print("  • Memory Index (Episodic/Semantic分离)")
    print("  • Vector Index (语义搜索)")
    print("  • Memory Write Buffer (批量写入)")
    print("  • Importance Scoring")
    print("  • Memory Consolidation (每日整合)")
    
    return {
        'bus': bus,
        'memory_index': memory_index,
        'memory_buffer': memory_buffer,
        'queue': queue,
        'watchdog': watchdog,
        'worker': worker,
        'planner': planner,
        'cognition': cognition,
        'logger': logger
    }


if __name__ == "__main__":
    main()