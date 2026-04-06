#!/usr/bin/env python3
"""
Async Task Runner - 异步任务执行器

防阻塞 + 并发限制：
  - 超时保护 (默认60s)
  - 并发限制 (默认3个)
  - 防止API洪水
"""
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from system.logger import logger

class AsyncTaskRunner:
    """
    异步任务执行器
    
    特性:
      - 超时保护: 防止单个任务卡住
      - 并发限制: 最多同时运行N个任务
      - 异常捕获: 任务出错不影响主循环
    """
    
    def __init__(self, timeout=60, max_concurrent=3):
        """
        初始化
        
        Args:
            timeout: 任务超时时间(秒)
            max_concurrent: 最大并发数
        """
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        
        logger.system_event("AsyncTaskRunner", f"initialized with timeout={timeout}s, max_concurrent={max_concurrent}")
    
    async def run_task(self, task_func, *args, task_id="", **kwargs):
        """
        运行任务，带并发限制和超时保护
        
        Args:
            task_func: 任务函数
            *args: 位置参数
            task_id: 任务ID
            **kwargs: 关键字参数
            
        Returns:
            dict: {"status": "success/timeout/error", "result": ..., "error": ...}
        """
        start_time = datetime.now()
        
        async with self.semaphore:  # 并发限制
            logger.task_start(task_id or "unknown", str(task_func.__name__))
            
            try:
                loop = asyncio.get_event_loop()
                
                # 在线程池中运行，避免阻塞主循环
                if asyncio.iscoroutinefunction(task_func):
                    # 如果是async函数，直接await
                    future = task_func(*args, **kwargs)
                else:
                    # 如果是普通函数，在线程池中运行
                    future = loop.run_in_executor(
                        self.executor,
                        functools.partial(task_func, *args, **kwargs)
                    )
                
                # 等待结果，带超时
                result = await asyncio.wait_for(future, timeout=self.timeout)
                
                duration = (datetime.now() - start_time).total_seconds()
                logger.task_finish(task_id or "unknown", f"success in {duration:.1f}s")
                
                return {
                    "status": "success",
                    "result": result,
                    "duration": duration,
                    "task_id": task_id
                }
                
            except asyncio.TimeoutError:
                logger.task_timeout(task_id or "unknown", self.timeout)
                return {
                    "status": "timeout",
                    "error": f"Task exceeded {self.timeout}s timeout",
                    "task_id": task_id
                }
                
            except Exception as e:
                logger.task_error(task_id or "unknown", str(e))
                return {
                    "status": "error",
                    "error": str(e),
                    "task_id": task_id
                }
    
    async def run_tasks_concurrent(self, tasks, task_id_prefix="batch"):
        """
        并发运行多个任务，但受限于semaphore
        
        Args:
            tasks: [(func, args, kwargs), ...]
            task_id_prefix: 任务ID前缀
            
        Returns:
            list: 每个任务的结果
        """
        async def run_with_index(index, task_def):
            func, args, kwargs = task_def
            task_id = f"{task_id_prefix}_{index}"
            return await self.run_task(func, *args, task_id=task_id, **kwargs)
        
        # 创建所有任务的coroutine
        coroutines = [run_with_index(i, task_def) for i, task_def in enumerate(tasks)]
        
        # 同时执行，但受semaphore限制
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        return results
    
    def shutdown(self):
        """关闭执行器"""
        self.executor.shutdown(wait=True)
        logger.system_event("AsyncTaskRunner", "shutdown")

# 全局实例
task_runner = AsyncTaskRunner()

# 便捷函数
async def run_with_timeout(func, timeout=60, *args, **kwargs):
    """带超时的便捷函数"""
    runner = AsyncTaskRunner(timeout=timeout)
    return await runner.run_task(func, *args, **kwargs)

if __name__ == "__main__":
    import time
    
    print("=== Async Task Runner Test ===\n")
    
    # 测试1: 正常任务
    def normal_task(x):
        time.sleep(1)
        return x * 2
    
    # 测试2: 超时任务
    def slow_task():
        time.sleep(5)
        return "should not reach here"
    
    # 测试3: 错误任务
    def error_task():
        raise ValueError("Intentional error")
    
    async def main():
        runner = AsyncTaskRunner(timeout=3, max_concurrent=2)
        
        print("Test 1: Normal task")
        result = await runner.run_task(normal_task, 5, task_id="test_normal")
        print(f"  Result: {result}\n")
        
        print("Test 2: Timeout task (3s timeout, 5s sleep)")
        result = await runner.run_task(slow_task, task_id="test_timeout")
        print(f"  Result: {result}\n")
        
        print("Test 3: Error task")
        result = await runner.run_task(error_task, task_id="test_error")
        print(f"  Result: {result}\n")
        
        print("Test 4: Concurrent tasks (5 tasks, max 2 concurrent)")
        tasks = [
            (normal_task, (i,), {}) for i in range(5)
        ]
        results = await runner.run_tasks_concurrent(tasks)
        for i, r in enumerate(results):
            print(f"  Task {i}: {r['status']}")
        
        runner.shutdown()
    
    asyncio.run(main())
    
    print("\n✅ 所有测试完成")
