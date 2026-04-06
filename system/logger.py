#!/usr/bin/env python3
"""
Logger - 分级日志系统 (v2.0 - 统一使用 StructuredLog)

向后兼容接口，内部使用 utils.structured_log

防止"悄悄变傻"，追踪Agent的思维过程：
  - agent.log: 核心事件
  - error.log: 异常错误
  - action.log: 任务执行记录
  - reflection.log: 自我反思
  - heartbeat.log: 周期状态

关键事件:
  - task start/finish/timeout
  - memory write
  - state change
"""
import sys
from datetime import datetime
from pathlib import Path

# 统一使用 structured_log
sys.path.insert(0, '/root/.openclaw/workspace/agent')
from utils.structured_log import get_logger, LogLevel

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
LOGS_DIR = AGENT_DIR / "logs"


class AgentLogger:
    """
    Agent分级日志系统 - v2.0
    
    向后兼容 v1.0 接口，内部统一使用 structured_log
    """
    
    _instance = None
    
    def __new__(cls, log_dir=None):
        """单例模式确保只有一个日志实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, log_dir=None):
        if self._initialized:
            return
            
        self.log_dir = Path(log_dir) if log_dir else LOGS_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用统一的 structured logger
        self._logger = get_logger()
        
        self._initialized = True
    
    def _get_component(self, log_type: str) -> str:
        """根据日志类型返回组件名"""
        return log_type
    
    # ============================================
    # 核心事件日志 (兼容 v1.0 接口)
    # ============================================
    def info(self, msg):
        """通用信息"""
        self._logger.info(msg, component="agent")
    
    def warning(self, msg):
        """警告"""
        self._logger.warning(msg, component="agent")
    
    def error(self, msg):
        """错误"""
        self._logger.error(msg, component="agent")
    
    # ============================================
    # 任务相关日志
    # ============================================
    def task_start(self, task_id, goal):
        """记录任务开始"""
        self._logger.info(f"[TASK_START] {task_id} | {goal[:80]}...", 
                         component="action", context={"task_id": task_id})
        self._logger.info(f"Task started: {task_id}", component="agent")
    
    def task_finish(self, task_id, result="success"):
        """记录任务完成"""
        self._logger.info(f"[TASK_FINISH] {task_id} | {result}",
                         component="action", context={"task_id": task_id, "result": result})
        self._logger.info(f"Task finished: {task_id}", component="agent")
    
    def task_timeout(self, task_id, timeout):
        """记录任务超时"""
        self._logger.warning(f"[TASK_TIMEOUT] {task_id} | {timeout}s",
                            component="action", context={"task_id": task_id, "timeout": timeout})
        self._logger.error(f"Task timeout: {task_id} after {timeout}s", component="agent")
    
    def task_error(self, task_id, error):
        """记录任务错误"""
        self._logger.error(f"[TASK_ERROR] {task_id} | {error}",
                          component="action", context={"task_id": task_id, "error": str(error)})
        self._logger.error(f"Task error: {task_id} - {error}", component="agent")
    
    # ============================================
    # 记忆相关日志
    # ============================================
    def memory_write(self, memory_type, content_preview):
        """记录记忆写入"""
        preview = content_preview[:100] if content_preview else ""
        self._logger.info(f"[MEMORY_WRITE] {memory_type} | {preview}...",
                         component="reflection", context={"memory_type": memory_type})
        self._logger.info(f"Memory written: {memory_type}", component="agent")
    
    def memory_read(self, memory_type, keys=None):
        """记录记忆读取"""
        context = {"memory_type": memory_type}
        if keys:
            context["keys"] = keys
        self._logger.info(f"[MEMORY_READ] {memory_type}", component="reflection", context=context)
    
    # ============================================
    # 心跳相关日志
    # ============================================
    def heartbeat(self, status, details=""):
        """记录心跳"""
        self._logger.info(f"[HEARTBEAT] {status} | {details}",
                         component="heartbeat", context={"status": status})
    
    def heartbeat_error(self, error):
        """记录心跳错误"""
        self._logger.error(f"[HEARTBEAT_ERROR] {error}",
                          component="heartbeat", context={"error": str(error)})
        self._logger.error(f"Heartbeat error: {error}", component="agent")
    
    # ============================================
    # 系统相关日志
    # ============================================
    def system_event(self, event_type, details=""):
        """记录系统事件"""
        self._logger.info(f"[SYSTEM] {event_type} | {details}",
                         component="agent", context={"event_type": event_type})
    
    def state_change(self, old_state, new_state, reason=""):
        """记录状态变更"""
        context = {"old_state": old_state, "new_state": new_state}
        if reason:
            context["reason"] = reason
        self._logger.info(f"[STATE_CHANGE] {old_state} → {new_state}",
                         component="agent", context=context)
    
    def recovery(self, stage, details=""):
        """记录恢复过程"""
        self._logger.info(f"[RECOVERY] {stage} | {details}",
                         component="agent", context={"stage": stage})


# 全局logger实例 (单例)
logger = AgentLogger()


def get_logger():
    """获取全局logger实例 (兼容新接口)"""
    return logger


# 兼容性：保留旧接口
def log_simple(msg):
    """简化日志（兼容旧代码）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger._logger.info(msg, component="agent")
    # 同时打印到控制台
    print(f"[{timestamp}] {msg}")


if __name__ == "__main__":
    print("=== Logger v2.0 Test ===\n")
    print("Now using unified StructuredLog backend\n")
    
    # 测试各种日志
    logger.info("Agent starting...")
    logger.task_start("task_001", "测试任务：学习新技能")
    logger.task_finish("task_001", "success")
    logger.memory_write("diary", "今天学到了很多关于日志系统的知识")
    logger.heartbeat("ok", "CPU: 20%, Mem: 30%")
    logger.state_change("idle", "running", "new task received")
    logger.recovery("memory_loaded", "Loaded 50 memories")
    
    print("\n✅ 日志已写入 logs/agent.log 和 logs/agent.jsonl")
    print("  - logs/agent.log (人类可读)")
    print("  - logs/agent.jsonl (结构化JSON)")
