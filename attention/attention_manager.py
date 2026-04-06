"""
Attention Manager - 注意力管理器

核心职责:
- 从 EventBus 获取待处理事件
- 根据当前 Goal 计算相关性
- 按优先级排序，动态 Top-K
- 返回过滤后的事件给 Cognition Loop

位置: Cognition Loop 层（而非 Event Bus 层）
原因: 保持 Event Bus 简单，注意力是"认知"层面的决策
"""

import time
import logging
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass

from attention.config import AttentionConfig
from attention.scoring import AttentionScorer, EventContext
from goals import GoalManager, get_goal_manager

logger = logging.getLogger(__name__)


@dataclass
class AttentionResult:
    """注意力处理结果"""
    events: List[Dict[str, Any]]
    total_scanned: int
    filtered_count: int
    top_k: int
    threshold: float
    goal_keywords: Set[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "events_count": len(self.events),
            "total_scanned": self.total_scanned,
            "filtered_count": self.filtered_count,
            "top_k": self.top_k,
            "threshold": self.threshold,
            "goal_keywords": list(self.goal_keywords),
        }


class AttentionManager:
    """
    注意力管理器
    
    使用方式:
        attention = AttentionManager()
        result = attention.get_relevant_events(pending_events)
        
        for event in result.events:
            process(event)
    """
    
    def __init__(
        self,
        goal_manager: Optional[GoalManager] = None,
        config: Optional[AttentionConfig] = None
    ):
        self.goal_manager = goal_manager or get_goal_manager()
        self.config = config or AttentionConfig.default()
        self.scorer = AttentionScorer(self.config)
        
        # 统计
        self.stats = {
            "total_scanned": 0,
            "total_filtered": 0,
            "total_selected": 0,
        }
        
        logger.info("AttentionManager initialized", extra={
            "config": self.config.to_dict()
        })
    
    def get_relevant_events(
        self,
        pending_events: List[Dict[str, Any]],
        goal_keywords: Optional[Set[str]] = None
    ) -> AttentionResult:
        """
        获取与当前目标相关的事件
        
        流程:
        1. 获取当前 Goal 的 keywords
        2. 批量计算相关性
        3. 按阈值过滤
        4. 动态 Top-K
        5. 返回结果
        
        Args:
            pending_events: 待处理事件列表
            goal_keywords: 手动指定目标关键词（默认使用当前 Goal）
        
        Returns:
            AttentionResult 包含过滤后的事件和元信息
        """
        if not pending_events:
            return AttentionResult(
                events=[],
                total_scanned=0,
                filtered_count=0,
                top_k=0,
                threshold=self.config.min_score_threshold,
                goal_keywords=set()
            )
        
        # 1. 获取目标关键词
        if goal_keywords is None:
            goal_keywords = self._get_current_goal_keywords()
        
        # 2. 批量计算相关性
        current_time = time.time()
        scored_events = self.scorer.batch_calculate(
            pending_events,
            goal_keywords,
            current_time
        )
        
        total_scanned = len(scored_events)
        
        # 3. 按阈值过滤
        filtered = self.scorer.filter_by_threshold(scored_events)
        filtered_count = len(filtered)
        
        # 4. 动态 Top-K
        queue_size = len(pending_events)
        top_k = self.config.get_top_k(queue_size)
        
        # 取前 top_k 个
        selected = filtered[:top_k]
        
        # 更新统计
        self.stats["total_scanned"] += total_scanned
        self.stats["total_filtered"] += filtered_count
        self.stats["total_selected"] += len(selected)
        
        logger.debug(
            f"Attention filter: {total_scanned} scanned, "
            f"{filtered_count} passed threshold, {len(selected)} selected (top_k={top_k})",
            extra={
                "total_scanned": total_scanned,
                "filtered_count": filtered_count,
                "selected_count": len(selected),
                "top_k": top_k,
                "goal_keywords": list(goal_keywords),
            }
        )
        
        return AttentionResult(
            events=selected,
            total_scanned=total_scanned,
            filtered_count=filtered_count,
            top_k=top_k,
            threshold=self.config.min_score_threshold,
            goal_keywords=goal_keywords
        )
    
    def _get_current_goal_keywords(self) -> Set[str]:
        """获取当前目标的关键词"""
        goal = self.goal_manager.get_active_goal()
        
        if goal is None:
            # 没有 active goal，返回空集合（给中等分数）
            return set()
        
        # 使用 Goal 的 get_keywords() 方法
        return goal.get_keywords()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "config": self.config.to_dict(),
        }
    
    def reset_stats(self):
        """重置统计"""
        self.stats = {
            "total_scanned": 0,
            "total_filtered": 0,
            "total_selected": 0,
        }


# 全局实例
_attention_manager_instance: Optional[AttentionManager] = None


def get_attention_manager() -> AttentionManager:
    """获取全局 AttentionManager 实例"""
    global _attention_manager_instance
    if _attention_manager_instance is None:
        _attention_manager_instance = AttentionManager()
    return _attention_manager_instance


def set_attention_manager(manager: AttentionManager):
    """设置全局 AttentionManager 实例"""
    global _attention_manager_instance
    _attention_manager_instance = manager
