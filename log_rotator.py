#!/usr/bin/env python3
"""
Log Rotator - 日志轮转模块

功能:
- 按天轮转日志文件
- 自动压缩旧日志 (gzip)
- 保留最近 N 天
- 低资源占用 (定时检查)

Usage:
    from log_rotator import LogRotator
    rotator = LogRotator(log_dir="/path/to/logs", retention_days=7)
    rotator.start()  # 后台线程
    
    # 或者在 cron 中调用
    rotator.rotate_now()  # 立即执行一次
"""

import os
import gzip
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
import logging

logger = logging.getLogger(__name__)


class LogRotator:
    """
    日志轮转器
    
    Attributes:
        log_dir: 日志目录
        retention_days: 保留天数 (默认7天)
        check_interval: 检查间隔秒数 (默认1小时)
        patterns: 要轮转的文件模式列表
    """
    
    def __init__(
        self,
        log_dir: str = "/root/.openclaw/workspace/agent/logs",
        retention_days: int = 7,
        check_interval: int = 3600,
        patterns: List[str] = None
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.retention_days = retention_days
        self.check_interval = check_interval
        self.patterns = patterns or ["agent.log", "execution_log.txt", "*.log"]
        
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
    
    def start(self):
        """启动后台轮转线程"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"LogRotator started (retention={self.retention_days}d)")
    
    def stop(self):
        """停止轮转线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("LogRotator stopped")
    
    def _loop(self):
        """主循环"""
        while self._running:
            try:
                self.rotate_now()
            except Exception as e:
                logger.error(f"Log rotation error: {e}")
            
            # 等待下一次检查
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)
    
    def rotate_now(self):
        """
        立即执行轮转
        
        策略:
        1. 检查当前日志文件，如果大于阈值则轮转
        2. 压缩昨天的日志
        3. 删除过期日志
        """
        with self._lock:
            rotated = 0
            compressed = 0
            deleted = 0
            
            # 1. 轮转大文件 (>10MB)
            for pattern in self.patterns:
                for log_file in self.log_dir.glob(pattern):
                    if log_file.is_file() and not log_file.name.endswith('.gz'):
                        size_mb = log_file.stat().st_size / (1024 * 1024)
                        if size_mb > 10:  # 大于 10MB 就轮转
                            if self._rotate_file(log_file):
                                rotated += 1
            
            # 2. 压缩昨天的日志
            yesterday = datetime.now() - timedelta(days=1)
            for log_file in self.log_dir.glob("*.log"):
                if log_file.is_file():
                    # 检查是否是昨天的文件
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime.date() == yesterday.date():
                        if self._compress_file(log_file):
                            compressed += 1
            
            # 3. 删除过期日志
            cutoff = datetime.now() - timedelta(days=self.retention_days)
            for log_file in self.log_dir.glob("*.gz"):
                if log_file.is_file():
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff:
                        log_file.unlink()
                        deleted += 1
            
            # 同时删除未压缩的旧日志
            for log_file in self.log_dir.glob("*.log"):
                if log_file.is_file():
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff:
                        log_file.unlink()
                        deleted += 1
            
            if rotated or compressed or deleted:
                logger.info(
                    f"Log rotation: {rotated} rotated, "
                    f"{compressed} compressed, {deleted} deleted"
                )
            
            return {
                "rotated": rotated,
                "compressed": compressed,
                "deleted": deleted
            }
    
    def _rotate_file(self, log_file: Path) -> bool:
        """
        轮转单个日志文件
        
        重命名为: filename-YYYYMMDD.log
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_name = f"{log_file.stem}-{timestamp}{log_file.suffix}"
            new_path = self.log_dir / new_name
            
            # 复制文件（不是移动，避免影响正在写入的文件）
            shutil.copy2(log_file, new_path)
            
            # 清空原文件
            with open(log_file, 'w'):
                pass
            
            logger.debug(f"Rotated: {log_file.name} -> {new_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rotate {log_file}: {e}")
            return False
    
    def _compress_file(self, log_file: Path) -> bool:
        """压缩日志文件"""
        try:
            gz_path = log_file.with_suffix(log_file.suffix + '.gz')
            
            with open(log_file, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # 删除原文件
            log_file.unlink()
            
            logger.debug(f"Compressed: {log_file.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to compress {log_file}: {e}")
            return False
    
    def get_stats(self) -> dict:
        """获取日志目录统计"""
        total_size = 0
        file_count = 0
        gz_count = 0
        
        for f in self.log_dir.iterdir():
            if f.is_file():
                total_size += f.stat().st_size
                file_count += 1
                if f.suffix == '.gz':
                    gz_count += 1
        
        return {
            "log_dir": str(self.log_dir),
            "file_count": file_count,
            "compressed_count": gz_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "retention_days": self.retention_days,
        }
    
    def cleanup_all(self):
        """清理所有日志（谨慎使用）"""
        with self._lock:
            deleted = 0
            for f in self.log_dir.iterdir():
                if f.is_file() and f.suffix in ['.log', '.gz', '.txt']:
                    f.unlink()
                    deleted += 1
            logger.warning(f"Cleanup all: {deleted} files deleted")
            return deleted


def main():
    """CLI 入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Log Rotator')
    parser.add_argument('--log-dir', default='/root/.openclaw/workspace/agent/logs')
    parser.add_argument('--retention', type=int, default=7, help='Retention days')
    parser.add_argument('--now', action='store_true', help='Rotate immediately')
    parser.add_argument('--stats', action='store_true', help='Show stats')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--cleanup-all', action='store_true', help='Delete all logs (DANGER)')
    
    args = parser.parse_args()
    
    rotator = LogRotator(
        log_dir=args.log_dir,
        retention_days=args.retention
    )
    
    if args.cleanup_all:
        confirm = input("Delete all logs? Type 'yes': ")
        if confirm == 'yes':
            rotator.cleanup_all()
        return
    
    if args.stats:
        import json
        print(json.dumps(rotator.get_stats(), indent=2))
        return
    
    if args.now:
        result = rotator.rotate_now()
        print(f"Rotated: {result}")
        return
    
    if args.daemon:
        rotator.start()
        print(f"LogRotator daemon started (retention={args.retention}d)")
        print("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            rotator.stop()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
