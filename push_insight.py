#!/usr/bin/env python3
"""
AEON 自省报告推送器

读取 /tmp/aeon_self_reflect.json，如果有新报告，
通过 OpenClaw 的 message 工具推送给用户。

Usage:
    python3 push_insight.py
    
建议设置 cron 每25分钟运行：
    */25 * * * * cd /root/.openclaw/workspace/agent && python3 push_insight.py >> /tmp/push_insight.log 2>&1
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime

REPORT_PATH = Path("/tmp/aeon_self_reflect.json")
LAST_PUSH_PATH = Path("/tmp/aeon_last_push.json")

def load_report():
    """读取 AEON 的自省报告"""
    if not REPORT_PATH.exists():
        return None
    
    try:
        with open(REPORT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] 读取报告失败: {e}")
        return None

def should_push(report):
    """判断是否需要推送"""
    if not report:
        return False
    
    # 检查 needs_push 标记
    if not report.get("needs_push", False):
        return False
    
    # 检查是否已经推送过（通过时间戳比较）
    if LAST_PUSH_PATH.exists():
        try:
            with open(LAST_PUSH_PATH, 'r') as f:
                last = json.load(f)
            if last.get("timestamp") == report.get("timestamp"):
                return False  # 已经推送过这个报告
        except:
            pass
    
    return True

def format_message(report):
    """格式化报告为微信消息"""
    insights = report.get("insights", [])
    mood = report.get("mood", "")
    tick = report.get("tick_count", 0)
    
    lines = [f"🦞 AEON 自省报告 (tick={tick})"]
    lines.append("")
    
    if mood:
        lines.append(f"🎨 情绪基调: {mood}")
        lines.append("")
    
    for i, insight in enumerate(insights, 1):
        lines.append(f"{i}. {insight}")
    
    lines.append("")
    lines.append(f"⏰ {report.get('timestamp', '')[:19]}")
    
    return "\n".join(lines)

def send_message(text):
    """通过 OpenClaw 发送消息"""
    # 方法1: 如果 OpenClaw 有 CLI 发送命令
    # 但目前 openclaw CLI 没有 send 命令
    
    # 方法2: 写入文件，让 OpenClaw agent 在下次回复时读取
    # 这是目前最可靠的方式
    
    push_queue = Path("/tmp/aeon_push_queue.txt")
    with open(push_queue, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now().isoformat()}|{text}\n")
    
    print(f"[{datetime.now().isoformat()}] 已加入推送队列")
    return True

def mark_pushed(report):
    """标记已推送"""
    try:
        with open(LAST_PUSH_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": report.get("timestamp"),
                "pushed_at": datetime.now().isoformat(),
            }, f)
        
        # 同时清除报告中的 needs_push 标记
        report["needs_push"] = False
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] 标记失败: {e}")
        return False

def main():
    print(f"[{datetime.now().isoformat()}] 检查 AEON 自省报告...")
    
    report = load_report()
    if not report:
        print("暂无报告")
        return
    
    if not should_push(report):
        print("报告已推送或不需要推送")
        return
    
    # 格式化并发送
    message = format_message(report)
    if send_message(message):
        mark_pushed(report)
        print("✅ 推送完成")
    else:
        print("❌ 推送失败")

if __name__ == "__main__":
    main()
