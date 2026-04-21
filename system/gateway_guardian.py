#!/usr/bin/env python3
"""
Gateway Memory Guardian - Gateway内存守护程序

监控 openclaw-gateway 进程内存，超阈值时自动重启
"""
import subprocess
import time
import logging
from datetime import datetime
from pathlib import Path

# 配置
MEMORY_THRESHOLD_MB = 500  # 内存阈值 500MB
CHECK_INTERVAL = 300  # 每5分钟检查一次
GATEWAY_SERVICE = "openclaw-gateway"
LOG_FILE = Path("/var/log/xiaxia-gateway-guardian.log")

def setup_logging():
    """设置日志"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def get_gateway_memory():
    """获取 Gateway 进程内存 (MB)"""
    try:
        # 查找 Gateway 进程
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        for line in result.stdout.split('\n'):
            if 'openclaw-gateway' in line and 'grep' not in line:
                parts = line.split()
                if len(parts) >= 6:
                    # RSS 在第6列 (KB)
                    rss_kb = int(parts[5])
                    rss_mb = rss_kb / 1024
                    pid = parts[1]
                    return pid, rss_mb
        
        return None, 0
    except Exception as e:
        logger.error(f"获取内存失败: {e}")
        return None, 0

def restart_gateway():
    """重启 Gateway 服务"""
    try:
        logger.warning("正在重启 Gateway...")
        
        # 先优雅停止
        subprocess.run(
            ["systemctl", "stop", GATEWAY_SERVICE],
            capture_output=True,
            timeout=10
        )
        
        time.sleep(2)
        
        # 启动
        subprocess.run(
            ["systemctl", "start", GATEWAY_SERVICE],
            capture_output=True,
            timeout=10
        )
        
        time.sleep(3)
        
        # 检查状态
        result = subprocess.run(
            ["systemctl", "is-active", GATEWAY_SERVICE],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if "active" in result.stdout:
            logger.info("Gateway 重启成功！")
            return True
        else:
            logger.error("Gateway 重启失败！")
            return False
            
    except Exception as e:
        logger.error(f"重启失败: {e}")
        return False

def main_loop():
    """主循环"""
    logger.info(f"Gateway Guardian 启动 - 阈值: {MEMORY_THRESHOLD_MB}MB, 检查间隔: {CHECK_INTERVAL}s")
    
    while True:
        try:
            pid, memory_mb = get_gateway_memory()
            
            if pid:
                logger.info(f"Gateway PID={pid}, 内存={memory_mb:.1f}MB")
                
                if memory_mb > MEMORY_THRESHOLD_MB:
                    logger.warning(f"内存超限！{memory_mb:.1f}MB > {MEMORY_THRESHOLD_MB}MB")
                    restart_gateway()
                else:
                    logger.debug(f"内存正常: {memory_mb:.1f}MB")
            else:
                logger.warning("未找到 Gateway 进程")
                # 尝试启动
                restart_gateway()
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("收到中断信号，退出...")
            break
        except Exception as e:
            logger.error(f"主循环错误: {e}")
            time.sleep(60)

if __name__ == "__main__":
    logger = setup_logging()
    main_loop()
