#!/usr/bin/env python3
"""
Aeon Alert - 告警通知系统

支持:
- 企业微信机器人 Webhook
- 分级告警 (INFO/WARNING/ERROR/CRITICAL)
- 告警抑制 (相同告警N分钟内只发一次)
- 关键事件自动触发

Usage:
    from alert import AlertManager
    alert = AlertManager()
    alert.send("系统启动完成", level="INFO")
    alert.send_critical("服务崩溃", details={"error": "..."})
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
import threading


class AlertLevel(Enum):
    """告警级别 - 数值越大级别越高"""
    INFO = 1        # 蓝色
    WARNING = 2     # 黄色
    ERROR = 3       # 红色
    CRITICAL = 4    # 红色 + @all


@dataclass
class AlertConfig:
    """告警配置"""
    webhook_url: str = ""
    enabled: bool = True
    throttle_minutes: int = 5  # 相同告警抑制时间
    min_level: AlertLevel = AlertLevel.WARNING  # 最低告警级别
    include_trace: bool = True
    
    @classmethod
    def from_config(cls) -> 'AlertConfig':
        """从配置文件加载"""
        import sys
        sys.path.insert(0, '/root/.openclaw/workspace/agent')
        from config import get_config
        
        cfg = get_config()
        
        # 将字符串级别转换为枚举
        level_map = {
            "info": AlertLevel.INFO,
            "warning": AlertLevel.WARNING,
            "error": AlertLevel.ERROR,
            "critical": AlertLevel.CRITICAL,
        }
        level_str = cfg.get("alert.min_level", "info")
        min_level = level_map.get(level_str, AlertLevel.INFO)
        
        return cls(
            webhook_url=cfg.get("alert.webhook_url", ""),
            enabled=cfg.get("alert.enabled", True),
            throttle_minutes=cfg.get("alert.throttle_minutes", 5),
            min_level=min_level,
        )


class AlertManager:
    """
    告警管理器
    
    功能:
    - 企业微信消息推送
    - 告警抑制 (避免消息轰炸)
    - 关键事件自动告警
    """
    
    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig.from_config()
        self._last_alert: Dict[str, float] = {}  # 告警抑制缓存
        self._lock = threading.Lock()
    
    def _is_throttled(self, alert_key: str) -> bool:
        """检查是否处于抑制期"""
        with self._lock:
            last_time = self._last_alert.get(alert_key)
            if last_time is None:
                return False
            
            throttle_seconds = self.config.throttle_minutes * 60
            if time.time() - last_time < throttle_seconds:
                return True
            
            return False
    
    def _record_alert(self, alert_key: str):
        """记录告警时间"""
        with self._lock:
            self._last_alert[alert_key] = time.time()
    
    def _build_wechat_msg(self, title: str, message: str, level: AlertLevel, details: Optional[Dict] = None) -> dict:
        """
        构建企业微信消息
        
        参考文档: https://developer.work.weixin.qq.com/document/path/99110
        """
        # 级别中文和颜色
        level_info = {
            AlertLevel.INFO: ("ℹ️ 信息", "info"),
            AlertLevel.WARNING: ("⚠️ 警告", "warning"),
            AlertLevel.ERROR: ("❌ 错误", "warning"),
            AlertLevel.CRITICAL: ("🚨 严重", "warning"),
        }
        
        level_text, color = level_info[level]
        
        # 构建内容 (Markdown格式)
        content = f"<font color='{color}'>**{level_text}**</font>\n\n"
        content += f"**{title}**\n\n"
        content += f"{message}\n\n"
        
        if details:
            content += "**详情:**\n"
            for k, v in details.items():
                content += f"- {k}: {v}\n"
        
        content += f"\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # CRITICAL级别 @所有人
        if level == AlertLevel.CRITICAL:
            content += "\n\n<@all>"
        
        # 企业微信markdown消息格式
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
    
    def send(self, title: str, message: str = "", 
             level: AlertLevel = AlertLevel.INFO,
             details: Optional[Dict] = None,
             force: bool = False) -> bool:
        """
        发送告警
        
        Args:
            title: 告警标题
            message: 告警内容
            level: 告警级别
            details: 额外详情字典
            force: 强制发送（忽略抑制）
        
        Returns:
            是否发送成功
        """
        # 检查是否启用
        if not self.config.enabled:
            return False
        
        # 检查级别
        if level.value < self.config.min_level.value:
            return False
        
        # 检查webhook
        if not self.config.webhook_url:
            return False
        
        # 告警抑制检查
        alert_key = f"{level.value}:{title}"
        if not force and self._is_throttled(alert_key):
            return False
        
        try:
            # 构建消息
            msg = self._build_wechat_msg(title, message, level, details)
            
            # 发送请求
            data = json.dumps(msg, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(
                self.config.webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get('errcode') == 0:
                    self._record_alert(alert_key)
                    return True
                else:
                    print(f"Alert failed: {result}")
                    return False
                    
        except Exception as e:
            print(f"Alert send error: {e}")
            return False
    
    def send_info(self, title: str, message: str = "", **kwargs):
        """发送信息级别告警"""
        return self.send(title, message, AlertLevel.INFO, **kwargs)
    
    def send_warning(self, title: str, message: str = "", **kwargs):
        """发送警告级别告警"""
        return self.send(title, message, AlertLevel.WARNING, **kwargs)
    
    def send_error(self, title: str, message: str = "", **kwargs):
        """发送错误级别告警"""
        return self.send(title, message, AlertLevel.ERROR, **kwargs)
    
    def send_critical(self, title: str, message: str = "", **kwargs):
        """发送严重级别告警 (@all)"""
        return self.send(title, message, AlertLevel.CRITICAL, **kwargs)
    
    # ===== 关键事件自动告警 =====
    
    def on_system_start(self, version: str = "3.1", recover: bool = False):
        """系统启动通知"""
        return self.send_info(
            "Aeon Agent 启动",
            f"版本 {version} 已启动{'(带恢复)' if recover else ''}",
            details={"timestamp": datetime.now().isoformat()}
        )
    
    def on_system_stop(self):
        """系统停止通知"""
        return self.send_info(
            "Aeon Agent 停止",
            "系统已正常关闭"
        )
    
    def on_goal_completed(self, goal_id: str, description: str, auto: bool = False):
        """目标完成通知"""
        return self.send_info(
            "目标完成",
            f"{'[自动]' if auto else ''}{description[:50]}",
            details={"goal_id": goal_id[:16]}
        )
    
    def on_goal_failed(self, goal_id: str, description: str, reason: str):
        """目标失败告警"""
        return self.send_error(
            "目标失败",
            f"{description[:50]}",
            details={"goal_id": goal_id[:16], "reason": reason}
        )
    
    def on_service_crash(self, error: str, component: str = ""):
        """服务崩溃告警"""
        return self.send_critical(
            "服务崩溃",
            f"{component or 'System'} 发生严重错误",
            details={"error": error[:200]}
        )
    
    def on_queue_overflow(self, queue_size: int, threshold: int = 1000):
        """队列堆积告警"""
        if queue_size > threshold:
            return self.send_warning(
                "队列堆积警告",
                f"事件队列堆积: {queue_size} 条",
                details={"threshold": threshold, "queue_size": queue_size}
            )
        return False
    
    def on_high_memory(self, memory_percent: float, threshold: float = 90.0):
        """内存使用过高告警"""
        if memory_percent > threshold:
            return self.send_warning(
                "内存使用过高",
                f"当前使用: {memory_percent:.1f}%",
                details={"threshold": f"{threshold}%", "memory": f"{memory_percent:.1f}%"}
            )
        return False


# 全局实例
_alert_instance: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """获取全局告警管理器"""
    global _alert_instance
    if _alert_instance is None:
        _alert_instance = AlertManager()
    return _alert_instance


def send_alert(title: str, message: str = "", level: str = "info", **kwargs):
    """便捷函数发送告警"""
    level_map = {
        "info": AlertLevel.INFO,
        "warning": AlertLevel.WARNING,
        "error": AlertLevel.ERROR,
        "critical": AlertLevel.CRITICAL,
    }
    alert_level = level_map.get(level, AlertLevel.INFO)
    mgr = get_alert_manager()
    return mgr.send(title, message, alert_level, **kwargs)


# CLI测试
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Aeon Alert Test')
    parser.add_argument('--webhook', help='Webhook URL')
    parser.add_argument('--title', default='测试告警', help='告警标题')
    parser.add_argument('--message', default='这是一条测试消息', help='告警内容')
    parser.add_argument('--level', default='info', choices=['info', 'warning', 'error', 'critical'])
    
    args = parser.parse_args()
    
    config = AlertConfig()
    if args.webhook:
        config.webhook_url = args.webhook
    
    alert = AlertManager(config)
    success = alert.send(args.title, args.message, AlertLevel(args.level))
    
    if success:
        print("✓ Alert sent successfully")
    else:
        print("✗ Failed to send alert")
