#!/usr/bin/env python3
"""
PerformanceMonitor - Aeon 性能监控 v1.0

埋点采集：
- 每 tick 的耗时（ms）
- 每 tick 处理的事件数
- 内存使用趋势（RSS/VMS）
- 队列大小趋势
- 模块执行时间（Observe/Plan/Act/Reflect 各阶段）

输出：JSON Lines 文件，供后续分析和可视化

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import json
import time
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class PerformanceMonitor:
    """
    性能监控器
    
    轻量级，每个 tick 调用一次 record()，记录关键指标。
    """
    
    LOG_DIR = "/root/.openclaw/workspace/agent/logs/performance"
    
    def __init__(self):
        self.log_dir = Path(self.LOG_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._process = psutil.Process()
        self._last_tick_time = 0
        self._tick_count = 0
    
    def _get_log_file(self) -> Path:
        """获取今天的日志文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.jsonl"
    
    def record(self, tick_id: str, tick_count: int,
               phase_times: Optional[Dict[str, float]] = None,
               events_processed: int = 0,
               tasks_created: int = 0,
               queue_size: int = 0,
               goal_count: int = 0) -> Dict:
        """
        记录一次 tick 的性能数据
        
        Args:
            tick_id: tick 标识
            tick_count: tick 序号
            phase_times: 各阶段耗时 {"observe": 10.5, "plan": 5.2, ...}
            events_processed: 本次处理的事件数
            tasks_created: 创建的任务数
            queue_size: 事件队列大小
            goal_count: 活跃目标数
        
        Returns:
            记录的数据字典
        """
        now = time.time()
        
        # 计算 tick 间隔
        tick_interval = 0
        if self._last_tick_time > 0:
            tick_interval = (now - self._last_tick_time) * 1000  # ms
        self._last_tick_time = now
        self._tick_count = tick_count
        
        # 内存信息
        try:
            mem_info = self._process.memory_info()
            memory_rss_mb = mem_info.rss / 1024 / 1024
            memory_vms_mb = mem_info.vms / 1024 / 1024
        except:
            memory_rss_mb = 0
            memory_vms_mb = 0
        
        # 构建记录
        record = {
            "timestamp": now,
            "datetime": datetime.now().isoformat(),
            "tick_id": tick_id,
            "tick_count": tick_count,
            "tick_interval_ms": round(tick_interval, 2),
            "phase_times": phase_times or {},
            "events_processed": events_processed,
            "tasks_created": tasks_created,
            "queue_size": queue_size,
            "goal_count": goal_count,
            "memory_rss_mb": round(memory_rss_mb, 2),
            "memory_vms_mb": round(memory_vms_mb, 2),
        }
        
        # 写入日志
        try:
            log_file = self._get_log_file()
            with open(log_file, 'a') as f:
                f.write(json.dumps(record) + '\n')
        except Exception as e:
            print(f"[PerformanceMonitor] Write failed: {e}")
        
        return record
    
    def get_summary(self, last_n: int = 100) -> Dict:
        """
        获取最近 N 条记录的摘要统计
        
        Returns:
            {
                "avg_tick_interval": float,
                "avg_memory_rss": float,
                "avg_queue_size": float,
                "max_queue_size": int,
                "total_events_processed": int,
                "records_count": int,
            }
        """
        log_file = self._get_log_file()
        if not log_file.exists():
            return {"error": "no data today"}
        
        records = []
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()[-last_n:]
            records = [json.loads(line) for line in lines]
        except:
            return {"error": "parse failed"}
        
        if not records:
            return {"error": "no records"}
        
        tick_intervals = [r["tick_interval_ms"] for r in records if r["tick_interval_ms"] > 0]
        memory_rss = [r["memory_rss_mb"] for r in records]
        queue_sizes = [r["queue_size"] for r in records]
        events = [r["events_processed"] for r in records]
        
        return {
            "records_count": len(records),
            "avg_tick_interval_ms": round(sum(tick_intervals) / len(tick_intervals), 2) if tick_intervals else 0,
            "max_tick_interval_ms": round(max(tick_intervals), 2) if tick_intervals else 0,
            "avg_memory_rss_mb": round(sum(memory_rss) / len(memory_rss), 2) if memory_rss else 0,
            "max_memory_rss_mb": round(max(memory_rss), 2) if memory_rss else 0,
            "avg_queue_size": round(sum(queue_sizes) / len(queue_sizes), 2) if queue_sizes else 0,
            "max_queue_size": max(queue_sizes) if queue_sizes else 0,
            "total_events_processed": sum(events),
            "time_range": {
                "start": records[0]["datetime"],
                "end": records[-1]["datetime"],
            }
        }
    
    def get_trend(self, metric: str = "memory_rss_mb", last_n: int = 50) -> list:
        """
        获取某个指标的最近趋势
        
        Args:
            metric: 指标名
            last_n: 最近多少条
        
        Returns:
            [(tick_count, value), ...]
        """
        log_file = self._get_log_file()
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()[-last_n:]
            records = [json.loads(line) for line in lines]
            return [(r["tick_count"], r.get(metric, 0)) for r in records]
        except:
            return []


# ============== 快速测试 ==============
if __name__ == "__main__":
    pm = PerformanceMonitor()
    
    # 模拟几次记录
    for i in range(5):
        result = pm.record(
            tick_id=f"test_{i}",
            tick_count=i,
            phase_times={"observe": 50 + i * 2, "plan": 20 + i, "act": 30},
            events_processed=i * 2,
            tasks_created=1,
            queue_size=10 + i,
            goal_count=2
        )
        print(f"Recorded tick {i}: {result['tick_interval_ms']}ms, {result['memory_rss_mb']}MB")
        time.sleep(0.1)
    
    # 查看摘要
    summary = pm.get_summary(last_n=10)
    print(f"\nSummary: {json.dumps(summary, indent=2)}")
    
    # 查看趋势
    trend = pm.get_trend("memory_rss_mb", last_n=5)
    print(f"\nMemory trend: {trend}")
