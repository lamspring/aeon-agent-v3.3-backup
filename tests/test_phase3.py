"""
Phase 3 测试 - Memory Index + Vector Search + Memory Consolidation
"""

import sys
import time
import os
import tempfile

sys.path.insert(0, '/root/.openclaw/workspace/agent')

from memory.memory_index import (
    MemoryIndex, MemoryEntry, MemoryType, 
    SimpleEmbedding, ImportanceScorer, MemoryConsolidator
)
from memory.memory_buffer import MemoryWriteBuffer, get_memory_buffer


def test_simple_embedding():
    """测试简单嵌入模型"""
    print("\n=== 测试 SimpleEmbedding ===")
    
    embed = SimpleEmbedding(dim=64)
    
    # 编码文本
    vec1 = embed.encode("这是一个测试")
    vec2 = embed.encode("这是另一个测试")
    vec3 = embed.encode("完全无关的内容")
    
    assert len(vec1) == 64
    print(f"  ✅ 向量维度正确: {len(vec1)}")
    
    # 计算相似度
    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        return dot
    
    sim_1_2 = cosine_similarity(vec1, vec2)
    sim_1_3 = cosine_similarity(vec1, vec3)
    
    print(f"  相似文本相似度: {sim_1_2:.3f}")
    print(f"  不相似文本相似度: {sim_1_3:.3f}")
    
    assert sim_1_2 > sim_1_3, "相似文本应该有更高的相似度"
    print(f"  ✅ 语义相似度计算正确")


def test_memory_entry():
    """测试记忆条目"""
    print("\n=== 测试 MemoryEntry ===")
    
    memory = MemoryEntry(
        id="test_001",
        content="测试记忆内容",
        memory_type=MemoryType.EPISODIC.value,
        timestamp=time.time(),
        importance=0.8,
        tags=["test", "memory"],
        metadata={"source": "test"}
    )
    
    assert memory.id == "test_001"
    assert memory.content == "测试记忆内容"
    assert memory.importance == 0.8
    
    # 测试访问更新
    assert memory.access_count == 0
    memory.update_access()
    assert memory.access_count == 1
    assert memory.last_accessed is not None
    
    print(f"  ✅ MemoryEntry 工作正常")


def test_importance_scorer():
    """测试重要性评分"""
    print("\n=== 测试 ImportanceScorer ===")
    
    scorer = ImportanceScorer()
    
    # 新记忆 (高时效性)
    new_memory = MemoryEntry(
        id="new",
        content="刚刚发生的事情",
        memory_type=MemoryType.EPISODIC.value,
        timestamp=time.time(),  # 现在
        access_count=0,
        tags=[]
    )
    
    # 旧记忆 (低时效性)
    old_memory = MemoryEntry(
        id="old",
        content="很久以前的事情",
        memory_type=MemoryType.EPISODIC.value,
        timestamp=time.time() - 7 * 24 * 3600,  # 7天前
        access_count=10,
        tags=[]
    )
    
    # 重要记忆 (有重要标签)
    important_memory = MemoryEntry(
        id="important",
        content="重要决策",
        memory_type=MemoryType.EPISODIC.value,
        timestamp=time.time(),
        access_count=0,
        tags=["decision", "milestone"]
    )
    
    new_score = scorer.calculate(new_memory)
    old_score = scorer.calculate(old_memory)
    important_score = scorer.calculate(important_memory)
    
    print(f"  新记忆重要性: {new_score:.3f}")
    print(f"  旧记忆重要性: {old_score:.3f}")
    print(f"  重要记忆重要性: {important_score:.3f}")
    
    assert important_score > old_score, "重要标签应该提高分数"
    print(f"  ✅ 重要性评分逻辑正确")


def test_memory_index_store_and_search():
    """测试记忆存储和搜索"""
    print("\n=== 测试 Memory Index 存储和搜索 ===")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # 创建记忆索引
        index = MemoryIndex()
        index.persistence.db_path = db_path
        index.persistence._init_db()
        
        # 存储一些记忆
        id1 = index.store_episodic(
            content="用户询问天气情况",
            metadata={"type": "question", "topic": "weather"},
            tags=["weather", "question"]
        )
        
        id2 = index.store_episodic(
            content="用户询问股票价格",
            metadata={"type": "question", "topic": "stock"},
            tags=["stock", "question"]
        )
        
        id3 = index.store_episodic(
            content="今天天气真好",
            metadata={"type": "statement", "topic": "weather"},
            tags=["weather"]
        )
        
        print(f"  ✅ 存储了3条记忆")
        
        # 搜索相似记忆
        results = index.search_similar("天气怎么样", top_k=2)
        
        assert len(results) > 0, "应该找到相似记忆"
        print(f"  ✅ 找到 {len(results)} 条相似记忆")
        
        for memory, score in results:
            print(f"    - {memory.content[:20]}... (相似度: {score:.3f})")
        
        # 验证最相关的是天气相关的
        top_result = results[0][0]
        assert "天气" in top_result.content or "weather" in top_result.tags
        
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_memory_consolidation():
    """测试记忆整合"""
    print("\n=== 测试 Memory Consolidation ===")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        consolidator = MemoryConsolidator(min_cluster_size=3)
        consolidator.persistence.db_path = db_path
        consolidator.persistence._init_db()
        
        # 创建一批记忆 (模拟一段时间内的对话)
        now = time.time()
        base_time = now - 3600  # 1小时前
        
        for i in range(5):
            memory = MemoryEntry(
                id=f"conv_{i}",
                content=f"对话内容 {i}: 讨论项目进展",
                memory_type=MemoryType.EPISODIC.value,
                timestamp=base_time + i * 300,  # 每5分钟一条
                importance=0.6,
                tags=["conversation", "project"],
                metadata={"topic": "project"}
            )
            consolidator.persistence.store_episodic(memory)
        
        print(f"  ✅ 创建了5条待整合记忆")
        
        # 运行整合
        consolidated = consolidator.consolidate(time_window_hours=24)
        
        print(f"  ✅ 整合完成: 生成了 {len(consolidated)} 条总结记忆")
        
        for mem in consolidated:
            print(f"    - 整合了 {len(mem.source_memories)} 条记忆")
        
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_memory_write_buffer():
    """测试记忆写入缓冲区"""
    print("\n=== 测试 Memory Write Buffer ===")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    try:
        # 创建记忆索引和缓冲区
        index = MemoryIndex()
        index.persistence.db_path = db_path
        index.persistence._init_db()
        
        buffer = MemoryWriteBuffer(
            memory_index=index,
            flush_interval=2,  # 2秒自动刷新
            max_batch_size=3   # 3条批量写入
        )
        
        # 添加记忆 (不触发批量)
        buffer.add("记忆1", {"type": "test"}, ["tag1"])
        buffer.add("记忆2", {"type": "test"}, ["tag2"])
        
        stats = buffer.get_stats()
        print(f"  缓冲区大小: {stats['buffer_size']}")
        assert stats['buffer_size'] == 2
        
        # 添加第3条，触发批量写入
        flushed = buffer.add("记忆3", {"type": "test"}, ["tag3"])
        assert flushed, "应该触发刷新"
        
        time.sleep(0.2)  # 等待写入完成
        
        stats = buffer.get_stats()
        print(f"  刷新后缓冲区大小: {stats['buffer_size']}")
        assert stats['buffer_size'] == 0
        
        print(f"  ✅ 批量写入工作正常")
        
        # 测试强制刷新
        buffer.add("记忆4", {"type": "test"}, ["tag4"])
        buffer.force_flush()
        
        stats = buffer.get_stats()
        assert stats['buffer_size'] == 0
        print(f"  ✅ 强制刷新工作正常")
        
        buffer.stop()
        
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def test_memory_stats():
    """测试记忆统计"""
    print("\n=== 测试 Memory Stats ===")
    
    index = MemoryIndex()
    
    # 存储一些记忆
    for i in range(5):
        index.store_episodic(
            content=f"测试记忆 {i}",
            tags=["test"]
        )
    
    stats = index.get_stats()
    
    print(f"  向量缓存大小: {stats['vector_cache_size']}")
    print(f"  向量维度: {stats['embedding_dim']}")
    print(f"  词汇表大小: {stats['vocab_size']}")
    
    assert stats['vector_cache_size'] >= 5
    assert stats['embedding_dim'] == 128
    
    print(f"  ✅ 统计信息正确")


def run_all_tests():
    """运行所有测试"""
    print("=" * 50)
    print("Phase 3 测试开始")
    print("=" * 50)
    
    tests = [
        test_simple_embedding,
        test_memory_entry,
        test_importance_scorer,
        test_memory_index_store_and_search,
        test_memory_consolidation,
        test_memory_write_buffer,
        test_memory_stats,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {test.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)