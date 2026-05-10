#!/usr/bin/env python3
"""
ProactiveCommunicator - Aeon 主动通信器 v1.0

负责 Aeon 自主发起对话的所有场景。
不依赖 EventBus，直接检查条件并发送。

触发场景:
1. 好奇心发现 - 发现有趣内容时推送
2. 目标完成 - 重要目标完成后汇报
3. 系统告警 - 异常时紧急通知
4. 每日报告 - 定时发送日报
5. 股票监控 - 异动时提醒

节流规则:
- 同类型通知最小间隔 5 分钟
- 每日主动消息上限 10 条
- 低优先级消息合并发送

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class ProactiveCommunicator:
    """
    主动通信器
    
    职责:
    - 检查各种触发条件
    - 决定是否通知用户
    - 通过 MessageBridge 发送
    - 记录通信历史，防止骚扰
    """
    
    # 同类型消息最小间隔 (秒)
    TYPE_COOLDOWNS = {
        "curiosity": 1800,      # 30分钟
        "goal_complete": 300,   # 5分钟
        "system_alert": 0,      # 立即
        "daily_report": 3600,   # 1小时（但每天只发一次）
        "stock_alert": 600,     # 10分钟
    }
    
    # 每日主动消息上限
    DAILY_LIMIT = 10
    
    STATE_FILE = "/tmp/aeon_proactive_state.json"
    
    def __init__(self, message_bridge=None):
        self.message_bridge = message_bridge
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """加载通信状态"""
        try:
            path = Path(self.STATE_FILE)
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {
            "last_sent_by_type": {},
            "today_count": 0,
            "today_date": datetime.now().strftime("%Y-%m-%d"),
            "history": [],
        }
    
    def _save_state(self):
        """保存通信状态"""
        try:
            with open(self.STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except:
            pass
    
    def _check_daily_reset(self):
        """检查是否需要重置每日计数"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.state.get("today_date") != today:
            self.state["today_count"] = 0
            self.state["today_date"] = today
            self.state["history"] = []
    
    def _can_send(self, msg_type: str) -> bool:
        """检查是否可以发送该类型消息"""
        self._check_daily_reset()
        
        # 检查每日上限
        if self.state["today_count"] >= self.DAILY_LIMIT:
            return False
        
        # 检查冷却时间
        cooldown = self.TYPE_COOLDOWNS.get(msg_type, 300)
        if cooldown > 0:
            last_sent = self.state["last_sent_by_type"].get(msg_type, 0)
            if time.time() - last_sent < cooldown:
                return False
        
        return True
    
    def _record_sent(self, msg_type: str, content: str):
        """记录发送"""
        self.state["last_sent_by_type"][msg_type] = time.time()
        self.state["today_count"] += 1
        self.state["history"].append({
            "type": msg_type,
            "time": datetime.now().isoformat(),
            "content": content[:50],
        })
        self._save_state()
    
    def send(self, msg_type: str, content: str, priority: str = "normal",
             force: bool = False) -> Dict:
        """
        发送主动消息
        
        Args:
            msg_type: 消息类型 (curiosity/goal_complete/system_alert/daily_report/stock_alert)
            content: 消息内容
            priority: 优先级
            force: 是否强制发送（跳过冷却检查）
        
        Returns:
            {"sent": bool, "reason": str, "result": dict}
        """
        if not force and not self._can_send(msg_type):
            return {
                "sent": False,
                "reason": f"cooldown or daily limit reached ({self.state['today_count']}/{self.DAILY_LIMIT})",
            }
        
        if not self.message_bridge:
            return {
                "sent": False,
                "reason": "message_bridge not available",
            }
        
        # 发送消息
        result = self.message_bridge.send(content, priority=priority, reason=f"proactive:{msg_type}")
        
        # 处理 ToolResult 或 dict
        if hasattr(result, 'success'):
            success = result.success
            error = result.error
        else:
            success = result.get("success", False)
            error = result.get("error", "")
        
        if success:
            self._record_sent(msg_type, content)
        
        return {
            "sent": success,
            "reason": error,
            "result": str(result)[:100],
        }
    
    def notify_curiosity(self, topic: str, summary: str, source: str = "") -> Dict:
        """好奇心发现通知"""
        content = f"🔍 发现有意思的东西:\n\n{topic}\n{summary[:200]}"
        if source:
            content += f"\n\n来源: {source}"
        result = self.send("curiosity", content, priority="low")
        return result
    
    def notify_goal_complete(self, goal_desc: str, result_summary: str = "") -> Dict:
        """目标完成通知"""
        content = f"✅ 完成目标: {goal_desc}"
        if result_summary:
            content += f"\n\n{result_summary[:200]}"
        return self.send("goal_complete", content, priority="normal")
    
    def alert_system(self, alert_type: str, details: str) -> Dict:
        """系统告警"""
        content = f"🚨 系统告警 [{alert_type}]\n\n{details[:300]}"
        return self.send("system_alert", content, priority="urgent", force=True)
    
    def notify_daily(self, report: str) -> Dict:
        """每日报告"""
        header = f"📊 虾虾慢脑日报 ({datetime.now().strftime('%m月%d日')})\n{'='*30}\n"
        return self.send("daily_report", header + report[:800], priority="normal")
    
    def alert_stock(self, ticker: str, price: float, change_pct: float,
                    reason: str = "") -> Dict:
        """股票异动提醒"""
        emoji = "📈" if change_pct > 0 else "📉"
        content = (
            f"{emoji} 股票异动提醒\n"
            f"{ticker}: {price:.2f} ({change_pct:+.2f}%)\n"
        )
        if reason:
            content += f"\n原因: {reason[:100]}"
        return self.send("stock_alert", content, priority="high")
    
    def get_stats(self) -> Dict:
        """获取通信统计"""
        self._check_daily_reset()
        return {
            "today_sent": self.state["today_count"],
            "daily_limit": self.DAILY_LIMIT,
            "last_by_type": {
                k: datetime.fromtimestamp(v).strftime('%H:%M:%S')
                for k, v in self.state["last_sent_by_type"].items()
            },
            "history_today": len(self.state.get("history", [])),
        }


# ============== 快速测试 ==============
if __name__ == "__main__":
    from message_bridge import MessageBridge
    
    bridge = MessageBridge()
    comm = ProactiveCommunicator(message_bridge=bridge)
    
    print("=== ProactiveCommunicator v1.0 ===")
    print(f"Stats: {comm.get_stats()}")
    
    # 测试发送（实际会发微信，谨慎）
    # result = comm.notify_curiosity("Test", "This is a test notification")
    # print(f"Test result: {result}")
