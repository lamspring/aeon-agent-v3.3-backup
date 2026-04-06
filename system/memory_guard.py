#!/usr/bin/env python3
"""
Memory Guard - 内存监控守护

防止内存缓慢膨胀导致OOM：
  - 监控内存使用
  - 超过阈值(默认2GB)优雅重启
  - 保存状态后退出
"""
import os
import sys
import time
import threading
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def get_logger():
    """延迟导入logger"""
    try:
        from system.logger import logger
        return logger
    except ImportError:
        class DummyLogger:
            def info(self, msg): print(f"[INFO] {msg}")
            def warning(self, msg): print(f"[WARN] {msg}")
            def error(self, msg): print(f"[ERROR] {msg}")
        return DummyLogger()

class MemoryGuard:
    """
    内存监控守护
    
    定期监控内存使用，超过阈值时优雅重启
    """
    
    # 退出码：42表示优雅重启
    EXIT_CODE_GRACEFUL_RESTART = 42
    
    def __init__(self, max_memory_gb=2, check_interval=60):
        """
        初始化
        
        Args:
            max_memory_gb: 内存阈值(GB)
            check_interval: 检查间隔(秒)
        """
        self.max_memory_bytes = max_memory_gb * 1024 ** 3
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.logger = get_logger()
        
        # 尝试导入psutil
        try:
            import psutil
            self.psutil = psutil
            self.process = psutil.Process(os.getpid())
            self.enabled = True
        except ImportError:
            self.logger.warning("[MEMORY_GUARD] psutil not installed, memory guard disabled")
            self.enabled = False
        
        if self.enabled:
            self.logger.info(f"[MEMORY_GUARD] Initialized: max={max_memory_gb}GB, interval={check_interval}s")
    
    def start(self):
        """启动内存监控线程"""
        if not self.enabled:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        self.logger.info("[MEMORY_GUARD] Monitor started")
    
    def stop(self):
        """停止内存监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                if self.check_memory():
                    # 内存超限，已触发重启
                    break
            except Exception as e:
                self.logger.error(f"[MEMORY_GUARD] Check failed: {e}")
            
            time.sleep(self.check_interval)
    
    def check_memory(self):
        """
        检查内存使用
        
        Returns:
            bool: True if memory exceeded and restart triggered
        """
        if not self.enabled:
            return False
        
        memory_info = self.process.memory_info()
        current_memory = memory_info.rss
        current_gb = current_memory / (1024 ** 3)
        
        # 记录内存使用（每10次检查记录一次）
        if not hasattr(self, '_check_count'):
            self._check_count = 0
        self._check_count += 1
        
        if self._check_count % 10 == 0:
            self.logger.info(f"[MEMORY_GUARD] Current usage: {current_gb:.2f}GB / {self.max_memory_bytes / (1024**3):.0f}GB")
        
        # 检查是否超过阈值
        if current_memory > self.max_memory_bytes:
            self.logger.warning(f"[MEMORY_GUARD] ⚠️  Memory exceeded: {current_gb:.2f}GB > {self.max_memory_bytes / (1024**3):.0f}GB")
            self.graceful_restart()
            return True
        
        return False
    
    def graceful_restart(self):
        """优雅重启：保存状态后退出"""
        self.logger.warning("[MEMORY_GUARD] Starting graceful restart...")
        
        try:
            # 1. 保存所有状态
            self._save_all_state()
            
            # 2. 记录重启原因
            self.logger.info("[MEMORY_GUARD] State saved, preparing to restart")
            
            # 3. 标记为优雅重启
            restart_marker = AGENT_DIR / "system" / ".graceful_restart"
            with open(restart_marker, 'w') as f:
                f.write(f"Memory threshold exceeded at {time.time()}")
            
            # 4. 退出（守护进程会自动重启）
            self.logger.info("[MEMORY_GUARD] Exiting with code 42 (graceful restart)")
            os._exit(self.EXIT_CODE_GRACEFUL_RESTART)
            
        except Exception as e:
            self.logger.error(f"[MEMORY_GUARD] Graceful restart failed: {e}")
            # 即使保存失败也要重启，避免OOM
            os._exit(self.EXIT_CODE_GRACEFUL_RESTART)
    
    def _save_all_state(self):
        """保存所有状态"""
        # 保存环境状态
        try:
            from system.world_input import WorldInput
            world = WorldInput()
            world.collect()
            self.logger.info("[MEMORY_GUARD] Environment state saved")
        except Exception as e:
            self.logger.error(f"[MEMORY_GUARD] Failed to save environment: {e}")
        
        # 保存任务队列
        try:
            import sys
            sys.path.insert(0, str(AGENT_DIR / "tasks"))
            from queue import TaskQueue
            queue = TaskQueue()
            queue.save_state()
            self.logger.info("[MEMORY_GUARD] Task queue saved")
        except Exception as e:
            self.logger.error(f"[MEMORY_GUARD] Failed to save task queue: {e}")
        
        # 保存Agent状态
        try:
            from system.cold_start_recovery import ColdStartRecovery
            recovery = ColdStartRecovery()
            recovery.save_state({
                "restart_reason": "memory_threshold",
                "timestamp": time.time()
            })
            self.logger.info("[MEMORY_GUARD] Recovery state saved")
        except Exception as e:
            self.logger.error(f"[MEMORY_GUARD] Failed to save recovery state: {e}")
    
    def get_memory_info(self):
        """获取内存信息"""
        if not self.enabled:
            return {"enabled": False}
        
        memory_info = self.process.memory_info()
        
        return {
            "enabled": True,
            "rss_gb": round(memory_info.rss / (1024 ** 3), 2),
            "vms_gb": round(memory_info.vms / (1024 ** 3), 2),
            "threshold_gb": round(self.max_memory_bytes / (1024 ** 3), 2),
            "percent": round(memory_info.rss / self.max_memory_bytes * 100, 1)
        }

if __name__ == "__main__":
    import sys
    
    # 如果带 --daemon 参数，启动守护模式
    if "--daemon" in sys.argv:
        print("[MEMORY_GUARD] Starting daemon mode...")
        guard = MemoryGuard(max_memory_gb=2, check_interval=60)
        guard.start()
        # 保持主程序运行
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("[MEMORY_GUARD] Stopping...")
            guard.stop()
    else:
        # 测试模式
        print("=== Memory Guard Test ===\n")
        
        guard = MemoryGuard(max_memory_gb=2, check_interval=10)
        
        # 显示当前内存
        info = guard.get_memory_info()
        print(f"Memory info: {info}")
        
        # 测试手动检查
        print("\nManual check...")
        exceeded = guard.check_memory()
        print(f"Memory exceeded: {exceeded}")
        
        print("\n✅ Memory guard test complete")
        print("Note: To run as daemon, use: python3 memory_guard.py --daemon")
