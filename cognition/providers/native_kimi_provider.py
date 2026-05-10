#!/usr/bin/env python3
"""
NativeKimiProvider - 直接调用 Kimi API v1.0

不依赖 OpenClaw，直接通过 HTTP 调用 Kimi API。

用途:
- OpenClaw 崩溃时的备用模型提供者
- 未来本地部署时的过渡方案
- 测试环境（mock provider）

配置:
{
    "api_key": "sk-...",
    "base_url": "https://api.kimi.com/coding",
    "default_model": "k2.6"
}

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import json
import os
import urllib.request
from typing import Dict, List, Optional, Any

from capability import ModelProvider, ToolAdapter, ChannelBridge


class NativeKimiModelProvider(ModelProvider):
    """原生 Kimi 模型提供者"""
    
    def __init__(self, api_key: str = "", base_url: str = "https://api.kimi.com/coding",
                 default_model: str = "k2.6", **kwargs):
        self.api_key = api_key or self._get_api_key()
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
    
    def _get_api_key(self) -> str:
        """智能获取 API key：参数 > 环境变量 > openclaw.json"""
        # 1. 环境变量
        env_key = os.getenv("KIMI_API_KEY", "")
        if env_key:
            return env_key
        
        # 2. 从 openclaw.json 读取
        try:
            config_path = "/root/.openclaw/openclaw.json"
            with open(config_path, 'r') as f:
                config = json.load(f)
            # 尝试多个可能的位置
            for key_path in [
                ["env", "KIMI_API_KEY"],
                ["models", "providers", "kimi-coding", "apiKey"],
                ["plugins", "entries", "kimi-claw", "config", "defaultModel", "apiKey"],
            ]:
                val = config
                for k in key_path:
                    if isinstance(val, dict) and k in val:
                        val = val[k]
                    else:
                        val = None
                        break
                if val and isinstance(val, str) and val.startswith("sk-"):
                    return val
        except:
            pass
        
        return ""
    
    def chat(self, messages: List[Dict[str, str]], model: str = "default",
             max_tokens: int = 4096, temperature: float = 0.7) -> str:
        """直接调用 Kimi API"""
        if not self.api_key:
            return "[Error] API key not configured"
        
        model_id = model if model != "default" else self.default_model
        
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[Error] Kimi API call failed: {str(e)[:100]}"
    
    def embed(self, text: str, model: str = "default") -> List[float]:
        """Kimi embedding API（预留）"""
        # Kimi 目前公开的 embedding API 可能需要额外配置
        # 这里返回 mock，实际使用时实现
        return [0.0] * 1024  # mock 1024维向量
    
    def list_models(self) -> List[str]:
        return ["k2.6", "k2p5"]
    
    def health_check(self) -> bool:
        """检查 API key 是否有效"""
        if not self.api_key:
            return False
        # 尝试一个极小的请求
        try:
            req = urllib.request.Request(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except:
            return False


class NativeKimiToolAdapter(ToolAdapter):
    """
    原生 Kimi 工具适配器
    
    策略：直接 exec 调用 OpenClaw CLI，不通过 OpenClaw Gateway。
    这样即使 Gateway 挂了，工具还能用（只要 CLI 可用）。
    """
    
    def __init__(self, **kwargs):
        self.kwargs = kwargs
    
    def call(self, tool_name: str, params: Dict[str, Any]) -> Dict:
        """通过 CLI 调用工具"""
        import subprocess
        
        # 构建 CLI 参数
        args = ["openclaw", tool_name]
        
        # 根据工具名添加参数
        if tool_name == "search":
            args.extend([params.get("query", ""), "--count", str(params.get("count", 5))])
        elif tool_name == "fetch":
            args.extend([params.get("url", "")])
        elif tool_name == "finance":
            args.extend([params.get("ticker", ""), "--file-path", params.get("file_path", "/tmp/finance.csv")])
        elif tool_name == "message":
            # 消息发送需要目标
            target = params.get("target", "o9cq806JQxsn4CVsKFpl4wX-kCr8@im.wechat")
            args.extend(["send", "--target", target, "--message", params.get("message", "")])
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=30,
                cwd="/root/.openclaw/workspace"
            )
            if result.returncode == 0:
                return {"success": True, "data": {"raw_output": result.stdout[:1000]}}
            else:
                return {"success": False, "error": f"CLI error: {result.stderr[:200]}"}
        except Exception as e:
            return {"success": False, "error": f"Exception: {str(e)[:100]}"}
    
    def list_tools(self) -> Dict[str, Dict]:
        return {
            "search": {"description": "搜索互联网", "params": ["query", "count"]},
            "fetch": {"description": "抓取网页", "params": ["url"]},
            "finance": {"description": "股票数据", "params": ["ticker", "file_path"]},
            "message": {"description": "发送消息", "params": ["message", "target"]},
        }
    
    def can_handle(self, action: str) -> bool:
        return action in self.list_tools()
    
    def health_check(self) -> bool:
        """检查 openclaw CLI 是否可用"""
        import subprocess
        try:
            result = subprocess.run(
                ["openclaw", "--version"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except:
            return False


class NativeKimiChannelBridge(ChannelBridge):
    """
    原生 Kimi 渠道桥接
    
    策略：直接调用 openclaw message CLI，不通过 Gateway。
    """
    
    def __init__(self, default_target: str = "o9cq806JQxsn4CVsKFpl4wX-kCr8@im.wechat", **kwargs):
        self.default_target = default_target
    
    def send(self, message: str, to: str = "", channel: str = "default",
             priority: str = "normal", media: Optional[str] = None) -> bool:
        import subprocess
        
        target = to or self.default_target
        args = [
            "openclaw", "message", "send",
            "--target", target,
            "--message", message,
        ]
        if channel and channel != "default":
            args.extend(["--channel", channel])
        if media:
            args.extend(["--media", media])
        
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except:
            return False
    
    def read(self, from_user: str = "", since: Optional[str] = None,
             limit: int = 10) -> List[Dict]:
        # 原生实现暂不支持消息读取
        return []
    
    def list_channels(self) -> List[str]:
        return ["openclaw-weixin"]
    
    def health_check(self) -> bool:
        """检查消息发送能力"""
        import subprocess
        try:
            result = subprocess.run(
                ["openclaw", "message", "--help"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except:
            return False


class NativeKimiProvider(ModelProvider, ToolAdapter, ChannelBridge):
    """原生 Kimi 统一提供者（实现全部三个接口）"""
    
    def __init__(self, api_key: str = "", base_url: str = "https://api.kimi.com/coding",
                 default_model: str = "k2.6", **kwargs):
        self._model = NativeKimiModelProvider(api_key=api_key, base_url=base_url, default_model=default_model)
        self._tool = NativeKimiToolAdapter(**kwargs)
        self._channel = NativeKimiChannelBridge(**kwargs)
    
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
