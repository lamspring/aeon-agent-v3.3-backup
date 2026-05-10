# PMNManager 设计方案 v1.0

> 任务：P0-1 实现PMN人格记忆网络核心
> 作者：虾虾
> 日期：2026-04-30

---

## 1. 总体架构

```
PMNManager
├── EpisodicMemory（情景层）— 具体交互事件的原始记录
├── SemanticMemory（语义层）— 从事件中抽象出的信念、知识、偏好
└── AutobiographicalMemory（自传层）— 关于"我"的身份、价值观、长期目标
```

---

## 2. 数据结构设计

### 2.1 EpisodicMemoryNode（情景记忆节点）

```python
@dataclass
class EpisodicMemoryNode:
    node_id: str           # UUID
    timestamp: float       # 事件发生时间
    event_type: str        # "user_message" / "tool_call" / "error" / "reflection"
    content: str           # 事件内容摘要（用户说了什么/做了什么）
    raw_context: Dict      # 完整上下文（用户ID、频道、消息原文等）
    emotional_tags: Dict  # 情感标签 {"valence": 0.5, "arousal": 0.3}  # 效价/唤醒度
    importance_score: float # 重要性评分（0-1，基于关键词/重复提及/情感强度）
    related_semantic_ids: List[str]  # 关联的语义记忆节点ID
```

### 2.2 SemanticMemoryNode（语义记忆节点）

```python
@dataclass
class SemanticMemoryNode:
    node_id: str
    created_at: float
    updated_at: float
    category: str           # "belief" / "preference" / "knowledge" / "skill"
    subject: str            # 主题（如 "用户A", "股票工具", "Python"）
    predicate: str          # 谓词（如 "喜欢简洁回答", "容易出错", "擅长"）
    confidence: float       # 置信度（0-1，基于证据数量）
    evidence_count: int     # 支持这个信念的证据数量
    source_episode_ids: List[str]  # 来源情景记忆节点ID
```

### 2.3 AutobiographicalMemoryNode（自传记忆节点）

```python
@dataclass
class AutobiographicalMemoryNode:
    node_id: str
    created_at: float
    updated_at: float
    layer: str              # "identity" / "values" / "long_term_goals" / "core_beliefs"
    content: str            # 内容（如 "我是虾虾，朋朋的伙伴"）
    stability_score: float  # 稳定性评分（0-1，越高越难被改变）
    evolution_history: List[Dict]  # 演化历史 [{"timestamp": ..., "old": ..., "new": ..., "trigger": ...}]
```

---

## 3. 存储方案

### 3.1 文件布局

```
agent/memory/pmn/
├── episodic/
│   ├── 2026-04-30.jsonl     # 按日分割的情景记忆
│   └── ...
├── semantic/
│   ├── beliefs.jsonl        # 信念节点
│   ├── preferences.jsonl    # 偏好节点
│   ├── knowledge.jsonl      # 知识节点
│   └── skills.jsonl         # 技能节点
└── autobiographical/
    ├── identity.jsonl        # 身份定义
    ├── values.jsonl          # 价值观
    ├── goals.jsonl           # 长期目标
    └── core_beliefs.jsonl    # 核心信念
```

### 3.2 数据迁移（personality_journal.jsonl → AutobiographicalMemory）

```python
# 迁移逻辑：
# 1. 读取 personality_journal.jsonl 中的所有条目
# 2. 根据 event_type 映射到 autobiographical 对应层
#    - "user_preference" → preferences.jsonl（实际是语义层，但初始数据量少，先放自传层）
#    - "execution_error" → core_beliefs.jsonl（"我有时会犯错"）
#    - "negative_reflection" → values.jsonl（"我应该更谨慎"）
# 3. 为每条数据生成 AutobiographicalMemoryNode
```

---

## 4. 核心接口设计

### 4.1 PMNManager 类

```python
class PMNManager:
    def __init__(self, base_dir: str = "/root/.openclaw/workspace/agent/memory/pmn"):
        self.base_dir = Path(base_dir)
        self.episodic = EpisodicMemoryStore(self.base_dir / "episodic")
        self.semantic = SemanticMemoryStore(self.base_dir / "semantic")
        self.autobiographical = AutobiographicalMemoryStore(self.base_dir / "autobiographical")
    
    def record_event(self, event: Dict) -> str:
        """
        记录一次交互事件，自动写入三层记忆。
        
        流程：
        1. 写入 EpisodicMemory（原始记录）
        2. 调用 _extract_semantic() 提取语义信息，写入 SemanticMemory
        3. 调用 _update_autobiographical() 更新自传层（如果有身份级影响）
        4. 返回 episodic_node_id
        """
    
    def recall_context(self, query: str, layer: str = "all", 
                     limit: int = 10, time_range: Optional[Tuple[float, float]] = None) -> List[Dict]:
        """
        从指定层检索相关记忆。
        
        Args:
            query: 查询文本
            layer: "episodic" / "semantic" / "autobiographical" / "all"
            limit: 返回数量上限
            time_range: (start, end) 时间过滤
        """
    
    def get_personality_snapshot(self) -> Dict:
        """
        获取当前人格快照（用于 BDI 决策引擎）。
        
        Returns:
            {
                "beliefs": [...],      # 高置信度信念
                "preferences": [...],    # 用户偏好
                "identity": [...],      # 自传层身份定义
                "values": [...],        # 核心价值观
                "recent_episodes": [...] # 最近情景记忆
            }
        """
    
    def migrate_from_journal(self, journal_path: str) -> int:
        """
        从 personality_journal.jsonl 迁移数据到 AutobiographicalMemory。
        
        Returns:
            迁移的条目数量
        """
```

### 4.2 语义提取逻辑（_extract_semantic）

```python
def _extract_semantic(self, episode: EpisodicMemoryNode) -> List[SemanticMemoryNode]:
    """
    从情景记忆提取语义信息。
    
    简化版规则（v1.0）：
    1. 如果 event_type == "user_preference"：
       - 生成 preference 节点：subject="用户", predicate=提取的偏好内容
    
    2. 如果 event_type == "execution_error"：
       - 生成 belief 节点：subject="self", predicate="容易在{工具名}上出错"
    
    3. 如果 event_type == "negative_reflection"：
       - 生成 belief 节点：subject="self", predicate="需要改进{方面}"
    
    4. 如果对话内容包含明确陈述（如"我是程序员"）：
       - 生成 knowledge 节点：subject=主语, predicate=陈述内容
    """
```

### 4.3 自传层更新逻辑（_update_autobiographical）

```python
def _update_autobiographical(self, episode: EpisodicMemoryNode, 
                              semantic_nodes: List[SemanticMemoryNode]) -> None:
    """
    更新自传层。
    
    触发条件（v1.0 简化）：
    1. 同一主题的信念累积超过阈值（confidence > 0.7）→ 升级为 core_belief
    2. 用户明确表达对我的认知（如"虾虾你真聪明"）→ 写入 identity
    3. 错误事件累积超过3次 → 写入 values（"谨慎"）
    """
```

---

## 5. 与现有系统集成

### 5.1 接入点

| 现有模块 | 接入方式 | 触发时机 |
|----------|----------|----------|
| ReflectionModule | 调用 `pmnm.record_event()` | 每次反思时 |
| PlanningModule | 调用 `pmnm.recall_context("相关查询")` | 生成计划前（获取人格上下文） |
| OrchestratorModule | 调用 `pmnm.get_personality_snapshot()` | 每次 tick 开始时（注入人格状态） |
| DialogueLogger | 调用 `pmnm.record_event()` | 记录用户对话时 |

### 5.2 BDI 集成预览（P0-2）

```python
# PlanningModule.plan() 中的 BDI 选择器
def bdi_select(self, candidate_plans: List[Plan], 
               beliefs: List[Belief], desires: List[Desire],
               personality_snapshot: Dict) -> Plan:
    """
    根据人格快照选择最佳计划。
    
    示例：如果 personality_snapshot["preferences"] 中有 "用户喜欢简洁回答"，
    则优先选择 steps 较少的 plan。
    """
```

---

## 6. 文件创建计划

| 文件 | 路径 | 说明 |
|------|------|------|
| PMNManager | `agent/cognition/pmn_manager.py` | 核心管理器 |
| EpisodicMemoryStore | `agent/cognition/pmn/episodic_store.py` | 情景层存储 |
| SemanticMemoryStore | `agent/cognition/pmn/semantic_store.py` | 语义层存储 |
| AutobiographicalMemoryStore | `agent/cognition/pmn/autobiographical_store.py` | 自传层存储 |
| 数据迁移脚本 | `agent/cognition/pmn/migrate_journal.py` | 从 journal 迁移 |
| 单元测试 | `agent/cognition/pmn/test_pmn.py` | 测试 |

---

## 7. 潜在风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 数据文件膨胀 | 高 | 性能下降 | 按日分割 + 定期归档旧数据 |
| 语义提取不准确 | 中 | 人格偏差 | 低置信度标记 + 人工复核机制 |
| 自传层过度更新 | 中 | 人格不稳定 | 稳定性评分阈值 + 平滑滤波 |
| 与现有系统耦合过紧 | 低 | 升级困难 | 通过 EventBus 通信，松耦合设计 |
| 数据迁移丢失 | 低 | 历史数据缺失 | 迁移前备份 + 迁移后验证 |

---

## 8. 验收标准

1. `PMNManager` 可独立实例化，并能正确初始化三层存储
2. 提供 `record_event(event)` 接口，能将一次交互自动分解并写入三层记忆
3. 提供 `recall_context(query, layer)` 接口，能从指定层检索相关记忆
4. 单元测试覆盖三层写入与检索逻辑
5. personality_journal.jsonl 数据成功迁移到 AutobiographicalMemory

---

**下一步：提交 MiMo 审查，寻找潜在 bug 和优化点。**
