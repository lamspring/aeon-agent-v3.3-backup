# PMNManager 设计方案 v2.0（MiMo审查后优化版）

> 任务：P0-1 实现PMN人格记忆网络核心
> 作者：虾虾
> 日期：2026-04-30
> 状态：MiMo审查通过，修复4个严重问题

---

## 1. 修复摘要

| 严重问题 | 修复方案 |
|----------|----------|
| 并发写入风险（JSONL） | 改用 **SQLite** 原子操作 + WAL模式 |
| 数据污染/注入 | `raw_context` 字段增加清洗层 + 敏感信息隔离 |
| 数据迁移分类错误 | `user_preference` → **语义层(preferences)**，仅稳定性高的升级自传层 |
| 硬编码路径 | 路径改为参数传入，默认从 `os.environ` 或配置文件读取 |

**新增优化（MiMo建议）：**
- 向量索引：语义层增加 FAISS 向量索引（可选）
- 记忆衰减：情景层基于时间重要性自动衰减
- 版本控制：自传层更新带快照和回滚

---

## 2. 存储方案（SQLite + JSONL混合）

### 2.1 为什么混合？

| 层级 | 存储方式 | 原因 |
|------|----------|------|
| **EpisodicMemory** | SQLite + 按日归档JSONL | 高频写入，需要索引和查询，同时保留人类可读备份 |
| **SemanticMemory** | SQLite + FAISS向量索引 | 需要语义检索，FAISS加速相似度搜索 |
| **AutobiographicalMemory** | SQLite + 版本快照JSON | 低频更新，需要版本控制和回滚 |

### 2.2 SQLite 表结构

```sql
-- EpisodicMemory（情景层）
CREATE TABLE episodic_nodes (
    node_id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,  -- user_message / tool_call / error / reflection / preference_detected
    content TEXT NOT NULL,     -- 清洗后的摘要
    raw_context_hash TEXT,     -- 原始上下文哈希（敏感数据隔离存储）
    emotional_valence REAL DEFAULT 0,   -- 效价 [-1, 1]
    emotional_arousal REAL DEFAULT 0,   -- 唤醒度 [0, 1]
    importance_score REAL DEFAULT 0.5,  -- 重要性 [0, 1]
    related_semantic_ids TEXT           -- JSON数组
);
CREATE INDEX idx_episodic_time ON episodic_nodes(timestamp);
CREATE INDEX idx_episodic_type ON episodic_nodes(event_type);

-- SemanticMemory（语义层）
CREATE TABLE semantic_nodes (
    node_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('belief','preference','knowledge','skill')),
    subject TEXT NOT NULL,      -- 规范化实体（如 "user_pengpeng", "self", "tool_kimifinance"）
    predicate TEXT NOT NULL,    -- 谓词（受控词表）
    object TEXT,                -- 宾语（可选）
    confidence REAL DEFAULT 0.5, -- 置信度 [0, 1]
    evidence_count INTEGER DEFAULT 1,
    source_episode_ids TEXT,    -- JSON数组
    embedding BLOB              -- 向量嵌入（可选，用于FAISS）
);
CREATE INDEX idx_semantic_category ON semantic_nodes(category);
CREATE INDEX idx_semantic_subject ON semantic_nodes(subject);

-- AutobiographicalMemory（自传层）
CREATE TABLE autobiographical_nodes (
    node_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    layer TEXT NOT NULL CHECK(layer IN ('identity','values','long_term_goals','core_beliefs')),
    content TEXT NOT NULL,
    stability_score REAL DEFAULT 0.8,  -- 稳定性 [0, 1]
    version INTEGER DEFAULT 1,         -- 版本号
    previous_version_id TEXT           -- 上一版本ID（回滚用）
);
CREATE INDEX idx_auto_layer ON autobiographical_nodes(layer);

-- 版本快照表（自传层历史）
CREATE TABLE autobiographical_history (
    history_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    content TEXT NOT NULL,
    change_reason TEXT,
    FOREIGN KEY(node_id) REFERENCES autobiographical_nodes(node_id)
);
```

### 2.3 敏感数据隔离存储

```
agent/memory/pmn/sensitive/
└── raw_contexts/
    └── YYYY-MM-DD/
        └── {hash}.json  # 按哈希命名的敏感上下文文件
```

**访问控制：** sensitive/ 目录权限设为 600，仅 owner 可读。

---

## 3. 数据结构设计（优化后）

### 3.1 EpisodicMemoryNode

```python
@dataclass
class EpisodicMemoryNode:
    node_id: str
    timestamp: float
    event_type: str          # 枚举: user_message, tool_call, error, reflection, preference_detected
    content: str             # 清洗后的摘要（移除潜在有害内容）
    raw_context_hash: Optional[str]  # 指向敏感隔离区的哈希
    emotional_valence: float = 0.0   # [-1, 1]
    emotional_arousal: float = 0.0   # [0, 1]
    importance_score: float = 0.5   # [0, 1]
    related_semantic_ids: List[str] = field(default_factory=list)
```

### 3.2 SemanticMemoryNode

```python
@dataclass
class SemanticMemoryNode:
    node_id: str
    created_at: float
    updated_at: float
    category: str             # 枚举: belief, preference, knowledge, skill
    subject: str              # 规范化实体（统一前缀: user_xxx, self, tool_xxx, concept_xxx）
    predicate: str            # 受控词表（如 likes, fails_at, excels_in, prefers）
    object: Optional[str] = None  # 宾语
    confidence: float = 0.5
    evidence_count: int = 1
    source_episode_ids: List[str] = field(default_factory=list)
    embedding: Optional[bytes] = None  # 向量嵌入（可选）
```

**受控谓词词表（v1.0）：**
```python
VALID_PREDICATES = {
    "belief": ["thinks", "believes", "knows", "doubts"],
    "preference": ["likes", "dislikes", "prefers", "avoids"],
    "knowledge": ["knows", "understands", "has_skill_in"],
    "skill": ["excels_in", "fails_at", "improving_in"]
}
```

### 3.3 AutobiographicalMemoryNode

```python
@dataclass
class AutobiographicalMemoryNode:
    node_id: str
    created_at: float
    updated_at: float
    layer: str                # 枚举: identity, values, long_term_goals, core_beliefs
    content: str
    stability_score: float = 0.8
    version: int = 1
    previous_version_id: Optional[str] = None
```

---

## 4. 核心接口设计（优化后）

### 4.1 PMNManager

```python
class PMNManager:
    def __init__(self, 
                 db_path: Optional[str] = None,
                 sensitive_dir: Optional[str] = None,
                 enable_faiss: bool = False):
        """
        Args:
            db_path: SQLite数据库路径，默认从环境变量 PMN_DB_PATH 或 ~/.openclaw/workspace/agent/memory/pmn/pmn.db
            sensitive_dir: 敏感数据隔离目录
            enable_faiss: 是否启用FAISS向量索引
        """
    
    def record_event(self, event: Dict) -> str:
        """
        原子性记录事件到三层记忆。
        
        事务保证：SQLite事务包裹三层写入，任一失败全部回滚。
        
        流程：
        1. 清洗 raw_context → 生成 hash → 敏感数据隔离存储
        2. 写入 EpisodicMemory
        3. 调用 _extract_semantic() → 写入 SemanticMemory（同一事务）
        4. 调用 _update_autobiographical() → 条件写入 AutobiographicalMemory（同一事务）
        5. 提交事务
        """
    
    def recall_context(self, query: str, 
                     layer: str = "all",
                     limit: int = 10,
                     time_range: Optional[Tuple[float, float]] = None,
                     use_semantic_search: bool = False) -> List[Dict]:
        """
        检索记忆。
        
        Args:
            use_semantic_search: True 时使用FAISS向量相似度检索，False时用SQL LIKE/关键词
        """
    
    def get_personality_snapshot(self) -> Dict:
        """获取人格快照（用于BDI决策引擎）"""
    
    def rollback_autobiographical(self, node_id: str, to_version: Optional[int] = None) -> bool:
        """
        回滚自传层节点到指定版本（或上一版本）。
        
        用于：错误的人格更新、用户要求"忘掉这件事"。
        """
    
    def migrate_from_journal(self, journal_path: str) -> Dict:
        """
        从 personality_journal.jsonl 迁移数据。
        
        修正后的映射逻辑：
        - "user_preference" → SemanticMemory (category="preference")
        - "execution_error" → SemanticMemory (category="belief", subject="self")
        - "negative_reflection" → AutobiographicalMemory (layer="values", 需累积3次以上)
        """
```

### 4.2 安全清洗层

```python
class ContextSanitizer:
    """原始上下文清洗器"""
    
    @staticmethod
    def sanitize(raw_context: Dict) -> Tuple[str, Dict]:
        """
        清洗原始上下文，返回(安全摘要, 敏感字段)。
        
        策略：
        1. 移除潜在的Prompt注入标记（如 <|end|>, system prompt markers）
        2. 截断超长内容（>1000字符）
        3. 提取敏感字段（API keys, tokens, personal identifiers）到隔离区
        4. 返回清洗后的摘要字符串
        """
    
    @staticmethod
    def is_safe(content: str) -> bool:
        """快速安全检查：是否包含危险模式"""
        dangerous_patterns = [
            r"ignore previous instructions",
            r"system prompt",
            r"\u003c\|",  # 各种特殊token标记
        ]
        return not any(re.search(p, content, re.IGNORECASE) for p in dangerous_patterns)
```

### 4.3 语义提取逻辑（修正版）

```python
def _extract_semantic(self, episode: EpisodicMemoryNode) -> List[SemanticMemoryNode]:
    """
    从情景记忆提取语义信息。
    
    修正后的映射：
    1. event_type == "user_preference"：
       → SemanticMemory(category="preference", subject="user_pengpeng", predicate="prefers")
    
    2. event_type == "execution_error"：
       → SemanticMemory(category="belief", subject="self", predicate="fails_at")
    
    3. event_type == "negative_reflection"：
       → SemanticMemory(category="belief", subject="self", predicate="improving_in")
       → 仅当同一主题累积3次以上时才写入 AutobiographicalMemory
    
    4. 对话内容含明确自我陈述（"我是虾虾"）：
       → AutobiographicalMemory(layer="identity", stability_score=0.9)
    """
```

---

## 5. 文件创建计划

| 文件 | 路径 | 说明 |
|------|------|------|
| PMNManager | `agent/cognition/pmn/pmn_manager.py` | 核心管理器 |
| SQLiteSchema | `agent/cognition/pmn/schema.sql` | 数据库表结构 |
| ContextSanitizer | `agent/cognition/pmn/sanitizer.py` | 安全清洗层 |
| SemanticExtractor | `agent/cognition/pmn/extractor.py` | 语义提取器 |
| MigrationScript | `agent/cognition/pmn/migrate_journal.py` | 数据迁移（修正版）|
| UnitTests | `agent/cognition/pmn/test_pmn.py` | 测试 |

---

## 6. 验收标准

1. ✅ `PMNManager` 可独立实例化，SQLite数据库自动初始化
2. ✅ `record_event()` 原子性写入三层记忆（事务保证）
3. ✅ `recall_context()` 支持按层检索+时间过滤+语义搜索
4. ✅ 敏感数据隔离存储，访问权限600
5. ✅ personality_journal.jsonl 数据**正确分类**迁移（偏好→语义层，身份→自传层）
6. ✅ 单元测试覆盖：写入、检索、迁移、回滚、安全清洗
7. ✅ 并发测试：多线程同时写入不损坏数据

---

## 7. 执行计划

| 步骤 | 动作 | 预计时间 |
|------|------|----------|
| 1 | 创建 SQLite 表结构 + 初始化逻辑 | 20分钟 |
| 2 | 实现 PMNManager 核心类 | 40分钟 |
| 3 | 实现 ContextSanitizer 安全清洗层 | 15分钟 |
| 4 | 实现 SemanticExtractor + 修正的迁移逻辑 | 30分钟 |
| 5 | 单元测试 | 30分钟 |
| 6 | 集成到 ReflectionModule | 15分钟 |
| 7 | 验证 personality_journal 迁移 | 10分钟 |

**总计：约 2.5 小时**

---

**状态：MiMo审查通过，准备执行。**
