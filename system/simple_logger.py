#!/usr/bin/env python3
"""
Simple Logger - 简化日志系统

直接追加文本，不格式化，不总结
"""
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
LOG_FILE = AGENT_DIR / "logs" / "execution_log.txt"

def log(msg: str):
    """
    直接追加一行文本到日志
    
    Args:
        msg: 要记录的文本
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 确保日志目录存在
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # 直接追加一行
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {msg}\n")

def log_raw(text: str):
    """
    追加原始文本（不带时间戳）
    
    Args:
        text: 原始文本
    """
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(text)
        if not text.endswith('\n'):
            f.write('\n')

def get_recent_logs(lines: int = 50) -> str:
    """
    获取最近的日志行
    
    Args:
        lines: 要读取的行数
        
    Returns:
        日志内容
    """
    if not LOG_FILE.exists():
        return ""
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            return ''.join(all_lines[-lines:])
    except:
        return ""

def clear_logs():
    """清空日志（谨慎使用）"""
    if LOG_FILE.exists():
        LOG_FILE.write_text("")

if __name__ == "__main__":
    # 测试
    log("系统启动")
    log("执行任务: task_001")
    log("步骤完成: step 1/4")
    
    print("日志已写入")
    print("\n最近日志:")
    print(get_recent_logs(10))
