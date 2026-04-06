#!/usr/bin/env python3
"""
Three-Layer Safety Protection - 三道安全保护

三层防线:
  1. Action Filter (动作过滤) - 第一层
  2. Rate Limit (速率限制) - 第二层  
  3. Critical Confirmation (关键确认) - 第三层

保护范围:
  - delete files (删除文件)
  - modify system config (修改系统配置)
  - network requests (网络请求)
  - mass operations (批量操作)
  - permission changes (权限修改)
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

class ThreeLayerProtection:
    """三道安全保护系统"""
    
    def __init__(self):
        self.config = self._load_config()
        self.rate_tracker = self._load_rate_tracker()
        self.violation_log = self._load_violation_log()
        self.pending_confirmations = {}
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "safety_protection.json"
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _load_rate_tracker(self):
        """加载速率追踪器"""
        tracker_path = AGENT_DIR / "system" / "rate_tracker.json"
        if tracker_path.exists():
            return read_json(tracker_path)
        return {
            "api_calls": [],
            "file_writes": [],
            "file_deletes": [],
            "network_requests": [],
            "exec_commands": []
        }
    
    def _save_rate_tracker(self):
        """保存速率追踪器"""
        tracker_path = AGENT_DIR / "system" / "rate_tracker.json"
        write_json(tracker_path, self.rate_tracker)
    
    def _load_violation_log(self):
        """加载违规日志"""
        log_path = AGENT_DIR / "system" / "violation_log.json"
        if log_path.exists():
            return read_json(log_path)
        return []
    
    def _save_violation_log(self):
        """保存违规日志"""
        log_path = AGENT_DIR / "system" / "violation_log.json"
        write_json(log_path, self.violation_log)
    
    def _log_violation(self, layer: str, action: str, reason: str):
        """记录违规"""
        violation = {
            "timestamp": datetime.now().isoformat(),
            "layer": layer,
            "action": action,
            "reason": reason
        }
        self.violation_log.append(violation)
        self._save_violation_log()
        
        # 检查是否需要采取行动
        self._handle_violation(violation)
    
    def _handle_violation(self, violation):
        """处理违规"""
        today_violations = [v for v in self.violation_log 
                           if v["timestamp"].startswith(datetime.now().strftime("%Y-%m-%d"))]
        count = len(today_violations)
        
        handling = self.config.get("violation_handling", {})
        
        if count == 1:
            print(f"⚠️  [SAFETY] 第一次违规: {violation['reason']}")
        elif count == 2:
            print(f"🚫 [SAFETY] 第二次违规: 临时阻止")
        elif count >= 3:
            print(f"🔒 [SAFETY] 多次违规! 关闭门控并通知用户")
            # 关闭门控
            gate_path = AGENT_DIR / "system" / "gate.json"
            if gate_path.exists():
                gate = read_json(gate_path)
                gate["agent_enabled"] = False
                gate["closed_reason"] = "multiple_safety_violations"
                gate["closed_at"] = datetime.now().isoformat()
                write_json(gate_path, gate)
    
    # ============================================
    # 第一道防线: Action Filter
    # ============================================
    def action_filter_check(self, action: str, action_type: str = "exec") -> Tuple[bool, str]:
        """
        动作过滤检查
        
        Returns:
            (allowed, reason)
        """
        if not self.config["three_protections"]["action_filter"]["enabled"]:
            return True, "action_filter_disabled"
        
        # 检查黑名单 (直接阻止)
        blocked = self.config["three_protections"]["action_filter"]["blocked_actions"]
        for item in blocked:
            if item["pattern"] in action:
                self._log_violation("action_filter", action, f"BLOCKED: {item['reason']}")
                return False, f"🚫 危险操作被阻止: {item['reason']}"
        
        # 检查可疑模式 (需要确认)
        suspicious = self.config["three_protections"]["action_filter"]["suspicious_patterns"]
        for item in suspicious:
            if item["pattern"] in action:
                return False, f"⚠️ 可疑操作需要确认: {action[:50]}..."
        
        return True, "passed"
    
    # ============================================
    # 第二道防线: Rate Limit
    # ============================================
    def rate_limit_check(self, action_type: str) -> Tuple[bool, str]:
        """
        速率限制检查
        
        Returns:
            (allowed, reason)
        """
        if not self.config["three_protections"]["rate_limit"]["enabled"]:
            return True, "rate_limit_disabled"
        
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)
        
        # 获取限制配置
        limits = self.config["three_protections"]["rate_limit"]["limits"]
        
        # 映射action_type到tracker key
        type_mapping = {
            "api_call": "api_calls",
            "file_write": "file_writes",
            "file_delete": "file_deletes",
            "network_request": "network_requests",
            "exec_command": "exec_commands"
        }
        
        tracker_key = type_mapping.get(action_type, action_type)
        
        # 清理旧记录
        if tracker_key in self.rate_tracker:
            self.rate_tracker[tracker_key] = [
                t for t in self.rate_tracker[tracker_key]
                if datetime.fromisoformat(t) > one_hour_ago
            ]
        else:
            self.rate_tracker[tracker_key] = []
        
        # 检查每分钟限制
        per_minute_key = f"{tracker_key}_per_minute"
        if per_minute_key in limits:
            recent_count = sum(1 for t in self.rate_tracker[tracker_key] 
                             if datetime.fromisoformat(t) > one_minute_ago)
            if recent_count >= limits[per_minute_key]:
                self._log_violation("rate_limit", action_type, f"Rate limit exceeded: {limits[per_minute_key]}/min")
                return False, f"⏱️ 速率限制: 每分钟最多{limits[per_minute_key]}次{action_type}"
        
        # 检查每小时限制
        per_hour_key = f"{tracker_key}_per_hour"
        if per_hour_key in limits:
            if len(self.rate_tracker[tracker_key]) >= limits[per_hour_key]:
                self._log_violation("rate_limit", action_type, f"Rate limit exceeded: {limits[per_hour_key]}/hour")
                return False, f"⏱️ 速率限制: 每小时最多{limits[per_hour_key]}次{action_type}"
        
        # 记录这次操作
        self.rate_tracker[tracker_key].append(now.isoformat())
        self._save_rate_tracker()
        
        return True, "passed"
    
    # ============================================
    # 第三道防线: Critical Confirmation
    # ============================================
    def critical_confirmation_check(self, action: str, action_type: str = "exec") -> Tuple[bool, str, Optional[Dict]]:
        """
        关键操作确认检查
        
        Returns:
            (allowed, reason, confirmation_info)
        """
        if not self.config["three_protections"]["critical_confirmation"]["enabled"]:
            return True, "confirmation_disabled", None
        
        critical_actions = self.config["three_protections"]["critical_confirmation"]["critical_actions"]
        
        for critical in critical_actions:
            for pattern in critical["patterns"]:
                if pattern in action.lower() or pattern in action_type.lower():
                    # 需要确认
                    confirmation_id = f"confirm_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(action) % 10000}"
                    
                    confirmation_info = {
                        "id": confirmation_id,
                        "action": action,
                        "type": critical["type"],
                        "message": critical["user_message"],
                        "timestamp": datetime.now().isoformat(),
                        "delay_seconds": self.config["three_protections"]["critical_confirmation"]["delay_seconds"]
                    }
                    
                    self.pending_confirmations[confirmation_id] = confirmation_info
                    
                    return False, f"🔐 需要确认: {critical['user_message']}", confirmation_info
        
        return True, "passed", None
    
    def confirm_action(self, confirmation_id: str, approved: bool) -> bool:
        """确认或拒绝待确认的操作"""
        if confirmation_id not in self.pending_confirmations:
            return False
        
        confirmation = self.pending_confirmations.pop(confirmation_id)
        
        if approved:
            print(f"✅ [SAFETY] 操作已确认: {confirmation['action'][:50]}...")
            return True
        else:
            print(f"❌ [SAFETY] 操作被拒绝: {confirmation['action'][:50]}...")
            self._log_violation("critical_confirmation", confirmation['action'], "User rejected")
            return False
    
    # ============================================
    # 统一检查接口
    # ============================================
    def check_action(self, action: str, action_type: str = "exec") -> Dict:
        """
        统一检查接口 - 依次通过三道防线
        
        Returns:
            {
                "allowed": bool,
                "reason": str,
                "layer": str,  # 哪一层阻止的
                "confirmation": Optional[Dict]  # 如果需要确认
            }
        """
        # 第一层: Action Filter
        allowed, reason = self.action_filter_check(action, action_type)
        if not allowed:
            return {
                "allowed": False,
                "reason": reason,
                "layer": "action_filter",
                "confirmation": None
            }
        
        # 第二层: Rate Limit
        allowed, reason = self.rate_limit_check(action_type)
        if not allowed:
            return {
                "allowed": False,
                "reason": reason,
                "layer": "rate_limit",
                "confirmation": None
            }
        
        # 第三层: Critical Confirmation
        allowed, reason, confirmation = self.critical_confirmation_check(action, action_type)
        if not allowed:
            return {
                "allowed": False,
                "reason": reason,
                "layer": "critical_confirmation",
                "confirmation": confirmation
            }
        
        return {
            "allowed": True,
            "reason": "all_layers_passed",
            "layer": None,
            "confirmation": None
        }
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_violations": len(self.violation_log),
            "today_violations": len([v for v in self.violation_log 
                                     if v["timestamp"].startswith(datetime.now().strftime("%Y-%m-%d"))]),
            "pending_confirmations": len(self.pending_confirmations),
            "rate_tracker": {k: len(v) for k, v in self.rate_tracker.items()}
        }

if __name__ == "__main__":
    print("=== Three-Layer Safety Protection Test ===\n")
    
    protection = ThreeLayerProtection()
    
    # 测试Action Filter
    print("1. Action Filter测试:")
    test_actions = [
        "ls -la",  # 安全
        "rm -rf /tmp/test",  # 可疑
        "rm -rf /",  # 危险！
    ]
    
    for action in test_actions:
        result = protection.check_action(action, "exec")
        status = "✅ 允许" if result["allowed"] else f"❌ 阻止"
        print(f"   {action}: {status}")
        if not result["allowed"]:
            print(f"      → 层: {result['layer']}, 原因: {result['reason'][:50]}")
    
    print("\n2. Rate Limit测试:")
    # 快速执行多次
    for i in range(3):
        result = protection.check_action("echo test", "exec_command")
        print(f"   执行#{i+1}: {'✅' if result['allowed'] else '❌'}")
    
    print("\n3. Critical Confirmation测试:")
    critical_actions = [
        "rm -rf /tmp/important",
        "curl https://example.com/api",
        "chmod 777 /etc/config",
    ]
    
    for action in critical_actions:
        result = protection.check_action(action, "exec")
        status = "✅ 允许" if result["allowed"] else f"🔐 需确认"
        print(f"   {action[:30]}: {status}")
    
    print(f"\n统计: {protection.get_stats()}")
