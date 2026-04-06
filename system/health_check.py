#!/usr/bin/env python3
"""
Health Checker - 健康检查系统

独立心跳线程：
  - 每60秒写一次心跳文件
  - 外部脚本监控心跳
  - 超时则kill+restart
"""
import os
import threading
import time
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
DEFAULT_HEARTBEAT_FILE = "/tmp/agent_heartbeat"

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

class HealthChecker:
    """
    独立健康检查线程
    
    不依赖主循环，独立运行
    """
    
    def __init__(self, interval=60, heartbeat_file=None, save_state_callback=None):
        """
        初始化
        
        Args:
            interval: 心跳间隔(秒)
            heartbeat_file: 心跳文件路径
            save_state_callback: 保存状态的回调函数
        """
        self.interval = interval
        self.heartbeat_file = Path(heartbeat_file or DEFAULT_HEARTBEAT_FILE)
        self.save_state_callback = save_state_callback
        self.running = False
        self.thread = None
        self.logger = get_logger()
        
        self.logger.info(f"[HEALTH] Initialized: interval={interval}s, file={self.heartbeat_file}")
    
    def start(self):
        """启动健康检查线程"""
        self.running = True
        self.thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.thread.start()
        self.logger.info("[HEALTH] Health checker started")
    
    def stop(self):
        """停止健康检查"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=self.interval + 5)
        self.logger.info("[HEALTH] Health checker stopped")
    
    def _heartbeat_loop(self):
        """心跳循环"""
        # 立即写第一次心跳
        self._write_heartbeat()
        
        while self.running:
            time.sleep(self.interval)
            
            if not self.running:
                break
            
            self._write_heartbeat()
    
    def _write_heartbeat(self):
        """写入心跳"""
        try:
            heartbeat_data = {
                "timestamp": datetime.now().isoformat(),
                "unix_time": time.time(),
                "pid": os.getpid(),
                "status": "alive"
            }
            
            # 写入心跳文件
            with open(self.heartbeat_file, 'w') as f:
                import json
                json.dump(heartbeat_data, f)
            
            # 记录日志（每5次记录一次）
            if not hasattr(self, '_beat_count'):
                self._beat_count = 0
            self._beat_count += 1
            
            if self._beat_count % 5 == 0:
                self.logger.info(f"[HEALTH] Heartbeat #{self._beat_count}")
            
        except Exception as e:
            self.logger.error(f"[HEALTH] Failed to write heartbeat: {e}")
    
    def get_last_heartbeat(self):
        """获取最后一次心跳信息"""
        try:
            if not self.heartbeat_file.exists():
                return None
            
            with open(self.heartbeat_file, 'r') as f:
                import json
                return json.load(f)
        except Exception as e:
            self.logger.error(f"[HEALTH] Failed to read heartbeat: {e}")
            return None
    
    def is_healthy(self, timeout=300):
        """
        检查是否健康
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            bool: True if healthy
        """
        heartbeat = self.get_last_heartbeat()
        
        if not heartbeat:
            return False
        
        last_time = heartbeat.get("unix_time", 0)
        current_time = time.time()
        
        return (current_time - last_time) < timeout

# 外部监控脚本内容
WATCHDOG_SCRIPT = '''#!/bin/bash
# Agent Watchdog - 外部健康监控脚本
# 建议添加到cron: */5 * * * * /usr/local/bin/agent_watchdog.sh

HEARTBEAT_FILE="/tmp/agent_heartbeat"
TIMEOUT=300  # 5分钟超时
AGENT_SERVICE="agent"  # systemd服务名

# 颜色输出
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 检查心跳文件是否存在
if [ ! -f "$HEARTBEAT_FILE" ]; then
    log "${RED}ERROR${NC}: Heartbeat file not found. Agent may not be running."
    
    # 尝试重启
    if systemctl is-active --quiet $AGENT_SERVICE 2>/dev/null; then
        log "${YELLOW}RESTARTING${NC}: Attempting to restart agent..."
        systemctl restart $AGENT_SERVICE
    else
        log "${YELLOW}STARTING${NC}: Attempting to start agent..."
        systemctl start $AGENT_SERVICE
    fi
    exit 1
fi

# 读取最后一次心跳
LAST_HEARTBEAT=$(cat "$HEARTBEAT_FILE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('unix_time', 0))" 2>/dev/null)

if [ -z "$LAST_HEARTBEAT" ] || [ "$LAST_HEARTBEAT" == "0" ]; then
    log "${RED}ERROR${NC}: Failed to parse heartbeat file"
    exit 1
fi

CURRENT_TIME=$(date +%s)
TIME_DIFF=$((CURRENT_TIME - LAST_HEARTBEAT))

if [ $TIME_DIFF -gt $TIMEOUT ]; then
    log "${RED}TIMEOUT${NC}: Agent heartbeat timeout (${TIME_DIFF}s > ${TIMEOUT}s)"
    log "${YELLOW}ACTION${NC}: Killing and restarting agent..."
    
    # 杀死Agent进程
    pkill -f "python3.*heartbeat.py"
    sleep 2
    
    # 使用systemd重启
    systemctl restart $AGENT_SERVICE
    
    exit 1
fi

# 计算分钟数
MINUTES=$((TIME_DIFF / 60))
log "${GREEN}OK${NC}: Agent healthy (last heartbeat: ${MINUTES}m ago)"
exit 0
'''

def install_watchdog():
    """安装外部监控脚本"""
    script_path = Path("/usr/local/bin/agent_watchdog.sh")
    
    try:
        with open(script_path, 'w') as f:
            f.write(WATCHDOG_SCRIPT)
        
        os.chmod(script_path, 0o755)
        print(f"✅ Watchdog script installed: {script_path}")
        print("📋 Add to crontab:")
        print("   */5 * * * * /usr/local/bin/agent_watchdog.sh")
        
        return True
    except PermissionError:
        print("❌ Permission denied. Run with sudo to install watchdog.")
        print("   Or manually create the script:")
        print(f"   sudo tee {script_path} << 'EOF'")
        print(WATCHDOG_SCRIPT)
        print("EOF")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Health Checker")
    parser.add_argument("--test", action="store_true", help="Run test")
    parser.add_argument("--install-watchdog", action="store_true", help="Install external watchdog script")
    parser.add_argument("--interval", type=int, default=5, help="Heartbeat interval for test")
    
    args = parser.parse_args()
    
    if args.install_watchdog:
        install_watchdog()
        exit(0)
    
    print("=== Health Checker Test ===\n")
    
    # 创建健康检查器
    checker = HealthChecker(interval=args.interval)
    
    # 启动
    print("Starting health checker (5 seconds)...")
    checker.start()
    
    # 运行一段时间
    time.sleep(12)
    
    # 检查状态
    print("\nChecking health status...")
    heartbeat = checker.get_last_heartbeat()
    print(f"Last heartbeat: {heartbeat}")
    print(f"Is healthy: {checker.is_healthy()}")
    
    # 停止
    print("\nStopping health checker...")
    checker.stop()
    
    print("\n✅ Health checker test complete")
