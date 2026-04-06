"""
Attention Scoring - 相关性评分算法

核心算法:
- keyword_match_score: 关键词匹配度 (Jaccard similarity)
- time_decay_score: 时间衰减
- boost_score: 关键词加权
- final_score = match_score * decay * boost

⚠️ 重要: 中文必须手动提供 keywords，不能依赖自动分词
"""

import time
import math
from typing import Set, Dict, Any, Optional
from dataclasses import dataclass

from attention.config import AttentionConfig


@dataclass
class EventContext:
    """事件上下文"""
    event_type: str
    source: Optional[str]
    keywords: Set[str]  # ⚠️ 必须手动提供
    timestamp: float
    data: Dict[str, Any]
    
    @classmethod
    def from_event(cls, event: Dict[str, Any]) -> 'EventContext':
        """从事件字典创建上下文"""
        # 获取 keywords（优先手动提供）
        keywords = set()
        
        # 1. 手动提供的 keywords
        if 'keywords' in event:
            keywords.update([k.lower() for k in event['keywords']])
        
        # 2. 从 context 中提取
        if 'context' in event and isinstance(event['context'], dict):
            ctx_keywords = event['context'].get('keywords', [])
            keywords.update([k.lower() for k in ctx_keywords])
        
        # 3. ⚠️ 不要依赖自动分词
        # 如果还是没有 keywords，记录警告
        if not keywords:
            # 只对英文简单处理
            desc = event.get('description', '') or event.get('data', {}).get('description', '')
            if desc and desc.isascii():
                keywords.update(desc.lower().split()[:5])  # 只取前5个词
        
        return cls(
            event_type=event.get('type', 'unknown'),
            source=event.get('source'),
            keywords=keywords,
            timestamp=event.get('timestamp', time.time()),
            data=event.get('data', {})
        )


class AttentionScorer:
    """
    注意力评分器
    
    计算事件与当前目标的 relevance score
    """
    
    def __init__(self, config: Optional[AttentionConfig] = None):
        self.config = config or AttentionConfig.default()
    
    def calculate_relevance(
        self,
        event: EventContext,
        goal_keywords: Set[str],
        current_time: Optional[float] = None
    ) -> float:
        """
        计算事件与目标的相关性
        
        公式: relevance = keyword_match * time_decay * boost
        
        Args:
            event: 事件上下文
            goal_keywords: 目标关键词集合
            current_time: 当前时间戳（默认 now）
        
        Returns:
            0.0 ~ 1.0 的相关性分数
        """
        if current_time is None:
            current_time = time.time()
        
        # 1. 关键词匹配度 (Jaccard similarity)
        match_score = self._keyword_match_score(event.keywords, goal_keywords)
        
        # 2. 时间衰减
        decay_score = self._time_decay_score(event.timestamp, current_time)
        
        # 3. 关键词加权 (error, critical 等)
        boost_score = self._boost_score(event)
        
        # 4. 综合评分
        relevance = match_score * decay_score * boost_score
        
        return min(relevance, 1.0)  # 上限 1.0
    
    def _keyword_match_score(self, event_keywords: Set[str], goal_keywords: Set[str]) -> float:
        """
        关键词匹配度 (Jaccard similarity)
        
        score = |A ∩ B| / |A ∪ B|
        """
        if not goal_keywords:
            # 如果没有目标关键词，给中等分数
            return 0.5
        
        if not event_keywords:
            # 事件没有关键词，给低分
            return 0.1
        
        intersection = event_keywords & goal_keywords
        union = event_keywords | goal_keywords
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def _time_decay_score(self, event_time: float, current_time: float) -> float:
        """
        时间衰减分数
        
        越旧的事件分数越低
        """
        hours_elapsed = (current_time - event_time) / 3600.0
        
        if hours_elapsed < 0:
            # 未来事件（时钟误差），给满分
            return 1.0
        
        return self.config.calculate_decay(hours_elapsed)
    
    def _boost_score(self, event: EventContext) -> float:
        """
        关键词加权
        
        特定关键词（如 error, critical）给予额外权重
        """
        boost = 1.0
        
        # 检查事件类型
        event_type_lower = event.event_type.lower()
        for keyword, weight in self.config.boost_keywords.items():
            if keyword in event_type_lower:
                boost = max(boost, weight)
        
        # 检查事件关键词
        for kw in event.keywords:
            kw_lower = kw.lower()
            for keyword, weight in self.config.boost_keywords.items():
                if keyword in kw_lower:
                    boost = max(boost, weight)
        
        return boost
    
    def batch_calculate(
        self,
        events: list,
        goal_keywords: Set[str],
        current_time: Optional[float] = None
    ) -> list:
        """
        批量计算相关性
        
        Returns:
            [(event, relevance_score), ...] 按分数排序（高到低）
        """
        results = []
        
        for event_data in events:
            try:
                event_ctx = EventContext.from_event(event_data)
                score = self.calculate_relevance(event_ctx, goal_keywords, current_time)
                results.append((event_data, score))
            except Exception as e:
                # 解析失败给最低分
                results.append((event_data, 0.0))
        
        # 按分数排序（高到低）
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def filter_by_threshold(
        self,
        scored_events: list,
        threshold: Optional[float] = None
    ) -> list:
        """
        按阈值过滤事件
        
        Args:
            scored_events: [(event, score), ...]
            threshold: 阈值（默认使用 config.min_score_threshold）
        
        Returns:
            过滤后的事件列表（只保留 event，去掉 score）
        """
        if threshold is None:
            threshold = self.config.min_score_threshold
        
        return [event for event, score in scored_events if score >= threshold]
