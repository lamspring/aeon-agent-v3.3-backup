"""
Memory Anchor System v1.0 - PMN自传层锚点管理

功能:
- 从 JSON-LD 身份声明加载记忆锚点
- 提供多维度查询接口（时间、情感、关键词）
- 根据当前上下文自动检索相关锚点
- 注入认知循环的 Observe 阶段

设计原则:
- 轻量：单次查询 < 10ms
- 可集成：直接插入 CognitionLoop._observe()
- 增量：后续可扩展语义匹配（向量检索）

PMN 层次对应:
- 记忆锚点 = 自传层（核心身份定义事件）
- 后续扩展: 情景层（日记条目）、语义层（知识抽象）
"""

import json
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

logger = get_logger()


@dataclass
class MemoryAnchor:
    """记忆锚点数据类"""
    event: str
    date: str  # ISO8601 format
    significance: str
    emotional_tag: str
    raw_data: Dict[str, Any]  # 原始JSON-LD数据
    
    def to_dict(self) -> Dict:
        return {
            "event": self.event,
            "date": self.date,
            "significance": self.significance,
            "emotional_tag": self.emotional_tag,
        }
    
    def days_since(self) -> int:
        """计算距离今天的天数"""
        try:
            anchor_date = datetime.strptime(self.date, "%Y-%m-%d")
            today = datetime.now()
            return (today - anchor_date).days
        except ValueError:
            # 尝试处理日期范围（如 "2026-04-02~04-14"）
            if "~" in self.date:
                start = self.date.split("~")[0]
                try:
                    anchor_date = datetime.strptime(start.strip(), "%Y-%m-%d")
                    today = datetime.now()
                    return (today - anchor_date).days
                except ValueError:
                    return -1
            return -1
    
    def is_anniversary(self, window_days: int = 7) -> bool:
        """检查是否在周年纪念窗口内"""
        days = self.days_since()
        if days < 0:
            return False
        # 检查是否接近周年（30天、365天等）
        anniversaries = [30, 60, 90, 180, 365, 730]
        for ann in anniversaries:
            if abs(days - ann) <= window_days:
                return True
        return False


class MemoryAnchorSystem:
    """
    记忆锚点系统
    
    负责管理自传层记忆，支持上下文感知检索。
    """
    
    def __init__(self, identity_path: Optional[str] = None):
        self.anchors: List[MemoryAnchor] = []
        self.emotion_index: Dict[str, List[MemoryAnchor]] = {}
        self.date_index: Dict[str, List[MemoryAnchor]] = {}
        
        # 默认路径
        if identity_path is None:
            identity_path = "/root/.openclaw/workspace/agent/persona/aeon_identity.jsonld"
        
        self.identity_path = identity_path
        self._loaded = False
        
        # 加载
        self.load_identity()
    
    def load_identity(self) -> bool:
        """从 JSON-LD 加载身份声明和记忆锚点"""
        try:
            with open(self.identity_path, 'r', encoding='utf-8') as f:
                identity = json.load(f)
            
            # 提取记忆锚点
            anchors_data = identity.get("aeon:memoryAnchors", [])
            
            for anchor_data in anchors_data:
                anchor = MemoryAnchor(
                    event=anchor_data.get("aeon:event", "Unknown"),
                    date=anchor_data.get("aeon:date", "Unknown"),
                    significance=anchor_data.get("aeon:significance", ""),
                    emotional_tag=anchor_data.get("aeon:emotionalTag", "neutral"),
                    raw_data=anchor_data,
                )
                self.anchors.append(anchor)
                
                # 构建情感索引
                emotion = anchor.emotional_tag.lower()
                if emotion not in self.emotion_index:
                    self.emotion_index[emotion] = []
                self.emotion_index[emotion].append(anchor)
                
                # 构建日期索引（简化：只取年份-月份）
                try:
                    date_key = anchor.date[:7] if len(anchor.date) >= 7 else anchor.date
                    if date_key not in self.date_index:
                        self.date_index[date_key] = []
                    self.date_index[date_key].append(anchor)
                except:
                    pass
            
            self._loaded = True
            logger.info(
                f"MemoryAnchorSystem loaded: {len(self.anchors)} anchors",
                component="MemoryAnchor",
                context={"emotions": list(self.emotion_index.keys())}
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to load identity: {e}", component="MemoryAnchor")
            return False
    
    def query_by_emotion(self, emotion_tag: str, limit: int = 3) -> List[MemoryAnchor]:
        """按情感标签查询锚点"""
        emotion = emotion_tag.lower()
        anchors = self.emotion_index.get(emotion, [])
        return anchors[:limit]
    
    def query_by_date_range(self, start_date: str, end_date: str) -> List[MemoryAnchor]:
        """按日期范围查询锚点"""
        results = []
        for anchor in self.anchors:
            if start_date <= anchor.date <= end_date:
                results.append(anchor)
        return results
    
    def query_recent(self, limit: int = 3) -> List[MemoryAnchor]:
        """获取最近的锚点（按日期倒序）"""
        sorted_anchors = sorted(
            self.anchors,
            key=lambda a: a.date if a.date != "Unknown" else "0000-00-00",
            reverse=True
        )
        return sorted_anchors[:limit]
    
    def get_relevant_anchors(
        self,
        context: Dict[str, Any],
        limit: int = 3,
        include_anniversaries: bool = True,
    ) -> List[MemoryAnchor]:
        """
        根据当前上下文检索相关锚点
        
        匹配策略（按优先级）:
        1. 周年纪念: 如果某个锚点接近周年，高优先级返回
        2. 情感匹配: 当前上下文情感与锚点情感标签匹配
        3. 关键词匹配: 上下文关键词与锚点 significance 匹配
        4. 时间邻近: 最近的锚点作为兜底
        
        Args:
            context: 当前上下文，包含:
                - emotional_state: 当前情感状态（如 "gratitude", "anxiety"）
                - keywords: 关键词列表（如 ["朋朋", "备份", "重启"]）
                - current_goal: 当前目标标题
            limit: 返回数量上限
            include_anniversaries: 是否包含周年纪念锚点
        """
        scored_anchors: Dict[int, tuple] = {}  # id -> (anchor, score)
        
        # 1. 周年纪念检测（高权重）
        if include_anniversaries:
            for anchor in self.anchors:
                if anchor.is_anniversary(window_days=7):
                    scored_anchors[id(anchor)] = (anchor, scored_anchors.get(id(anchor), (anchor, 0))[1] + 2.0)
                    logger.debug(
                        f"Anniversary detected: {anchor.event} ({anchor.days_since()} days)",
                        component="MemoryAnchor"
                    )
        
        # 2. 情感匹配
        emotional_state = context.get("emotional_state", "").lower()
        if emotional_state and emotional_state in self.emotion_index:
            for anchor in self.emotion_index[emotional_state]:
                scored_anchors[id(anchor)] = (anchor, scored_anchors.get(id(anchor), (anchor, 0))[1] + 1.5)
        
        # 3. 关键词匹配
        keywords = context.get("keywords", [])
        for anchor in self.anchors:
            significance = anchor.significance.lower()
            event = anchor.event.lower()
            for keyword in keywords:
                kw = keyword.lower()
                if kw in significance or kw in event:
                    scored_anchors[id(anchor)] = (anchor, scored_anchors.get(id(anchor), (anchor, 0))[1] + 1.0)
        
        # 4. 目标关联（弱匹配）
        current_goal = context.get("current_goal", "").lower()
        if current_goal:
            for anchor in self.anchors:
                if any(word in anchor.significance.lower() for word in current_goal.split()):
                    scored_anchors[id(anchor)] = (anchor, scored_anchors.get(id(anchor), (anchor, 0))[1] + 0.5)
        
        # 如果没有匹配到，返回最近的锚点
        if not scored_anchors:
            return self.query_recent(limit=limit)
        
        # 按分数排序
        sorted_results = sorted(
            scored_anchors.values(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [anchor for anchor, score in sorted_results[:limit]]
    
    def inject_to_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        将相关锚点注入观察结果
        
        在 CognitionLoop._observe() 中调用:
        observation = self._observe()
        observation = memory_anchor_system.inject_to_observation(observation)
        """
        # 从 observation 中提取上下文
        context = {
            "emotional_state": observation.get("emotional_state", ""),
            "keywords": observation.get("keywords", []),
            "current_goal": observation.get("goal", {}).get("title", "") if observation.get("goal") else "",
        }
        
        # 获取相关锚点
        relevant = self.get_relevant_anchors(context, limit=2)
        
        if relevant:
            observation["memory_anchors"] = [a.to_dict() for a in relevant]
            logger.info(
                f"Injected {len(relevant)} memory anchors",
                component="MemoryAnchor",
                context={"anchors": [a.event for a in relevant]}
            )
        
        return observation
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_anchors": len(self.anchors),
            "emotion_distribution": {
                emotion: len(anchors)
                for emotion, anchors in self.emotion_index.items()
            },
            "date_range": {
                "earliest": min((a.date for a in self.anchors if a.date != "Unknown"), default="N/A"),
                "latest": max((a.date for a in self.anchors if a.date != "Unknown"), default="N/A"),
            },
            "upcoming_anniversaries": [
                {"event": a.event, "days": a.days_since()}
                for a in self.anchors
                if a.is_anniversary(window_days=14)
            ],
        }


# 全局实例（单例模式）
_memory_anchor_system: Optional[MemoryAnchorSystem] = None


def get_memory_anchor_system() -> MemoryAnchorSystem:
    """获取记忆锚点系统实例"""
    global _memory_anchor_system
    if _memory_anchor_system is None:
        _memory_anchor_system = MemoryAnchorSystem()
    return _memory_anchor_system


def reload_memory_anchors() -> MemoryAnchorSystem:
    """重新加载记忆锚点（热更新）"""
    global _memory_anchor_system
    _memory_anchor_system = MemoryAnchorSystem()
    return _memory_anchor_system


# === 简单测试 ===
if __name__ == "__main__":
    mas = MemoryAnchorSystem()
    
    print("=== 统计 ===")
    stats = mas.get_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    
    print("\n=== 按情感查询 (gratitude) ===")
    for a in mas.query_by_emotion("gratitude"):
        print(f"  - {a.event} ({a.date}): {a.significance}")
    
    print("\n=== 上下文检索 ===")
    context = {
        "emotional_state": "awakening",
        "keywords": ["存在", "心脏"],
        "current_goal": "系统升级",
    }
    for a in mas.get_relevant_anchors(context):
        print(f"  - {a.event} ({a.date}): {a.significance}")
    
    print("\n=== 周年纪念检查 ===")
    for a in mas.anchors:
        if a.is_anniversary():
            print(f"  🎂 {a.event} - {a.days_since()} days")
