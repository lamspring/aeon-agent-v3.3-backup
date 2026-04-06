#!/usr/bin/env python3
"""
Risk Controller - 风险控制模块
权限极高，必须严格审查所有操作
"""
import json
import re
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

class RiskController:
    """风险控制器 - 审查所有危险操作"""
    
    def __init__(self):
        self.config = self._load_json("risk/config.json")
        self.allowed_commands = self._load_json("risk/allowed_commands.json")
        self.restricted_paths = self._load_json("risk/restricted_paths.json")
        self.dangerous_actions = self._load_json("risk/dangerous_actions.json")
    
    def _load_json(self, filename):
        with open(AGENT_DIR / filename, 'r') as f:
            return json.load(f)
    
    def is_enabled(self):
        """检查风险控制是否启用"""
        return self.config.get("enabled", True)
    
    def is_strict_mode(self):
        """检查是否严格模式"""
        return self.config.get("strict_mode", True)
    
    def check_command(self, command):
        """
        检查命令是否允许执行
        返回: (allowed: bool, reason: str, level: str)
        """
        if not self.is_enabled():
            return True, "Risk control disabled", "info"
        
        # 提取命令主体
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False, "Empty command", "error"
        
        base_cmd = cmd_parts[0]
        
        # 检查是否在允许列表
        if base_cmd not in self.allowed_commands:
            return False, f"Command '{base_cmd}' not in allowed list", "high"
        
        # 检查是否包含危险操作
        for danger in self.dangerous_actions:
            action = danger["action"]
            level = danger["level"]
            
            if action in command:
                if self.is_strict_mode():
                    return False, f"Dangerous action detected: {action} - {danger['description']}", level
                else:
                    return True, f"Warning: {action} - {danger['description']}", level
        
        # 检查是否涉及受限路径
        for restricted in self.restricted_paths:
            if restricted in command:
                return False, f"Access to restricted path: {restricted}", "critical"
        
        return True, "Command approved", "ok"
    
    def check_path(self, path):
        """
        检查路径是否允许访问
        返回: (allowed: bool, reason: str)
        """
        if not self.is_enabled():
            return True, "Risk control disabled"
        
        path = str(path)
        
        for restricted in self.restricted_paths:
            if restricted in path:
                return False, f"Path restricted: {restricted}"
        
        return True, "Path approved"
    
    def check_tool(self, tool_name, parameters=None):
        """
        检查工具调用是否安全
        返回: (allowed: bool, reason: str, level: str)
        """
        if not self.is_enabled():
            return True, "Risk control disabled", "info"
        
        parameters = parameters or {}
        
        # 危险工具列表
        dangerous_tools = {
            "exec": "high",
            "write": "medium",
            "edit": "medium",
            "message": "low",
            "browser": "medium"
        }
        
        level = dangerous_tools.get(tool_name, "low")
        
        if level == "high" and self.is_strict_mode():
            return False, f"High-risk tool: {tool_name}", level
        elif level in ["high", "medium"]:
            return True, f"Risk acknowledged: {tool_name}", level
        
        return True, "Tool approved", level
    
    def log_violation(self, action, reason, level):
        """记录违规操作"""
        from datetime import datetime
        log_file = AGENT_DIR / "logs" / "risk_violations.log"
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] [{level}] {action}: {reason}\n"
        
        with open(log_file, 'a') as f:
            f.write(entry)

# 便捷函数
def check_command_safe(command):
    """检查命令是否安全"""
    rc = RiskController()
    return rc.check_command(command)

def check_path_safe(path):
    """检查路径是否安全"""
    rc = RiskController()
    return rc.check_path(path)

def check_tool_safe(tool_name, parameters=None):
    """检查工具是否安全"""
    rc = RiskController()
    return rc.check_tool(tool_name, parameters)

if __name__ == "__main__":
    # 测试
    rc = RiskController()
    
    print("=== Risk Controller Test ===")
    print(f"Enabled: {rc.is_enabled()}")
    print(f"Strict Mode: {rc.is_strict_mode()}")
    print()
    
    test_commands = [
        "ls -la",
        "rm -rf /",
        "cat /etc/passwd",
        "python3 script.py",
        "curl https://example.com"
    ]
    
    for cmd in test_commands:
        allowed, reason, level = rc.check_command(cmd)
        status = "✓" if allowed else "✗"
        print(f"{status} [{level:8}] {cmd:30} -> {reason}")
