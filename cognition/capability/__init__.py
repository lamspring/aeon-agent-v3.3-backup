from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ModelProvider(ABC):
    """
    模型提供者抽象接口
    
    职责: 提供 LLM 聊天和嵌入能力
    Aeon Core 只依赖此接口，不关心具体是 Kimi/DeepSeek/本地模型
    """
    
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], 
             model: str = "default",
             max_tokens: int = 4096,
             temperature: float = 0.7) -> str:
        """
        聊天接口
        
        Args:
            messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
            model: 模型标识
            max_tokens: 最大输出长度
            temperature: 温度
        
        Returns:
            模型回复文本
        """
        pass
    
    @abstractmethod
    def embed(self, text: str, model: str = "default") -> List[float]:
        """
        文本嵌入
        
        Args:
            text: 输入文本
            model: 嵌入模型
        
        Returns:
            向量列表
        """
        pass
    
    @abstractmethod
    def list_models(self) -> List[str]:
        """返回可用模型列表"""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """检查提供者是否可用"""
        pass


class ToolAdapter(ABC):
    """
    工具适配器抽象接口
    
    职责: 提供外部工具调用能力（搜索、股票、浏览器等）
    Aeon Core 只依赖此接口，不关心具体怎么实现
    """
    
    @abstractmethod
    def call(self, tool_name: str, params: Dict[str, Any]) -> Dict:
        """
        调用工具
        
        Args:
            tool_name: 工具名
            params: 工具参数
        
        Returns:
            {"success": bool, "data": ..., "error": str}
        """
        pass
    
    @abstractmethod
    def list_tools(self) -> Dict[str, Dict]:
        """
        列出可用工具
        
        Returns:
            {"tool_name": {"description": "...", "params": [...]}}
        """
        pass
    
    @abstractmethod
    def can_handle(self, action: str) -> bool:
        """检查是否支持某个 action"""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """检查适配器是否可用"""
        pass


class ChannelBridge(ABC):
    """
    渠道桥接抽象接口
    
    职责: 提供与用户通信的能力（微信/飞书/邮件等）
    Aeon Core 只依赖此接口，不关心具体渠道
    """
    
    @abstractmethod
    def send(self, message: str, to: str = "", 
             channel: str = "default",
             priority: str = "normal",
             media: Optional[str] = None) -> bool:
        """
        发送消息
        
        Args:
            message: 消息内容
            to: 接收者标识
            channel: 渠道标识
            priority: 优先级 (urgent/high/normal/low)
            media: 媒体文件路径
        
        Returns:
            是否发送成功
        """
        pass
    
    @abstractmethod
    def read(self, from_user: str = "", since: Optional[str] = None,
             limit: int = 10) -> List[Dict]:
        """
        读取消息
        
        Args:
            from_user: 指定用户
            since: 时间戳（ISO格式）
            limit: 最大条数
        
        Returns:
            [{"from": "...", "content": "...", "timestamp": "..."}]
        """
        pass
    
    @abstractmethod
    def list_channels(self) -> List[str]:
        """返回可用渠道列表"""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """检查渠道是否可用"""
        pass
