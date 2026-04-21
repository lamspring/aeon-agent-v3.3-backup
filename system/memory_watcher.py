#!/usr/bin/env python3
"""
Memory Watcher - 纯观察模式 (修正版)
记录 Gateway 内存趋势，不干预系统
"""

import psutil
import time
import json
from datetime import datetime

LOGFILE = "/var/log/aeon_memory_watch.jsonl"
INTERVAL = 300  # 5分钟

def get_gateway():
    for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
        try:
            cmd = " ".join(proc.info.get('cmdline') or [])
            if "openclaw-gateway" in cmd:
                return {
                    "time": datetime.now().isoformat(),
                    "pid": proc.info["pid"],
                    "rss_mb": proc.info["memory_info"].rss // 1024 // 1024,
                    "vms_mb": proc.info["memory_info"].vms // 1024 // 1024
                }
        except:
            continue
    return None

def main():
    while True:
        info = get_gateway()
        if info:
            with open(LOGFILE, "a") as f:
                f.write(json.dumps(info) + "\n")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
