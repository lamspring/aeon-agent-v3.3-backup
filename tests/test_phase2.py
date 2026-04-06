"""
Phase 2 测试 - Cognition Loop + Task Planner + Action Handlers
"""

import sys
import time
import os

sys.path.insert(0, '/root/.openclaw/workspace/agent')

from cognition.cognition_loop import CognitionLoop, ContextCache, Observation, Plan, CognitionState
from tasks.task_planner import TaskPlanner, TaskDefinition, PlanOutput, RuleBasedPlanner
from tasks.action_handlers import ActionHandlers
from tasks.task_system import Task, TaskStatus


def test_context_cache():
    """测试上下文缓存"""
    print("\n=== 测试 Context Cache ===")
    
    cache = ContextCache()
    
    # 更新缓存
    cache.update(
        events=[{"type": "test", "timestamp": time.time()}],
        tasks=[{"task_id": "t1", "status": "running"}],
        goal={"description": "测试目标"}
    )
    
    assert cache.has_active_tasks()
    assert cache.has_current_goal()
    assert not cache.is_stale()
    
    print("  ✅ Context Cache 工作正常")


def test_cognition_idle():
    """测试IDLE状态检测"""
    print("\n=== 测试 Cognition IDLE ===")
    
    # 创建短idle超时的cognition
    cognition = CognitionLoop(
        tick_interval=1,
        idle_timeout=2,  # 2秒无活动进入IDLE
        enable_llm=False
    )
    
    # 第一次tick，应该活跃
    cognition.context_cache.update(events=[{"timestamp": time.time()}])
    cognition.last_activity = time.time()
    
    is_idle = cognition._is_idle()
    print(f"  刚有活动，IDLE={is_idle}")
    assert not is_idle
    
    # 等待3秒
    print("  等待3秒...")
    time.sleep(3)
    
    # 清空缓存
    cognition.context_cache = ContextCache()
    
    is_idle = cognition._is_idle()
    print(f"  3秒后无活动，IDLE={is_idle}")
    assert is_idle
    
    print("  ✅ IDLE状态检测工作正常")


def test_rule_based_planner():
    """测试基于规则的规划器"""
    print("\n=== 测试 RuleBasedPlanner ===")
    
    # 测试健康检查规则
    plan = RuleBasedPlanner.try_plan("检查系统健康状态")
    assert plan is not None
    assert len(plan.tasks) == 1
    assert plan.tasks[0].action == "run_command"
    print(f"  ✅ 健康检查规则匹配: {plan.tasks[0].description}")
    
    # 测试备份规则
    plan = RuleBasedPlanner.try_plan("备份工作目录")
    assert plan is not None
    print(f"  ✅ 备份规则匹配: {plan.tasks[0].description}")
    
    # 测试不匹配
    plan = RuleBasedPlanner.try_plan("一些不相关的任务")
    assert plan is None
    print(f"  ✅ 不匹配时返回None")


def test_task_definition_schema():
    """测试任务定义Schema校验"""
    print("\n=== 测试 TaskDefinition Schema ===")
    
    # 有效任务
    task = TaskDefinition(
        action="create_file",
        params={"path": "/tmp/test.txt", "content": "hello"},
        description="创建测试文件",
        retry=3,
        timeout=120
    )
    print(f"  ✅ 有效任务创建成功: {task.id}")
    
    # 无效action
    try:
        task = TaskDefinition(
            action="invalid_action",
            params={},
            description="无效动作"
        )
        assert False, "应该抛出验证错误"
    except Exception as e:
        print(f"  ✅ 无效action被拦截: {type(e).__name__}")
    
    # 无效retry
    try:
        task = TaskDefinition(
            action="wait",
            params={"seconds": 1},
            description="等待",
            retry=10  # 超过最大值5
        )
        assert False, "应该抛出验证错误"
    except Exception as e:
        print(f"  ✅ 无效retry被拦截: {type(e).__name__}")


def test_action_handlers():
    """测试动作处理器"""
    print("\n=== 测试 Action Handlers ===")
    
    test_file = "/tmp/test_action_handler.txt"
    
    # 1. 创建文件
    result = ActionHandlers.create_file({
        "path": test_file,
        "content": "Hello World"
    })
    assert result["status"] == "success"
    print(f"  ✅ create_file: {result['path']}")
    
    # 2. 读取文件
    result = ActionHandlers.read_file({"path": test_file})
    assert result["content"] == "Hello World"
    print(f"  ✅ read_file: {len(result['content'])} bytes")
    
    # 3. 更新文件
    result = ActionHandlers.update_file({
        "path": test_file,
        "content": " Updated",
        "mode": "append"
    })
    assert result["status"] == "success"
    print(f"  ✅ update_file (append)")
    
    # 4. 删除文件
    result = ActionHandlers.delete_file({"path": test_file})
    assert result["status"] == "success"
    print(f"  ✅ delete_file")
    
    # 5. 等待
    start = time.time()
    result = ActionHandlers.wait({"seconds": 0.5})
    elapsed = time.time() - start
    assert elapsed >= 0.5
    print(f"  ✅ wait: {elapsed:.2f}s")
    
    # 6. 运行命令
    result = ActionHandlers.run_command({
        "command": "echo 'hello from subprocess'",
        "timeout": 5
    })
    assert result["status"] == "success"
    assert "hello from subprocess" in result["stdout"]
    print(f"  ✅ run_command: {result['stdout'].strip()}")


def test_cognition_observation():
    """测试认知循环观察阶段"""
    print("\n=== 测试 Cognition Observation ===")
    
    cognition = CognitionLoop(enable_llm=False)
    
    # 设置一些测试数据
    cognition.context_cache.update(
        events=[{"type": "message", "timestamp": time.time()}],
        tasks=[{"task_id": "t1", "status": "pending"}],
        goal={"description": "测试目标", "trace_id": "trace-001"}
    )
    
    # 观察
    observation = cognition._observe()
    
    assert len(observation.events) >= 0
    assert len(observation.tasks) >= 0
    assert observation.goal is not None
    assert observation.environment["tick_count"] == 0
    
    print(f"  ✅ 观察到 {len(observation.events)} 个事件")
    print(f"  ✅ 观察到 {len(observation.tasks)} 个任务")
    print(f"  ✅ 当前目标: {observation.goal['description']}")


def test_plan_cache():
    """测试规划缓存"""
    print("\n=== 测试 Plan Cache ===")
    
    from cognition.cognition_loop import PlanCache, Plan
    
    cache = PlanCache(ttl=2)  # 2秒TTL便于测试
    
    # 创建测试plan
    plan = Plan(
        plan_id="test-001",
        goal="测试目标",
        steps=[{"action": "wait", "params": {}}],
        estimated_time=5,
        created_at=time.time()
    )
    
    # 存入缓存
    cache.set("测试目标", plan)
    
    # 获取缓存
    cached = cache.get("测试目标")
    assert cached is not None
    assert cached.plan_id == plan.plan_id
    print(f"  ✅ 缓存命中: {cached.plan_id}")
    
    # 等待过期
    print("  等待2秒让缓存过期...")
    time.sleep(2.5)
    
    cached = cache.get("测试目标")
    assert cached is None
    print(f"  ✅ 缓存已过期")


def test_full_workflow():
    """测试完整工作流"""
    print("\n=== 测试完整工作流 ===")
    
    from bus.event_bus import EventBus, EventType
    from tasks.task_system import TaskQueue, TaskWatchdog, Worker, TaskPersistence
    from tasks.action_handlers import register_standard_handlers
    import tempfile
    
    # 使用临时数据库避免冲突
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # 1. 创建组件
        bus = EventBus(enable_persistence=False)
        
        # 使用临时数据库
        persistence = TaskPersistence(db_path=db_path)
        queue = TaskQueue()
        queue.persistence = persistence
        
        watchdog = TaskWatchdog(check_interval=1, heartbeat_timeout=2)
        worker = Worker("test_worker")
        register_standard_handlers(worker)
        queue.register_worker(worker)
        
        # 2. 启动看门狗
        watchdog.start()
        
        # 3. 手动添加任务
        task = Task(
            action="create_file",
            params={
                "path": "/tmp/workflow_test.txt",
                "content": "Workflow test"
            },
            description="工作流测试任务"
        )
        
        task_id = queue.add_task(task)
        print(f"  ✅ 任务已添加: {task_id}")
        
        # 4. 处理任务
        queue.process_next()
        
        time.sleep(0.5)
        
        # 5. 验证结果
        assert os.path.exists("/tmp/workflow_test.txt"), "文件未创建"
        with open("/tmp/workflow_test.txt") as f:
            content = f.read()
        assert content == "Workflow test", f"内容不匹配: {content}"
        
        print(f"  ✅ 任务执行成功，文件已创建")
        
        # 清理
        os.remove("/tmp/workflow_test.txt")
        
    finally:
        watchdog.stop()
        # 删除临时数据库
        if os.path.exists(db_path):
            os.remove(db_path)


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Phase 2 测试开始")
    print("=" * 50)
    
    tests = [
        test_context_cache,
        test_cognition_idle,
        test_rule_based_planner,
        test_task_definition_schema,
        test_action_handlers,
        test_cognition_observation,
        test_plan_cache,
        test_full_workflow,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)