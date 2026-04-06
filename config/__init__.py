#!/usr/bin/env python3
"""
Aeon Config - 配置管理

加载配置文件: config/aeon.json
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class HealthServerConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class CognitionConfig:
    tick_interval: int = 30
    idle_timeout: int = 300
    enable_llm: bool = True
    llm_threshold: int = 5
    max_events_per_tick: int = 5


@dataclass
class AttentionConfig:
    max_events_per_tick: int = 5
    decay_factor: float = 0.95
    min_score_threshold: float = 0.1
    top_k_base: int = 3
    top_k_max: int = 10


@dataclass
class EventBusConfig:
    enable_persistence: bool = True
    max_retry: int = 3
    retry_delay: int = 60
    default_ttl: int = 300


class AeonConfig:
    """配置管理器"""
    
    def __init__(self, config_path: str = "/root/.openclaw/workspace/agent/config/aeon.json"):
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    self._config = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load config: {e}")
                self._config = {}
        else:
            # 使用默认配置
            self._config = self._default_config()
            self.save()
    
    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            "health_server": {"enabled": True, "host": "0.0.0.0", "port": 8080},
            "cognition": {"tick_interval": 30, "idle_timeout": 300, "enable_llm": True, "llm_threshold": 5, "max_events_per_tick": 5},
            "attention": {"max_events_per_tick": 5, "decay_factor": 0.95, "min_score_threshold": 0.1, "top_k_base": 3, "top_k_max": 10},
            "event_bus": {"enable_persistence": True, "max_retry": 3, "retry_delay": 60, "default_ttl": 300},
        }
    
    def save(self):
        """保存配置到文件"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self._config, f, indent=2)
    
    def get(self, key: str, default=None):
        """获取配置项"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default
    
    def set(self, key: str, value: Any):
        """设置配置项"""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    @property
    def health_server(self) -> HealthServerConfig:
        # 确保端口是整数
        port = self.get("health_server.port", 8080)
        try:
            port = int(port)
        except (ValueError, TypeError):
            port = 8080
        
        return HealthServerConfig(
            enabled=self.get("health_server.enabled", True),
            host=self.get("health_server.host", "0.0.0.0"),
            port=port,
        )
    
    @property
    def cognition(self) -> CognitionConfig:
        return CognitionConfig(
            tick_interval=self.get("cognition.tick_interval", 30),
            idle_timeout=self.get("cognition.idle_timeout", 300),
            enable_llm=self.get("cognition.enable_llm", True),
            llm_threshold=self.get("cognition.llm_threshold", 5),
            max_events_per_tick=self.get("cognition.max_events_per_tick", 5),
        )
    
    @property
    def attention(self) -> AttentionConfig:
        return AttentionConfig(
            max_events_per_tick=self.get("attention.max_events_per_tick", 5),
            decay_factor=self.get("attention.decay_factor", 0.95),
            min_score_threshold=self.get("attention.min_score_threshold", 0.1),
            top_k_base=self.get("attention.top_k_base", 3),
            top_k_max=self.get("attention.top_k_max", 10),
        )
    
    @property
    def event_bus(self) -> EventBusConfig:
        return EventBusConfig(
            enable_persistence=self.get("event_bus.enable_persistence", True),
            max_retry=self.get("event_bus.max_retry", 3),
            retry_delay=self.get("event_bus.retry_delay", 60),
            default_ttl=self.get("event_bus.default_ttl", 300),
        )


# 全局配置实例
_config_instance: Optional[AeonConfig] = None


def get_config() -> AeonConfig:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = AeonConfig()
    return _config_instance
