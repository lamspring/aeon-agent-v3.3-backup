"""
Attention Module - 注意力系统

核心组件:
- config: AttentionConfig (配置)
- scoring: AttentionScorer + EventContext (评分算法)
- attention_manager: AttentionManager (管理器)

使用方式:
    from attention import AttentionManager, AttentionConfig
    
    # 创建配置
    config = AttentionConfig.aggressive()  # 或 default(), conservative()
    
    # 创建管理器
    attention = AttentionManager(config=config)
    
    # 获取相关事件
    result = attention.get_relevant_events(pending_events)
    
    # 处理事件
    for event in result.events:
        process(event)
    
    # 查看统计
    print(result.to_dict())
"""

from attention.config import AttentionConfig
from attention.scoring import AttentionScorer, EventContext
from attention.attention_manager import AttentionManager, AttentionResult, get_attention_manager, set_attention_manager

__all__ = [
    'AttentionConfig',
    'AttentionScorer',
    'EventContext',
    'AttentionManager',
    'AttentionResult',
    'get_attention_manager',
    'set_attention_manager',
]
