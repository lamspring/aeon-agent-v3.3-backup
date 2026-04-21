#!/usr/bin/env python3
"""Health Check Wrapper - 持续运行的健康检查"""
import sys
import time
sys.path.insert(0, '/root/.openclaw/workspace/agent')
from system.health_check import HealthChecker

hc = HealthChecker(interval=60)
hc.start()

# 保持运行
try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    hc.stop()
