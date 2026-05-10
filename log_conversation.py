#!/usr/bin/env python3
"""
对话记录器 - 方案C

每次和朋朋对话后，自动把对话摘要写入 EventBus。
这样日报就能读取到今天的对话记录。

Usage:
    python3 log_conversation.py "用户消息" "我的回复摘要"
"""

import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path

EVENTS_DB = Path("/root/.openclaw/workspace/agent/db/events.db")

def log_conversation(user_message: str, my_reply: str):
    """记录对话到 EventBus"""
    try:
        conn = sqlite3.connect(str(EVENTS_DB))
        
        # 构建事件数据
        event_data = {
            "user_id": "pengpeng",
            "channel": "openclaw-weixin",
            "message": user_message[:200],  # 截断
            "reply_summary": my_reply[:200],
            "logged_at": datetime.now().isoformat(),
        }
        
        conn.execute("""
            INSERT INTO events (event_id, type, data, timestamp, status, retry_count, ttl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hash(user_message) % 10000:04d}",
            "message.received",  # 使用相同的类型，让日报能读取
            json.dumps(event_data, ensure_ascii=False),
            datetime.now().timestamp(),
            "pending",
            0,
            86400  # 24小时TTL
        ))
        
        conn.commit()
        conn.close()
        
        print(f"✅ 对话已记录: {user_message[:30]}...")
        return True
        
    except Exception as e:
        print(f"❌ 记录失败: {e}")
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 log_conversation.py '用户消息' '我的回复摘要'")
        return
    
    user_msg = sys.argv[1]
    my_reply = sys.argv[2]
    
    log_conversation(user_msg, my_reply)

if __name__ == "__main__":
    main()
