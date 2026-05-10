from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional


@dataclass
class MessageDigest:
    """单条消息的摘要"""
    message_id: str
    timestamp: datetime
    channel: str
    user_id: str
    content_preview: str  # 前100字
    
    # 规则分析结果
    topic: str  # "技术", "情感", "创作", "系统", "日常"
    emotion: str  # "positive", "neutral", "negative"
    is_explicit_todo: bool  # 是否显式待办（"帮我"/"查一下"）
    
    # 元数据
    hour: int  # 消息发送小时（用于熬夜检测）


@dataclass  
class DailyDigest:
    """一天的摘要"""
    date: str  # YYYY-MM-DD
    generated_at: datetime
    
    # 统计
    total_messages: int
    channels: List[str]
    topic_distribution: Dict[str, int]  # {"技术": 5, "情感": 3, ...}
    emotion_distribution: Dict[str, int]  # {"positive": 3, ...}
    
    # 详细数据
    message_digests: List[MessageDigest]
    explicit_todos: List[Dict]  # 显式待办列表
    
    # 洞察（P1阶段LLM生成）
    late_night_flag: bool  # 是否有深夜消息（23点后）
    late_night_hours: List[int]  # 具体熬夜的小时 [23, 0, 1]
    key_topics: List[str]  # 关键主题（去重后的）
    llm_insight: Optional[str]  # LLM生成的洞察（P0可为空）
