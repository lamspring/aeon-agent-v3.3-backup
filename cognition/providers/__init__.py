#!/usr/bin/env python3
"""
OpenClawProvider - OpenClaw 能力封装 v1.0

将现有 ToolAdapter + MessageBridge 封装为 Capability Interface 实现。

这是当前默认 Provider，Aeon v3.0 的所有功能都通过这个提供。

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import sys
from typing import Dict, List, Optional, Any

# 添加路径
sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition')

from capability import ModelProvider, ToolAdapter, ChannelBridge


class OpenClawModelProvider(ModelProvider):
    """OpenClaw 模型提供者
    
    当前 OpenClaw 没有直接的 model CLI，模型调用通过 Gateway。
    这里 health_check 只验证 Gateway 是否运行，chat/embed 暂时未实现
    （因为 Aeon Core 目前不直接调用模型，模型调用在虾虾层）。
    
    未来如果 Aeon Core 需要自主 LLM 调用，可以实现为 Gateway HTTP API 调用。
    """
    
    def __init__(self, **kwargs):
        self.config = kwargs
    
    def chat(self, messages: List[Dict[str, str]], model: str = "default",
             max_tokens: int = 4096, temperature: float = 0.7) -> str:
        raise NotImplementedError("OpenClaw model chat not implemented yet. Use Gateway.")
    
    def embed(self, text: str, model: str = "default") -> List[float]:
        raise NotImplementedError("OpenClaw embed not implemented yet.")
    
    def list_models(self) -> List[str]:
        return ["kimi-coding/k2.6", "kimi-coding/k2p5"]
    
    def health_check(self) -> bool:
        """检查 Gateway 是否运行"""
        try:
            import subprocess
            result = subprocess.run(
                ["openclaw", "gateway", "status"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0 and "running" in result.stdout
        except:
            return False


class OpenClawToolAdapter(ToolAdapter):
    """OpenClaw 工具适配器
    
    封装现有的 tool_adapter.py，包装为 Capability Interface。
    """
    
    def __init__(self, **kwargs):
        from tool_adapter import ToolAdapter as _ToolAdapter
        self.adapter = _ToolAdapter(**kwargs)
    
    def call(self, tool_name: str, params: Dict[str, Any]) -> Dict:
        result = self.adapter.call(tool_name, params)
        return result.to_dict()
    
    def list_tools(self) -> Dict[str, Dict]:
        return self.adapter.list_tools()
    
    def can_handle(self, action: str) -> bool:
        return self.adapter.can_handle(action)
    
    def health_check(self) -> bool:
        # 检查至少一个工具可用
        try:
            tools = self.list_tools()
            return len(tools) > 0
        except:
            return False


class OpenClawChannelBridge(ChannelBridge):
    """OpenClaw 渠道桥接
    
    封装现有的 message_bridge.py，包装为 Capability Interface。
    """
    
    def __init__(self, default_target: str = "o9cq806JQxsn4CVsKFpl4wX-kCr8@im.wechat", **kwargs):
        from message_bridge import MessageBridge
        self.bridge = MessageBridge(**kwargs)
        self.default_target = default_target
    
    def send(self, message: str, to: str = "", channel: str = "default",
             priority: str = "normal", media: Optional[str] = None) -> bool:
        target = to or self.default_target
        
        result = self.bridge.send(
            content=message,
            priority=priority,
            channel=channel if channel != "default" else "openclaw-weixin",
            reason="aeon_proactive"
        )
        return result.get("success", False)
    
    def read(self, from_user: str = "", since: Optional[str] = None,
             limit: int = 10) -> List[Dict]:
        # OpenClaw 没有直接的消息读取 CLI，暂时返回空
        # 未来可以通过 Gateway API 实现
        return []
    
    def list_channels(self) -> List[str]:
        return ["openclaw-weixin", "feishu", "discord"]
    
    def health_check(self) -> bool:
        # 尝试发送一个测试消息（空内容检查）
        try:
            # 不实际发送，只检查 bridge 对象存在
            return self.bridge is not None
        except:
            return False


class OpenClawProvider(ModelProvider, ToolAdapter, ChannelBridge):
    """OpenClaw 统一提供者（实现全部三个接口）"""
    
    def __init__(self, default_target: str = "o9cq806JQxsn4CVsKFpl4wX-kCr8@im.wechat", **kwargs):
        self._model = OpenClawModelProvider()
        self._tool = OpenClawToolAdapter()
        self._channel = OpenClawChannelBridge(default_target=default_target)
    
    # ModelProvider 接口转发
    def chat(self, messages: list, model: str = "default", max_tokens: int = 4096, temperature: float = 0.7) -> str:
        return self._model.chat(messages, model, max_tokens, temperature)
    
    def embed(self, text: str, model: str = "default") -> list:
        return self._model.embed(text, model)
    
    def list_models(self) -> list:
        return self._model.list_models()
    
    # ToolAdapter 接口转发
    def call(self, tool_name: str, params: dict) -> dict:
        return self._tool.call(tool_name, params)
    
    def list_tools(self) -> dict:
        return self._tool.list_tools()
    
    def can_handle(self, action: str) -> bool:
        return self._tool.can_handle(action)
    
    # ChannelBridge 接口转发
    def send(self, message: str, to: str = "", channel: str = "default",
             priority: str = "normal", media: str = None) -> bool:
        return self._channel.send(message, to, channel, priority, media)
    
    def read(self, from_user: str = "", since: str = None, limit: int = 10) -> list:
        return self._channel.read(from_user, since, limit)
    
    def list_channels(self) -> list:
        return self._channel.list_channels()
    
    # 统一 health_check
    def health_check(self) -> bool:
        return (
            self._model.health_check() and
            self._tool.health_check() and
            self._channel.health_check()
        )
