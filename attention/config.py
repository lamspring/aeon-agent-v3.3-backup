"""
Attention Config - 注意力系统配置

核心参数:
- max_events_per_tick: 每轮处理事件数上限
- decay_factor: 时间衰减因子 (0.95 = 5%衰减/小时)
- min_score_threshold: 最低相关性阈值
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class AttentionConfig:
    """
    注意力系统配置
    
    Attributes:
        max_events_per_tick: 每轮最多处理的事件数 (默认5)
        decay_factor: 时间衰减因子 (默认0.95，即每小时衰减5%)
        min_score_threshold: 最低相关性阈值 (默认0.1)
        top_k: 动态 Top-K (根据 queue_size 调整)
        boost_keywords: 关键词匹配时的额外加分
    """
    max_events_per_tick: int = 5
    decay_factor: float = 0.95  # 每小时衰减系数
    min_score_threshold: float = 0.1
    top_k_base: int = 3
    top_k_max: int = 10
    boost_keywords: Dict[str, float] = None
    
    def __post_init__(self):
        if self.boost_keywords is None:
            self.boost_keywords = {
                "error": 1.5,
                "critical": 2.0,
                "urgent": 1.8,
                "failed": 1.3,
                "timeout": 1.2,
            }
    
    def get_top_k(self, queue_size: int) -> int:
        """
        动态 Top-K 策略
        
        queue_size 小的时候关注质量，大的时候扩大处理量
        """
        if queue_size < 10:
            return self.top_k_base
        elif queue_size < 50:
            return min(self.top_k_base + 2, self.top_k_max)
        else:
            return self.top_k_max
    
    def calculate_decay(self, hours_elapsed: float) -> float:
        """
        计算时间衰减
        
        公式: decay_factor ^ hours_elapsed
        """
        return self.decay_factor ** hours_elapsed
    
    @classmethod
    def default(cls) -> 'AttentionConfig':
        """默认配置"""
        return cls()
    
    @classmethod
    def aggressive(cls) -> 'AttentionConfig':
        """激进配置（高吞吐量）"""
        return cls(
            max_events_per_tick=10,
            decay_factor=0.9,  # 更快衰减
            min_score_threshold=0.05,  # 更低阈值
            top_k_base=5,
            top_k_max=20,
        )
    
    @classmethod
    def conservative(cls) -> 'AttentionConfig':
        """保守配置（高质量）"""
        return cls(
            max_events_per_tick=3,
            decay_factor=0.98,  # 更慢衰减
            min_score_threshold=0.3,  # 更高阈值
            top_k_base=2,
            top_k_max=5,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_events_per_tick": self.max_events_per_tick,
            "decay_factor": self.decay_factor,
            "min_score_threshold": self.min_score_threshold,
            "top_k_base": self.top_k_base,
            "top_k_max": self.top_k_max,
            "boost_keywords": self.boost_keywords,
        }
