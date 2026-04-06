"""
Memory Index - 记忆索引
核心特性:
- Episodic Memory (时间线记忆)
- Semantic Memory (知识记忆)
- Vector Index (语义搜索)
- Importance Scoring
- Memory Consolidation (每日整合)
"""

import json
import time
import sqlite3
import threading
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import logging

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from bus.event_bus import get_event_bus, EventType, listener
from utils.structured_log import get_logger

logger = get_logger()


class MemoryType(Enum):
    """记忆类型"""
    EPISODIC = "episodic"      # 时间线记忆 (具体事件)
    SEMANTIC = "semantic"      # 知识记忆 (抽象概念)
    CONSOLIDATED = "consolidated"  # 整合后的记忆


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    memory_type: str
    timestamp: float
    
    # 向量嵌入 (可选，None表示未计算)
    embedding: Optional[List[float]] = None
    
    # 重要性评分 (0-1)
    importance: float = 0.5
    
    # 元数据
    metadata: Dict[str, Any] = None
    
    # 标签
    tags: List[str] = None
    
    # 访问统计
    access_count: int = 0
    last_accessed: float = None
    
    # 整合标记
    consolidated: bool = False
    source_memories: List[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.tags is None:
            self.tags = []
        if self.source_memories is None:
            self.source_memories = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "timestamp": self.timestamp,
            "embedding": self.embedding,
            "importance": self.importance,
            "metadata": self.metadata,
            "tags": self.tags,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "consolidated": self.consolidated,
            "source_memories": self.source_memories
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'MemoryEntry':
        """从字典创建"""
        return cls(
            id=d["id"],
            content=d["content"],
            memory_type=d["memory_type"],
            timestamp=d["timestamp"],
            embedding=d.get("embedding"),
            importance=d.get("importance", 0.5),
            metadata=d.get("metadata", {}),
            tags=d.get("tags", []),
            access_count=d.get("access_count", 0),
            last_accessed=d.get("last_accessed"),
            consolidated=d.get("consolidated", False),
            source_memories=d.get("source_memories", [])
        )
    
    def update_access(self):
        """更新访问统计"""
        self.access_count += 1
        self.last_accessed = time.time()


class SimpleEmbedding:
    """
    简单嵌入模型
    
    使用简单的词袋模型作为fallback
    实际生产环境应使用 sentence-transformers
    """
    
    def __init__(self, dim: int = 128):
        self.dim = dim
        self.vocab = {}
        self._lock = threading.Lock()
    
    def _tokenize(self, text: str) -> List[str]:
        """简单分词"""
        # 中文按字，英文按词
        import re
        # 提取中文和英文单词
        tokens = re.findall(r'[\u4e00-\u9fff]|\w+', text.lower())
        return tokens
    
    def _get_or_create_id(self, token: str) -> int:
        """获取或创建token ID"""
        with self._lock:
            if token not in self.vocab:
                self.vocab[token] = len(self.vocab) % self.dim
            return self.vocab[token]
    
    def encode(self, text: str) -> List[float]:
        """编码文本为向量"""
        tokens = self._tokenize(text)
        
        if not tokens:
            return [0.0] * self.dim
        
        # 简单的词袋模型
        vec = [0.0] * self.dim
        for token in tokens:
            idx = self._get_or_create_id(token)
            vec[idx] += 1.0
        
        # 归一化
        norm = sum(x**2 for x in vec) ** 0.5
        if norm > 0:
            vec = [x / norm for x in vec]
        
        return vec
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """批量编码"""
        return [self.encode(text) for text in texts]


class MemoryPersistence:
    """记忆持久化"""
    
    def __init__(self, db_path: str = "/root/.openclaw/workspace/agent/db/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            # Episodic Memory 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    embedding BLOB,
                    importance REAL DEFAULT 0.5,
                    metadata TEXT,
                    tags TEXT,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL,
                    consolidated BOOLEAN DEFAULT FALSE,
                    source_memories TEXT
                )
            """)
            
            # Semantic Memory 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    concept TEXT NOT NULL,
                    definition TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    embedding BLOB,
                    importance REAL DEFAULT 0.5,
                    associations TEXT,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic_memory(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_episodic_consolidated ON episodic_memory(consolidated)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_concept ON semantic_memory(concept)")
            
            conn.commit()
    
    def store_episodic(self, memory: MemoryEntry):
        """存储时间线记忆"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO episodic_memory VALUES 
                   (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    memory.id,
                    memory.content,
                    memory.timestamp,
                    json.dumps(memory.embedding) if memory.embedding else None,
                    memory.importance,
                    json.dumps(memory.metadata),
                    json.dumps(memory.tags),
                    memory.access_count,
                    memory.last_accessed,
                    memory.consolidated,
                    json.dumps(memory.source_memories)
                )
            )
            conn.commit()
    
    def get_episodic(self, memory_id: str) -> Optional[MemoryEntry]:
        """获取时间线记忆"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM episodic_memory WHERE id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return self._row_to_episodic(row)
            return None
    
    def get_episodic_range(self, start_time: float, end_time: float) -> List[MemoryEntry]:
        """获取时间范围内的记忆"""
        memories = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT * FROM episodic_memory 
                   WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp""",
                (start_time, end_time)
            )
            
            for row in cursor.fetchall():
                memories.append(self._row_to_episodic(row))
        
        return memories
    
    def get_unconsolidated_episodic(self, min_count: int = 10) -> List[MemoryEntry]:
        """获取未整合的时间线记忆"""
        memories = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT * FROM episodic_memory 
                   WHERE consolidated = FALSE
                   ORDER BY timestamp"""
            )
            
            for row in cursor.fetchall():
                memories.append(self._row_to_episodic(row))
        
        return memories
    
    def mark_consolidated(self, memory_ids: List[str]):
        """标记记忆已整合"""
        with sqlite3.connect(self.db_path) as conn:
            for mid in memory_ids:
                conn.execute(
                    "UPDATE episodic_memory SET consolidated = TRUE WHERE id = ?",
                    (mid,)
                )
            conn.commit()
    
    def _row_to_episodic(self, row) -> MemoryEntry:
        """行转对象"""
        return MemoryEntry(
            id=row[0],
            content=row[1],
            memory_type=MemoryType.EPISODIC.value,
            timestamp=row[2],
            embedding=json.loads(row[3]) if row[3] else None,
            importance=row[4],
            metadata=json.loads(row[5]) if row[5] else {},
            tags=json.loads(row[6]) if row[6] else [],
            access_count=row[7] or 0,
            last_accessed=row[8],
            consolidated=row[9] or False,
            source_memories=json.loads(row[10]) if row[10] else []
        )
    
    def cleanup_low_importance(self, threshold: float = 0.2, min_age_days: int = 30):
        """清理低重要性记忆"""
        cutoff = time.time() - (min_age_days * 86400)
        
        with sqlite3.connect(self.db_path) as conn:
            # 删除旧的、低重要性的、已整合的记忆
            conn.execute(
                """DELETE FROM episodic_memory 
                   WHERE importance < ? 
                   AND timestamp < ?
                   AND consolidated = TRUE""",
                (threshold, cutoff)
            )
            conn.commit()


class ImportanceScorer:
    """重要性评分器"""
    
    def calculate(self, memory: MemoryEntry) -> float:
        """
        计算记忆重要性
        
        公式: importance = f(recency, frequency, emotional_weight, relevance)
        """
        # 时效性 (越新越重要)
        age_hours = (time.time() - memory.timestamp) / 3600
        recency_score = max(0, 1 - (age_hours / 168))  # 一周内从1降到0
        
        # 访问频率 (访问越多越重要)
        freq_score = min(1, memory.access_count / 10)  # 10次访问达到满分
        
        # 情绪权重 (从metadata中提取)
        emotional_score = memory.metadata.get('emotional_weight', 0.5)
        
        # 任务相关性
        relevance_score = 0.5
        if memory.tags:
            # 如果有重要标签，提高分数
            important_tags = ['goal', 'decision', 'error', 'milestone']
            if any(t in memory.tags for t in important_tags):
                relevance_score = 0.8
        
        # 加权平均
        score = (
            recency_score * 0.3 +
            freq_score * 0.2 +
            emotional_score * 0.2 +
            relevance_score * 0.3
        )
        
        return min(1.0, max(0.0, score))
    
    def batch_update(self, memories: List[MemoryEntry]):
        """批量更新重要性"""
        for memory in memories:
            memory.importance = self.calculate(memory)


class MemoryConsolidator:
    """
    记忆整合器
    
    将多个零碎记忆合成为总结记忆
    模仿人类大脑的记忆巩固机制
    """
    
    def __init__(self, 
                 llm_summarizer: Optional[Any] = None,
                 min_cluster_size: int = 5):
        self.llm_summarizer = llm_summarizer
        self.min_cluster_size = min_cluster_size
        self.persistence = MemoryPersistence()
        self.event_bus = get_event_bus()
        self.logger = get_logger()
    
    def consolidate(self, time_window_hours: int = 24) -> List[MemoryEntry]:
        """
        整合记忆
        
        流程:
        1. 获取时间窗口内的未整合记忆
        2. 按主题聚类
        3. 对每个聚类生成summary
        4. 存储到semantic memory
        5. 标记原始记忆为已整合
        """
        cutoff = time.time() - (time_window_hours * 3600)
        
        # 获取待整合记忆
        memories = self.persistence.get_unconsolidated_episodic(0)
        memories = [m for m in memories if m.timestamp >= cutoff]
        
        if len(memories) < self.min_cluster_size:
            self.logger.debug(
                f"Not enough memories to consolidate: {len(memories)}/{self.min_cluster_size}",
                component="MemoryConsolidator"
            )
            return []
        
        self.logger.info(
            f"Consolidating {len(memories)} memories",
            component="MemoryConsolidator"
        )
        
        # 按主题聚类 (简单实现: 按时间窗口)
        clusters = self._cluster_by_time(memories, window_hours=2)
        
        consolidated = []
        
        for cluster in clusters:
            if len(cluster) >= self.min_cluster_size:
                # 生成summary
                summary = self._summarize_cluster(cluster)
                
                if summary:
                    # 创建整合记忆
                    memory = MemoryEntry(
                        id=f"consolidated_{int(time.time())}_{len(consolidated)}",
                        content=summary,
                        memory_type=MemoryType.CONSOLIDATED.value,
                        timestamp=time.time(),
                        importance=max(m.importance for m in cluster),
                        tags=['consolidated'] + list(set(
                            tag for m in cluster for tag in m.tags
                        )),
                        consolidated=True,
                        source_memories=[m.id for m in cluster]
                    )
                    
                    # 存储 (这里简化处理，实际应存储到semantic memory)
                    # self.persistence.store_semantic(memory)
                    
                    consolidated.append(memory)
                    
                    # 标记原始记忆为已整合
                    self.persistence.mark_consolidated([m.id for m in cluster])
                    
                    self.logger.info(
                        f"Consolidated {len(cluster)} memories into 1 summary",
                        component="MemoryConsolidator"
                    )
        
        return consolidated
    
    def _cluster_by_time(self, memories: List[MemoryEntry], window_hours: int = 2) -> List[List[MemoryEntry]]:
        """按时间窗口聚类"""
        if not memories:
            return []
        
        # 按时间排序
        sorted_memories = sorted(memories, key=lambda m: m.timestamp)
        
        clusters = []
        current_cluster = [sorted_memories[0]]
        
        for memory in sorted_memories[1:]:
            # 检查时间差
            time_diff = memory.timestamp - current_cluster[-1].timestamp
            
            if time_diff <= window_hours * 3600:
                current_cluster.append(memory)
            else:
                clusters.append(current_cluster)
                current_cluster = [memory]
        
        if current_cluster:
            clusters.append(current_cluster)
        
        return clusters
    
    def _summarize_cluster(self, cluster: List[MemoryEntry]) -> Optional[str]:
        """为聚类生成summary"""
        if not self.llm_summarizer:
            # 简单summary
            topics = list(set(m.metadata.get('topic', 'general') for m in cluster))
            return f"Summary of {len(cluster)} events about: {', '.join(topics)}"
        
        try:
            # 调用LLM生成summary
            contents = [m.content for m in cluster]
            summary = self.llm_summarizer(contents)
            return summary
        except Exception as e:
            self.logger.error(
                f"Failed to summarize cluster: {e}",
                component="MemoryConsolidator"
            )
            return None


class MemoryIndex:
    """
    记忆索引
    
    统一的记忆管理接口
    """
    
    def __init__(self):
        self.persistence = MemoryPersistence()
        self.embedding = SimpleEmbedding(dim=128)
        self.scorer = ImportanceScorer()
        self.consolidator = MemoryConsolidator()
        self.event_bus = get_event_bus()
        self.logger = get_logger()
        
        # 内存中的向量索引 (简化实现)
        self._vector_cache: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        
        # 订阅事件
        self._subscribe_events()
    
    def _subscribe_events(self):
        """订阅记忆相关事件"""
        @listener(EventType.MESSAGE_RECEIVED.value)
        def on_message(event):
            # 自动将消息存储为记忆
            self.store_episodic(
                content=f"Message: {event.data.get('message', '')}",
                metadata={
                    'event_type': 'message',
                    'source': event.data.get('from')
                },
                tags=['message', 'conversation']
            )
        
        @listener(EventType.TASK_FINISHED.value)
        def on_task_finished(event):
            # 存储任务完成记忆
            self.store_episodic(
                content=f"Task finished: {event.data.get('task_id')}",
                metadata={
                    'event_type': 'task_finished',
                    'result': event.data.get('result')
                },
                tags=['task', 'milestone']
            )
    
    def store_episodic(self, content: str, 
                       metadata: Dict = None,
                       tags: List[str] = None,
                       embedding: List[float] = None) -> str:
        """
        存储时间线记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据
            tags: 标签
            embedding: 预计算的向量 (None则自动计算)
        
        Returns:
            memory_id: 记忆ID
        """
        memory_id = hashlib.md5(
            f"{content}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        # 计算向量
        if embedding is None:
            embedding = self.embedding.encode(content)
        
        memory = MemoryEntry(
            id=memory_id,
            content=content,
            memory_type=MemoryType.EPISODIC.value,
            timestamp=time.time(),
            embedding=embedding,
            metadata=metadata or {},
            tags=tags or []
        )
        
        # 计算重要性
        memory.importance = self.scorer.calculate(memory)
        
        # 持久化
        self.persistence.store_episodic(memory)
        
        # 更新内存缓存
        with self._lock:
            self._vector_cache[memory_id] = embedding
        
        # 发布事件
        self.event_bus.publish_simple(
            EventType.MEMORY_UPDATED.value,
            {
                "memory_id": memory_id,
                "type": "episodic",
                "importance": memory.importance
            }
        )
        
        self.logger.debug(
            f"Episodic memory stored: {memory_id}",
            component="MemoryIndex"
        )
        
        return memory_id
    
    def search_similar(self, query: str, top_k: int = 5) -> List[Tuple[MemoryEntry, float]]:
        """
        语义搜索相似记忆
        
        Args:
            query: 查询文本
            top_k: 返回数量
        
        Returns:
            [(memory, score), ...]
        """
        # 编码查询
        query_vec = self.embedding.encode(query)
        
        # 计算相似度 (余弦相似度)
        results = []
        
        with self._lock:
            for memory_id, vec in self._vector_cache.items():
                # 余弦相似度
                dot = sum(a * b for a, b in zip(query_vec, vec))
                score = dot  # 已归一化，无需再除
                
                # 获取完整记忆
                memory = self.persistence.get_episodic(memory_id)
                if memory:
                    results.append((memory, score))
        
        # 排序并返回top_k
        results.sort(key=lambda x: x[1], reverse=True)
        
        # 更新访问统计
        for memory, _ in results[:top_k]:
            memory.update_access()
            self.persistence.store_episodic(memory)
        
        return results[:top_k]
    
    def get_recent(self, hours: int = 24, limit: int = 50) -> List[MemoryEntry]:
        """获取最近记忆"""
        start_time = time.time() - (hours * 3600)
        end_time = time.time()
        
        memories = self.persistence.get_episodic_range(start_time, end_time)
        
        # 按重要性排序
        memories.sort(key=lambda m: m.importance, reverse=True)
        
        return memories[:limit]
    
    def run_consolidation(self):
        """运行记忆整合"""
        consolidated = self.consolidator.consolidate(time_window_hours=24)
        
        if consolidated:
            self.logger.info(
                f"Memory consolidation complete: {len(consolidated)} summaries created",
                component="MemoryIndex"
            )
        
        return consolidated
    
    def cleanup(self):
        """清理低重要性记忆"""
        self.persistence.cleanup_low_importance(threshold=0.2, min_age_days=30)
        self.logger.info("Memory cleanup complete", component="MemoryIndex")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        # 这里简化实现，实际应查询数据库
        return {
            "vector_cache_size": len(self._vector_cache),
            "embedding_dim": self.embedding.dim,
            "vocab_size": len(self.embedding.vocab)
        }


# 全局实例
_memory_index_instance = None


def get_memory_index() -> MemoryIndex:
    """获取全局记忆索引"""
    global _memory_index_instance
    if _memory_index_instance is None:
        _memory_index_instance = MemoryIndex()
    return _memory_index_instance


def set_memory_index(index: MemoryIndex):
    """设置全局记忆索引"""
    global _memory_index_instance
    _memory_index_instance = index