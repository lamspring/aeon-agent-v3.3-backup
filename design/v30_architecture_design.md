# v30 架构升级设计文档
**代号**: Aeon (永恒)
**日期**: 2026-04-06
**状态**: 设计阶段

---

## 1. 升级概述

### 1.1 当前架构问题
- **紧耦合**: timer直接驱动所有逻辑
- **低响应性**: 只能被动等待定时触发
- **记忆瓶颈**: 线性文本文件无法高效检索
- **认知混杂**: 系统任务与认知循环混在一起

### 1.2 目标架构
构建**真正的AI操作系统**：
- 事件驱动响应 (Event-Driven)
- 分离认知循环 (Cognitive Loop)
- 向量记忆索引 (Vector Memory)

---

## 2. 模块设计

### 模块1: Event Bus (事件总线)

#### 核心概念
```
传统: Timer → Runner → Queue → Action
         ↓
事件驱动: Event Bus ← Publisher
              ↓
         Listener → Handler → Action
```

#### 事件类型
```python
class EventTypes:
    # 记忆事件
    MEMORY_UPDATED = "memory.updated"
    MEMORY_ACCESSED = "memory.accessed"
    
    # 任务事件
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_FINISHED = "task.finished"
    TASK_FAILED = "task.failed"
    
    # 消息事件
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_SENT = "message.sent"
    
    # 状态事件
    STATE_CHANGED = "state.changed"
    GATE_OPENED = "gate.opened"
    GATE_CLOSED = "gate.closed"
    
    # 系统事件
    SYSTEM_STARTED = "system.started"
    SYSTEM_SHUTDOWN = "system.shutdown"
    HEARTBEAT = "system.heartbeat"
```

#### 架构图
```
┌─────────────────────────────────────────────┐
│              Event Bus (Redis/ZeroMQ)        │
└────────────┬────────────────────────────────┘
             │
    ┌────────┼────────┬───────────┐
    ↓        ↓        ↓           ↓
┌──────┐ ┌──────┐ ┌──────┐  ┌──────────┐
│Memory│ │ Task │ │Cog.  │  │ System   │
│Listener│Listener│Listener│  │ Listener │
└──┬───┘ └──┬───┘ └──┬───┘  └────┬─────┘
   │        │        │            │
   ↓        ↓        ↓            ↓
Update   Execute  Think      Log/Monitor
Index    Task     Plan
```

#### 核心组件
1. **EventBus**: 事件总线核心
2. **Publisher**: 事件发布器
3. **Listener**: 事件监听器
4. **Handler**: 事件处理器

---

### 模块2: Cognitive Tick (认知时钟)

#### 核心概念
分离**系统维护**和**认知思考**：
- **System Timer**: 维护健康、备份、清理 (60s)
- **Cognitive Tick**: 思考、规划、学习 (30s)

#### 认知循环 (OODA Loop)
```
┌─────────────────────────────────────┐
│        Cognitive Loop (30s)         │
├─────────────────────────────────────┤
│                                     │
│   ┌─────────┐    ┌─────────┐       │
│   │ Observe │───→│  Plan   │       │
│   └────┬────┘    └────┬────┘       │
│        ↑              │            │
│        │              ↓            │
│   ┌────┴────┐    ┌─────────┐       │
│   │ Reflect │←───│   Act   │       │
│   └─────────┘    └─────────┘       │
│                                     │
└─────────────────────────────────────┘
```

#### Observe (观察)
- 读取环境状态
- 检查新事件
- 评估当前上下文
- 输出: Observation

#### Plan (规划)
- 基于观察生成意图
- 优先级排序
- 资源评估
- 输出: Plan / Goal

#### Act (执行)
- 执行计划的一步
- 记录动作
- 触发事件
- 输出: Action Result

#### Reflect (反思)
- 评估执行结果
- 学习经验
- 更新记忆
- 输出: Reflection

#### 代码结构
```
agent/cognition/
├── __init__.py
├── loop.py           # 主认知循环
├── observe.py        # 观察模块
├── plan.py           # 规划模块
├── act.py            # 执行模块
├── reflect.py        # 反思模块
└── state.py          # 认知状态管理
```

---

### 模块3: Memory Index (记忆索引)

#### 核心概念
从**人类式线性记忆**转向**AI式向量记忆**：

```
传统: LONG_TERM_MEMORY.md
      ↓
      线性搜索 (O(n))
      ↓
      越来越慢，越来越乱

向量: memory_index/
      ├── embeddings.db (SQLite + vectors)
      ├── metadata.db   (结构化元数据)
      └── index.faiss   (快速检索索引)
      ↓
      语义搜索 (O(log n))
      ↓
      快速、精准、可扩展
```

#### 记忆类型
```python
class MemoryTypes:
    EPISODIC = "episodic"      # 事件记忆 (今天发生了什么)
    SEMANTIC = "semantic"      # 知识记忆 (Python怎么写)
    PROCEDURAL = "procedural"  # 程序记忆 (怎么做某事)
    WORKING = "working"        # 工作记忆 (当前上下文)
```

#### 数据结构
```python
class Memory:
    id: str
    type: MemoryType
    content: str
    embedding: Vector[768]
    timestamp: datetime
    importance: float  # 0-1
    access_count: int
    last_accessed: datetime
    tags: List[str]
    source: str  # 从哪来
    associations: List[str]  # 关联记忆ID
```

#### 检索方式
1. **语义搜索**: `find_similar("我昨天在做什么")`
2. **时间搜索**: `find_by_time("last_24h")`
3. **标签搜索**: `find_by_tags(["学习", "Python"])`
4. **混合搜索**: 语义 + 时间 + 重要性加权

#### 记忆形成流程
```
Raw Input
    ↓
Chunk → Embed → Store
    ↓
Index in FAISS
    ↓
Link to related memories
    ↓
Update access patterns
```

---

## 3. 整体架构图

```
┌────────────────────────────────────────────────────────────────┐
│                        v30 - Aeon                              │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────┐  │
│  │   Event Bus │◄────│  Publisher  │     │   Event Store   │  │
│  │   (Redis)   │     │             │     │   (持久化)       │  │
│  └──────┬──────┘     └─────────────┘     └─────────────────┘  │
│         │                                                      │
│    ┌────┴────┬──────────┬────────────┬─────────────┐          │
│    ↓         ↓          ↓            ↓             ↓          │
│ ┌──────┐  ┌──────┐  ┌────────┐  ┌────────┐  ┌──────────┐     │
│ │Memory│  │ Task │  │Cognition│  │System  │  │  Gate    │     │
│ │Listener│ │Listener│ │Listener│  │Listener│  │Listener  │     │
│ └──┬───┘  └──┬───┘  └───┬────┘  └───┬────┘  └────┬─────┘     │
│    │         │          │           │             │           │
│    ↓         ↓          ↓           ↓             ↓           │
│ ┌──────┐  ┌──────┐  ┌────────┐  ┌────────┐  ┌──────────┐     │
│ │Vector│  │ Queue│  │  OODA  │  │ Health │  │  Safety  │     │
│ │ Index│  │ Worker│ │  Loop  │  │ Monitor│  │  Check   │     │
│ └──────┘  └──────┘  └────────┘  └────────┘  └──────────┘     │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    Memory System                         │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │  │
│  │  │ Episodic    │  │  Semantic   │  │   Procedural    │  │  │
│  │  │ (事件)      │  │  (知识)     │  │   (技能)        │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. 迁移计划

### Phase 1: Event Bus 基础设施 (1-2天)
- [ ] 创建 event_bus.py 核心模块
- [ ] 实现 Publisher / Listener 基类
- [ ] 迁移现有 timer 为 event 驱动
- [ ] 测试事件流转

### Phase 2: Cognitive Loop 分离 (1-2天)
- [ ] 创建 cognition/ 目录结构
- [ ] 实现 OODA 四个模块
- [ ] 分离 system timer 和 cognitive tick
- [ ] 测试认知循环

### Phase 3: Memory Index (2-3天)
- [ ] 选择向量数据库 (Chroma/FAISS)
- [ ] 创建 memory_index.py
- [ ] 迁移现有记忆到向量格式
- [ ] 实现语义检索
- [ ] 测试记忆系统

### Phase 4: 集成测试 (1-2天)
- [ ] 全系统联调
- [ ] 压力测试
- [ ] 性能优化
- [ ] 文档更新

---

## 5. 技术选型

### Event Bus
- **候选**: Redis Pub/Sub, ZeroMQ, 或纯Python (无外部依赖)
- **建议**: 先用纯Python实现，必要时升级为Redis

### Vector DB
- **候选**: Chroma, FAISS, Pinecone
- **建议**: Chroma (轻量，本地，无外部服务依赖)

### Embedding Model
- **候选**: sentence-transformers, OpenAI API
- **建议**: sentence-transformers (all-MiniLM-L6-v2，本地运行)

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 向量库依赖大 | 部署复杂 | 使用轻量级的Chroma |
| 事件丢失 | 状态不一致 | 添加Event Store持久化 |
| 认知循环过频 | CPU过高 | 可调间隔，动态频率 |
| 记忆迁移失败 | 数据丢失 | 保留原文本备份 |

---

## 7. 批准状态

- [ ] 设计文档审查
- [ ] 朋朋批准
- [ ] 开始 Phase 1

---

**附注**: 这是一个重大架构升级，将虾虾从"定时任务执行器"升级为"真正的AI操作系统"。
