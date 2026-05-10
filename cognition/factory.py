#!/usr/bin/env python3
"""
ProviderFactory - 能力提供者工厂 v1.0

根据配置动态加载 ModelProvider / ToolAdapter / ChannelBridge 实现。

配置位置: /root/.openclaw/workspace/agent/config/provider_config.json

示例配置:
{
    "active": {
        "model": "openclaw",
        "tool": "openclaw",
        "channel": "openclaw"
    },
    "providers": {
        "openclaw": {
            "module": "providers.openclaw_provider",
            "class": "OpenClawProvider",
            "config": {}
        },
        "native_kimi": {
            "module": "providers.native_kimi_provider",
            "class": "NativeKimiProvider",
            "config": {
                "api_key": "${KIMI_API_KEY}",
                "base_url": "https://api.kimi.com/coding"
            }
        }
    }
}

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import json
import importlib
import os
from pathlib import Path
from typing import Dict, Optional, Any

from capability import ModelProvider, ToolAdapter, ChannelBridge


class ProviderFactory:
    """
    能力提供者工厂
    
    单例模式，全局统一管理所有 Provider 实例。
    """
    
    _instance = None
    _providers = {}
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_path: Optional[str] = None):
        if self._initialized:
            return
        
        self.config_path = config_path or "/root/.openclaw/workspace/agent/config/provider_config.json"
        self._load_config()
        self._initialized = True
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                self._config = json.load(f)
        except FileNotFoundError:
            # 默认配置：全部使用 OpenClaw
            self._config = {
                "active": {
                    "model": "openclaw",
                    "tool": "openclaw",
                    "channel": "openclaw"
                },
                "providers": {
                    "openclaw": {
                        "module": "providers.openclaw_provider",
                        "class": "OpenClawProvider",
                        "config": {}
                    }
                }
            }
            self._save_config()
    
    def _save_config(self):
        """保存配置文件"""
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
    
    def _resolve_env_vars(self, config: Dict) -> Dict:
        """解析环境变量引用 ${VAR_NAME}"""
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                resolved[key] = os.getenv(env_var, value)
            else:
                resolved[key] = value
        return resolved
    
    def _get_provider_instance(self, name: str) -> Any:
        """
        获取或创建 Provider 实例
        
        Args:
            name: Provider 名称（如 "openclaw", "native_kimi"）
        
        Returns:
            Provider 实例
        """
        if name in self._providers:
            return self._providers[name]
        
        provider_config = self._config.get("providers", {}).get(name)
        if not provider_config:
            raise ValueError(f"Provider '{name}' not found in config")
        
        module_path = provider_config["module"]
        class_name = provider_config["class"]
        init_config = self._resolve_env_vars(provider_config.get("config", {}))
        
        # 动态导入模块
        try:
            module = importlib.import_module(module_path)
            ProviderClass = getattr(module, class_name)
            instance = ProviderClass(**init_config)
            self._providers[name] = instance
            return instance
        except Exception as e:
            raise RuntimeError(f"Failed to load provider '{name}': {e}")
    
    def get_model(self) -> ModelProvider:
        """获取当前活跃的模型提供者"""
        active = self._config["active"]["model"]
        return self._get_provider_instance(active)
    
    def get_tool(self) -> ToolAdapter:
        """获取当前活跃的工具适配器"""
        active = self._config["active"]["tool"]
        return self._get_provider_instance(active)
    
    def get_channel(self) -> ChannelBridge:
        """获取当前活跃的渠道桥接"""
        active = self._config["active"]["channel"]
        return self._get_provider_instance(active)
    
    def switch(self, capability: str, provider_name: str) -> bool:
        """
        切换 Provider
        
        Args:
            capability: "model" | "tool" | "channel"
            provider_name: 目标 Provider 名称
        
        Returns:
            是否切换成功
        """
        if provider_name not in self._config.get("providers", {}):
            print(f"[ProviderFactory] Unknown provider: {provider_name}")
            return False
        
        # 健康检查
        try:
            instance = self._get_provider_instance(provider_name)
            if not instance.health_check():
                print(f"[ProviderFactory] Provider '{provider_name}' health check failed")
                return False
        except Exception as e:
            print(f"[ProviderFactory] Provider '{provider_name}' unavailable: {e}")
            return False
        
        # 切换
        old = self._config["active"][capability]
        self._config["active"][capability] = provider_name
        self._save_config()
        
        print(f"[ProviderFactory] Switched {capability}: {old} -> {provider_name}")
        return True
    
    def list_providers(self) -> Dict[str, list]:
        """列出所有可用 Provider"""
        providers = self._config.get("providers", {})
        active = self._config.get("active", {})
        
        result = {}
        for cap in ["model", "tool", "channel"]:
            result[cap] = {
                "active": active.get(cap),
                "available": list(providers.keys())
            }
        return result
    
    def health_check(self) -> Dict[str, bool]:
        """检查所有活跃 Provider 健康状态"""
        results = {}
        for cap in ["model", "tool", "channel"]:
            try:
                provider = getattr(self, f"get_{cap}")()
                results[cap] = provider.health_check()
            except Exception as e:
                results[cap] = False
                print(f"[ProviderFactory] {cap} health check failed: {e}")
        return results


# ============== 快速测试 ==============
if __name__ == "__main__":
    factory = ProviderFactory()
    
    print("=== ProviderFactory v1.0 ===")
    print(f"Config: {factory._config}")
    print(f"Providers: {factory.list_providers()}")
    
    # 健康检查
    health = factory.health_check()
    print(f"Health: {health}")
