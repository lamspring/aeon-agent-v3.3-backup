#!/usr/bin/env python3
"""
v11.4 Message Queue Checker
检查来自v11.4系统的消息队列
"""
import json
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
MESSAGES_DIR = Path("/root/.openclaw/workspace/xiaxia-v11")

def read_json(path):
    if not path.exists():
        return None
    with open(path, 'r') as f:
        return json.load(f)

class MessageChecker:
    """消息队列检查器"""
    
    def __init__(self):
        self.config = read_json(AGENT_DIR / "system" / "messages.json") or {"enabled": True}
    
    def is_enabled(self):
        return self.config.get("enabled", True)
    
    def check_messages(self):
        """
        检查消息队列
        
        Returns:
            {
                "has_messages": bool,
                "count": int,
                "messages": [...],
                "action_required": bool
            }
        """
        if not self.is_enabled():
            return {"has_messages": False, "count": 0, "messages": [], "action_required": False}
        
        # 检查xiaxia-v11消息目录
        queue_file = MESSAGES_DIR / "messages" / "queue.json"
        
        if not queue_file.exists():
            return {"has_messages": False, "count": 0, "messages": [], "action_required": False}
        
        try:
            queue = read_json(queue_file)
            messages = queue.get("messages", [])
            unread = [m for m in messages if not m.get("read", False)]
            
            return {
                "has_messages": len(unread) > 0,
                "count": len(unread),
                "messages": unread,
                "action_required": len(unread) > 0
            }
        except:
            return {"has_messages": False, "count": 0, "messages": [], "action_required": False}
    
    def process_messages(self):
        """处理消息并返回需要执行的任务"""
        result = self.check_messages()
        
        if not result["has_messages"]:
            return None
        
        # 解析消息，生成任务
        tasks = []
        for msg in result["messages"]:
            task = self._message_to_task(msg)
            if task:
                tasks.append(task)
        
        return tasks
    
    def _message_to_task(self, message):
        """将消息转换为任务"""
        msg_type = message.get("type", "unknown")
        content = message.get("content", "")
        
        # 根据消息类型生成任务
        if msg_type == "research":
            return {
                "task_id": f"msg_task_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "type": "research",
                "goal": content,
                "priority": message.get("priority", 2),
                "source": "v11_message"
            }
        elif msg_type == "learn":
            return {
                "task_id": f"msg_task_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "type": "learn",
                "goal": content,
                "priority": message.get("priority", 2),
                "source": "v11_message"
            }
        
        return None

if __name__ == "__main__":
    print("=== Message Queue Checker ===")
    checker = MessageChecker()
    print(f"Enabled: {checker.is_enabled()}")
    
    result = checker.check_messages()
    print(f"\nMessages: {result['count']}")
    print(f"Action required: {result['action_required']}")
