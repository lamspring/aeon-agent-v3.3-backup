# Aeon Agent v3.1 Architecture - Goal & Attention Extension

## 版本信息

| 属性 | 值 |
|------|-----|
| **Version** | v3.1 |
| **Base Version** | v3.0 |
| **Date** | 2026-04-06 |
| **Status** | Design Phase |
| **Priority** | Goal (P0) > Attention (P1) |

---

## 概述

本设计文档基于 Aeon Agent v3.0 架构，新增两个核心模块：

1. **Goal Persistence System** - 目标持久化系统
2. **Attention System** - 注意力管理系统

解决 v3.0 的两个关键问题：
- **Goal 丢失问题**: `current_goal.json` 存储在内存，重启后丢失
- **信号淹没问题**: 所有事件权重相同，低价值事件淹没高价值事件

---

## 架构图 (v3.1)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         System Startup / Restart                        │
│                    (systemd / launcher.py)                              │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        Recovery Manager                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Recover      │  │ Recover      │  │ Recover      │                   │
│  │ Events       │  │ Tasks        │  │ Goals        │                   │
│  │ (v3.0)       │  │ (v3.0)       │  │ (v3.1 NEW)   │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     Event Bus (Persistent + ACK + Retry)                │
│                    (SQLite: events.db)                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Event Status:                                                   │   │
│  │  pending → processing → done/failed/dead                         │   │
│  │                     ↓ crash                                      │   │
│  │                  retry++                                         │   │
│  │  • retry_count ≤ MAX → 重新进入 pending                          │   │
│  │  • retry_count > MAX → dead (不再处理)                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                      Attention Manager (v3.1 NEW)                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Scoring Pipeline                                                │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │   │
│  │  │ Priority   │  │ Recency    │  │ Goal       │                │   │
│  │  │ Score      │  │ Score      │  │ Relevance  │                │   │
│  │  │ (base)     │  │ (exp decay)│  │ (keywords) │                │   │
│  │  └────────────┘  └────────────┘  └────────────┘                │   │
│  │              ↓              ↓              ↓                    │   │
│  │              └──────────────┴──────────────┘                    │   │
│  │                         ↓                                       │   │
│  │              Attention Score (weighted sum)                     │   │
│  │                         ↓                                       │   │
│  │         Dynamic Top-K (k = min(5, sqrt(n)))                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                   Cognition Loop (OODA + Trace)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Observe    │→ │  Orient     │→ │   Decide    │→ │   Act       │    │
│  │  (感知)     │  │  (理解)     │  │  (决策)     │  │  (执行)     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│         ↑                                                    │          │
│         └──────────────── Reflect ←──────────────────────────┘          │
│                                                                         │
│  [Trace] tick_id=xxx goal=yyy events=z tasks=w time=tms                 │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     Goal Manager (v3.1 NEW)                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Goal Store (SQLite: goals.db)                                   │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │   │
│  │  │ ACTIVE     │  │ PENDING    │  │ COMPLETED  │                │   │
│  │  │ (原子保证)  │  │ (等待队列)  │  │ (历史记录)  │                │   │
│  │  └────────────┘  └────────────┘  └────────────┘                │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  State Machine:                                                  │   │
│  │  pending → active → completed                                    │   │
│  │      ↓       ↓        ↓                                          │   │
│  │   paused   failed   cancelled                                    │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  Auto-completion:                                                │   │
│  │  IF all tasks finished → auto complete goal                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        Task System (Persistent)                         │
│                    (SQLite: tasks.db)                                   │
└──────────────────────────┬──────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        Workers / Executors                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 关键问题修复 (Review Feedback)

### 1. Event Bus 堆积问题

**问题**: 无 `processed` 标记导致事件无限堆积，半年后 events.db = 3GB

**解决方案**:
```sql
ALTER TABLE events ADD COLUMN status TEXT DEFAULT 'pending';  -- pending/processing/done/failed/dead
ALTER TABLE events ADD COLUMN processed_at REAL;
ALTER TABLE events ADD COLUMN processing_by TEXT;  -- worker_id
```

**流程**:
```
fetch WHERE status='pending'
    ↓
UPDATE status='processing' WHERE event_id IN (SELECT ...)
    ↓  
attention select top k
    ↓
process
    ↓
UPDATE status='done', processed_at=NOW()
```

**清理策略**:
```sql
-- 每周清理已处理且超过30天的事件
DELETE FROM events WHERE status='done' AND processed_at < NOW() - 30days;
```

### 2. Recency 指数衰减

**旧方案 (线性)**:
```
RecencyScore = max(0, 1 - age/300)
问题: 5分钟后突然=0，重要旧事件被忽略
```

**新方案 (指数)**:
```python
import math

def recency_score(age: float, tau: float = 300) -> float:
    """
    指数衰减: recency = exp(-age / τ)
    
    τ = 300s (5分钟半衰期)
    
    效果:
    - 1 min  → 0.82
    - 5 min  → 0.37  
    - 10 min → 0.14
    - 旧事件 gracefully 衰减，不会突然"死亡"
    """
    return math.exp(-age / tau)
```

### 3. Goal 自动激活原子操作

**问题**: 多线程竞争导致多个 active goal

**解决方案 (SQL 原子操作)**:
```sql
-- 保证永远只有一个 active goal
UPDATE goals
SET status='active', activated_at=UNIX_TIMESTAMP()
WHERE goal_id = (
    SELECT goal_id FROM goals
    WHERE status='pending'
    ORDER BY priority ASC, created_at ASC
    LIMIT 1
)
AND NOT EXISTS (
    SELECT 1 FROM goals WHERE status='active'
);
```

### 4. Goal Relevance 具体规则

**问题**: `calculate_relevance()` 是黑箱，用 LLM 太贵

**隐性 Bug**: 中文分词
```python
# ❌ 错误：中文 split() 无效
"完成架构设计".split()  # -> ["完成架构设计"]  整个字符串！

# ✅ 正确：手动提供 keywords
context.keywords = ["architecture", "design", "agent", "v3.1"]
```

**解决方案 (Keyword Overlap + 手动 Keywords)**:
```python
def calculate_goal_relevance(event: Event, goal: Dict) -> float:
    """
    基于关键词重叠的相关性计算
    无需 LLM，O(1) 复杂度
    
    注意：中文必须手动提供 keywords，不能依赖自动分词
    """
    # 提取目标关键词 (优先使用手动提供的 keywords)
    goal_keywords = set(goal.get("context", {}).get("keywords", []))
    
    # 英文描述可以简单 split 作为备选
    description = goal.get("description", "").lower()
    if description.isascii():
        goal_keywords.update(description.split())
    
    if not goal_keywords:
        return 0.0
    
    # 提取事件关键词
    event_text = f"{event.type} {json.dumps(event.data)}"
    event_keywords = set(event_text.lower().split())
    
    # 计算重叠
    overlap = len(goal_keywords & event_keywords)
    
    # 归一化
    relevance = min(1.0, overlap / len(goal_keywords))
    
    # 特定事件类型加分
    if event.type == "task.finished":
        if event.data.get("task_id") in goal.get("related_task_ids", []):
            relevance = 1.0  # 目标任务完成，最高相关
    
    return relevance
```

**Goal 创建时手动指定 keywords**:
```python
goal_manager.create_goal(
    description="完成 Aeon v3.1 架构设计",
    context={
        "keywords": ["aeon", "v3.1", "architecture", "design", "goal", "attention"]
    }
)
```

### 5. 两阶段 ACK

**问题**: Cognition crash 后事件丢失

**解决方案**:
```python
class EventStatus(Enum):
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中
    DONE = "done"            # 完成

# Cognition Loop 流程
def cognition_tick():
    # 1. 获取 pending 事件
    events = event_store.get_by_status(EventStatus.PENDING)
    
    # 2. 标记为 processing
    event_store.mark_processing([e.event_id for e in events])
    
    # 3. Attention 筛选
    selected = attention_manager.select(events)
    
    # 4. 处理
    try:
        process(selected)
        # 5a. 成功 → 标记 done
        event_store.mark_done([e.event_id for e in selected])
    except Exception:
        # 5b. 失败 → 保持 processing，下次重试
        pass
```

### 6. Goal-Task 自动同步

**问题**: Goal 可能永远 active，任务都完成了也不自动结束

**解决方案**:
```python
def check_goal_completion(goal: Goal) -> bool:
    """检查目标是否应该自动完成"""
    
    # 获取关联任务
    related_tasks = task_store.get_by_ids(goal.related_task_ids)
    
    if not related_tasks:
        return False  # 无关联任务，不自动完成
    
    # 检查是否所有任务都完成
    all_finished = all(
        t.status in [TaskStatus.FINISHED.value, TaskStatus.FAILED.value]
        for t in related_tasks
    )
    
    if all_finished:
        # 统计结果
        finished_count = sum(1 for t in related_tasks if t.status == TaskStatus.FINISHED.value)
        failed_count = len(related_tasks) - finished_count
        
        # 自动完成目标
        goal_manager.complete_goal(
            goal.goal_id,
            result={
                "auto_completed": True,
                "tasks_total": len(related_tasks),
                "tasks_finished": finished_count,
                "tasks_failed": failed_count
            }
        )
        return True
    
    return False

# 在 Task 完成时调用
@on_event(EventType.TASK_FINISHED)
def on_task_finished(event):
    # 更新关联目标的进度
    goal = goal_manager.get_goal_by_task(event.data["task_id"])
    if goal:
        check_goal_completion(goal)
```

### 7. 动态 Top-K

**旧方案**:
```python
max_events = 5  # 固定
```

**新方案**:
```python
import math

def dynamic_top_k(total_events: int, max_k: int = 5) -> int:
    """
    动态调整每轮处理事件数
    
    公式: k = min(max_k, ceil(sqrt(total_events)))
    
    效果:
    - events=1   → k=1
    - events=2   → k=2  (不会卡住)
    - events=4   → k=2
    - events=9   → k=3
    - events=25  → k=5
    - events=100 → k=5 (上限保护)
    """
    return min(max_k, math.ceil(math.sqrt(total_events)))

# 使用
k = dynamic_top_k(len(events))
selected = attention_manager.select(events, max_events=k)
```

### 8. Trace 日志 (增强版)

**每轮 Cognition Tick 输出**:
```python
import time
import psutil

def cognition_tick():
    tick_id = generate_tick_id()
    start_time = time.time()
    
    # ... cognition logic ...
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    # 获取队列大小
    queue_size = event_store.count_pending()
    
    # 获取内存使用
    memory_percent = psutil.virtual_memory().percent
    
    # Trace 日志 (增强版)
    logger.info(
        f"[Trace] tick={tick_id} "
        f"goal={active_goal.goal_id if active_goal else 'none'} "
        f"attention_events={len(attention_events)} "
        f"generated_tasks={len(new_tasks)} "
        f"queue={queue_size} "           # 待处理事件数
        f"mem={memory_percent:.0f}% "    # 内存使用率
        f"time={elapsed_ms:.1f}ms"
    )
```

**输出示例**:
```
[Trace] tick=abc123 goal=goal_001 attention_events=3 generated_tasks=2 queue=17 mem=24% time=45.2ms
[Trace] tick=abc124 goal=goal_001 attention_events=5 generated_tasks=1 queue=12 mem=25% time=38.7ms
[Trace] tick=abc125 goal=none attention_events=2 generated_tasks=0 queue=8 mem=23% time=12.3ms
```

---

## 数据流 (v3.1) - 修正版

### 完整数据流

```
System Startup
    ↓
┌─────────────────────────────────────────┐
│ Recovery Phase                          │
│ • events.db → reset_processing()        │
│   (processing事件→failed/dead)           │
│ • tasks.db  → recover_pending()         │
│ • goals.db  → recover_active()          │
└─────────────────────────────────────────┘
    ↓
Event Bus
    ↓ (WHERE status='pending' OR (status='failed' AND retryable))
┌─────────────────────────────────────────┐
│ Attention Manager                       │
│ • score_events(exp decay)               │
│ • rank_events()                         │
│ • select_top_k(dynamic k)               │
└─────────────────────────────────────────┘
    ↓ (高注意力事件)
┌─────────────────────────────────────────┐
│ Cognition Loop                          │
│ • UPDATE status='processing'            │
│ • process events                        │
│ • IF success → status='done'            │
│ • IF fail → retry_count++ → status='failed' (retryable)
│ • IF retry_count > MAX → status='dead'
└─────────────────────────────────────────┘
    ↓
Goal Check (原子操作)
    ↓
Planner → generate_tasks() → link to goal
    ↓
Task Queue → Workers
    ↓
[Task Finished] → check_goal_completion()
    ↓
Reflection Engine
    ↓
Memory System
    ↓
SLEEP (wait next heartbeat)
```

---

## Module 1: Goal Persistence System

### 1.1 设计目标

- **持久化**: Goal 存储在 SQLite，重启不丢失
- **原子性**: 自动激活使用 SQL 原子操作，防止多 active goal
- **状态机**: 支持 pending/active/paused/completed/failed/cancelled 状态流转
- **优先级**: 支持优先级排序，高优先级目标优先执行
- **层级结构**: 支持父子目标关系
- **自动完成**: 所有关联任务完成后自动标记目标完成

### 1.2 数据模型

```python
class GoalStatus(Enum):
    PENDING = "pending"      # 等待开始
    ACTIVE = "active"        # 正在执行
    PAUSED = "paused"        # 暂停
    COMPLETED = "completed"  # 完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 取消

class GoalPriority(Enum):
    CRITICAL = 0   # 系统关键
    HIGH = 1       # 高优先级
    NORMAL = 2     # 普通
    LOW = 3        # 低优先级

@dataclass
class Goal:
    goal_id: str
    description: str
    status: GoalStatus
    priority: GoalPriority
    
    # 层级
    parent_goal_id: Optional[str] = None
    sub_goals: List[str] = None
    
    # 上下文 (⚠️ 必须手动提供 keywords，中文分词不可靠)
    context: Dict[str, Any] = None  # 格式: {"keywords": ["word1", "word2"]}
    success_criteria: List[str] = None
    
    # 时间
    created_at: float
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # 关联
    related_task_ids: List[str] = None
    
    def get_keywords(self) -> Set[str]:
        """
        提取关键词用于 relevance 计算
        ⚠️ 中文必须手动提供 keywords，不能依赖自动分词
        """
        # 优先使用手动提供的 keywords
        keywords = set(self.context.get("keywords", []))
        
        # 英文描述可以简单 split 作为备选
        if self.description.isascii():
            keywords.update(self.description.lower().split())
        
        return keywords
```

### 1.3 数据库 Schema

```sql
-- goals.db
CREATE TABLE goals (
    goal_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    parent_goal_id TEXT,
    sub_goals TEXT,                 -- JSON array
    context TEXT,                   -- JSON object (含 keywords，⚠️ 中文必须手动提供)
    success_criteria TEXT,          -- JSON array
    created_at REAL,
    activated_at REAL,
    completed_at REAL,
    related_task_ids TEXT,          -- JSON array
    auto_completed INTEGER DEFAULT 0 -- 是否自动完成
);

CREATE INDEX idx_goals_status ON goals(status);
CREATE INDEX idx_goals_priority ON goals(priority);
CREATE INDEX idx_goals_parent ON goals(parent_goal_id);
CREATE INDEX idx_goals_activated ON goals(activated_at);
```

### 1.4 核心 API

```python
class GoalManager:
    # 创建
    def create_goal(description, priority=NORMAL, **kwargs) -> Goal
    
    # 使用示例 (⚠️ 中文必须手动提供 keywords)
    goal = goal_manager.create_goal(
        description="完成 Aeon v3.1 架构设计",
        priority=GoalPriority.HIGH,
        context={
            "keywords": ["aeon", "v3.1", "architecture", "design", "goal", "attention"],
            "notes": "基于朋朋的 review 反馈"
        },
        success_criteria=["文档完成", "代码实现", "测试通过"]
    )
    
    # 状态流转 (原子操作保证)
    def activate_next_pending() -> Optional[Goal]:
        """
        原子激活下一个 pending goal
        SQL保证永远只有一个 active goal
        """
    
    def pause_goal(goal_id)                 # active -> paused
    def resume_goal(goal_id)                # paused -> active
    def complete_goal(goal_id, result)      # active -> completed
    def fail_goal(goal_id, reason)          # active -㸅 failed
    
    # 查询
    def get_active_goal() -> Optional[Goal]
    def get_pending_goals(limit=5) -> List[Goal]
    def get_goal_by_id(goal_id) -> Optional[Goal]
    def get_goal_by_task(task_id) -> Optional[Goal]
    
    # 自动管理
    def auto_pick_next_goal() -> Optional[Goal]
    def check_and_complete(goal_id) -> bool:
        """检查并自动完成目标"""
    
    # 启动恢复
    def recover_on_startup() -> Dict
```

### 1.5 原子激活实现

```python
def activate_next_pending(self) -> Optional[Goal]:
    """
    原子激活下一个 pending goal
    使用 SQL 保证永远只有一个 active goal
    """
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.execute("""
            UPDATE goals
            SET status = 'active', activated_at = ?
            WHERE goal_id = (
                SELECT goal_id FROM goals
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            )
            AND NOT EXISTS (
                SELECT 1 FROM goals WHERE status = 'active'
            )
            RETURNING *
        """, (time.time(),))
        
        row = cursor.fetchone()
        conn.commit()
        
        if row:
            return self._row_to_goal(row)
        return None
```

### 1.6 自动完成检查 (含保护条件)

```python
def check_and_complete(self, goal_id: str) -> bool:
    """
    检查目标是否应该自动完成或失败
    返回: 是否已处理 (完成或失败)
    
    保护条件:
    - 无关联任务 → 标记为失败 (规划失败)
    - 所有任务完成 → 标记为完成
    - 部分任务失败 → 仍标记为完成 (记录失败数)
    """
    goal = self.get_by_id(goal_id)
    if not goal or goal.status != GoalStatus.ACTIVE:
        return False
    
    # 保护条件: 无关联任务 = 规划失败
    if not goal.related_task_ids:
        self.fail_goal(
            goal_id,
            reason="planning_failed",
            details={"error": "No tasks generated after planning"}
        )
        logger.warning(f"Goal {goal_id} failed: no tasks generated")
        return True
    
    # 获取所有关联任务
    from tasks.task_system import TaskPersistence
    task_store = TaskPersistence()
    tasks = task_store.get_by_ids(goal.related_task_ids)
    
    # 保护条件: 任务列表为空 (可能被删除)
    if not tasks:
        self.fail_goal(
            goal_id,
            reason="tasks_missing",
            details={"error": "All related tasks deleted or missing"}
        )
        logger.warning(f"Goal {goal_id} failed: related tasks missing")
        return True
    
    # 检查是否全部完成
    all_done = all(
        t.status in [TaskStatus.FINISHED.value, TaskStatus.FAILED.value]
        for t in tasks
    )
    
    if all_done:
        finished = sum(1 for t in tasks if t.status == TaskStatus.FINISHED.value)
        failed = len(tasks) - finished
        
        self.complete_goal(
            goal_id,
            result={
                "auto_completed": True,
                "tasks_total": len(tasks),
                "tasks_finished": finished,
                "tasks_failed": failed,
                "completion_rate": finished / len(tasks)
            }
        )
        return True
    
    return False
```

### 1.7 规划阶段的保护

```python
class Planner:
    def plan_for_goal(self, goal: Goal) -> List[Task]:
        """
        为目标生成任务
        如果无法生成任务，立即标记目标失败
        """
        tasks = self._generate_tasks(goal)
        
        if not tasks:
            # 无法规划 → 目标立即失败
            self.goal_manager.fail_goal(
                goal.goal_id,
                reason="unplannable",
                details={"error": "Planner could not generate any tasks for this goal"}
            )
            logger.error(f"Goal {goal.goal_id} is unplannable, marked as failed")
            return []
        
        # 保存任务并关联到目标
        task_ids = [t.task_id for t in tasks]
        self.goal_manager.link_tasks(goal.goal_id, task_ids)
        
        return tasks
```

---

## Module 2: Attention System

### 2.1 设计目标

- **优先级区分**: 不同事件类型有不同的基础优先级
- **指数衰减**: 时间衰减使用指数函数，旧事件 gracefully 降级
- **目标相关**: 基于 keyword overlap 计算相关性，无需 LLM
- **有限注意力**: 动态 Top-K，防止认知过载
- **两阶段 ACK**: pending → processing → done，支持崩溃恢复

### 2.2 事件状态管理 (含重试机制 + TTL)

```sql
-- events.db schema update
ALTER TABLE events ADD COLUMN status TEXT DEFAULT 'pending';
ALTER TABLE events ADD COLUMN processed_at REAL;
ALTER TABLE events ADD COLUMN processing_by TEXT;  -- worker_id
ALTER TABLE events ADD COLUMN retry_count INTEGER DEFAULT 0;  -- 重试次数
ALTER TABLE events ADD COLUMN last_error TEXT;  -- 上次错误信息
ALTER TABLE events ADD COLUMN expires_at REAL;  -- TTL 过期时间 (NEW)

-- 索引
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_created ON events(created_at);
CREATE INDEX idx_events_retry ON events(retry_count);
CREATE INDEX idx_events_expires ON events(expires_at);  -- (NEW)
```

```python
class EventStatus(Enum):
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中 (防并发)
    DONE = "done"            # 完成
    FAILED = "failed"        # 处理失败 (可重试)
    DEAD = "dead"           # 死信 (超过重试阈值，不再处理)
    EXPIRED = "expired"     # 已过期 (超过 TTL，不再处理)

class EventConfig:
    MAX_RETRY = 3  # 最大重试次数
    RETRY_DELAY = 60  # 重试间隔 (秒)
    
    # TTL 配置 (秒)
    TTL_MAP = {
        "system.shutdown": 3600,      # 1小时
        "system.critical_error": 86400,  # 24小时
        "message.received": 300,      # 5分钟
        "user.command": 300,          # 5分钟
        "task.failed": 600,           # 10分钟
        "task.finished": 300,         # 5分钟
        "cognition.plan": 120,        # 2分钟
        "cognition.reflect": 60,      # 1分钟
        "memory.updated": 60,         # 1分钟
        "cognition.tick": 30,         # 30秒
        "heartbeat": 30,              # 30秒
        "default": 300,               # 默认5分钟
    }
    
    @classmethod
    def get_ttl(cls, event_type: str) -> float:
        return cls.TTL_MAP.get(event_type, cls.TTL_MAP["default"])
```

**TTL 机制说明**:
- 每个事件创建时计算 `expires_at = now + TTL`
- Attention Manager 只查询 `expires_at > now` 的事件
- 过期事件自动标记为 `expired`，不参与处理
- 清理任务可以安全删除 expired 事件

### 2.3 事件优先级配置

```python
class EventPriority(Enum):
    CRITICAL = 1.0   # 系统关键
    HIGH = 0.8       # 用户消息、任务失败
    NORMAL = 0.5     # 常规事件
    LOW = 0.2        # 内部心跳
    BACKGROUND = 0.1 # 统计、清理

EVENT_PRIORITY_MAP = {
    # Critical (1.0)
    "system.shutdown": 1.0,
    "system.critical_error": 1.0,
    "system.emergency": 1.0,
    
    # High (0.8)
    "message.received": 0.8,
    "user.command": 0.8,
    "user.urgent": 0.8,
    "task.failed": 0.8,
    "task.timeout": 0.8,
    
    # Normal (0.5)
    "task.finished": 0.5,
    "task.created": 0.5,
    "task.started": 0.5,
    "cognition.plan": 0.5,
    "memory.created": 0.5,
    
    # Low (0.2)
    "cognition.reflect": 0.2,
    "memory.updated": 0.2,
    "memory.accessed": 0.2,
    "state.changed": 0.2,
    
    # Background (0.1)
    "cognition.tick": 0.1,
    "heartbeat": 0.1,
    "system.log": 0.1,
}
```

### 2.4 注意力分数计算

```python
import math
from typing import Dict, Any, Set

class AttentionConfig:
    TAU = 300.0           # 5分钟半衰期
    PRIORITY_WEIGHT = 0.6
    RECENCY_WEIGHT = 0.2
    GOAL_WEIGHT = 0.2
    MAX_K = 5

def recency_score(age: float, tau: float = AttentionConfig.TAU) -> float:
    """指数衰减: recency = exp(-age / τ)"""
    return math.exp(-age / tau)

def goal_relevance_score(event: Event, goal: Dict) -> float:
    """
    基于关键词重叠的相关性计算
    O(n) 复杂度，无需 LLM
    
    ⚠️ 重要: 中文必须手动提供 keywords，不能依赖自动分词
    "完成架构设计".split() -> ["完成架构设计"] (无效)
    """
    # 提取目标关键词 (优先使用手动提供的 keywords)
    goal_keywords = set(goal.get("keywords", []))
    
    # 英文描述可以简单 split 作为备选
    description = goal.get("description", "").lower()
    if description.isascii():
        goal_keywords.update(description.split())
    
    if not goal_keywords:
        return 0.0
    
    event_text = f"{event.type} {json.dumps(event.data)}"
    event_keywords = set(event_text.lower().split())
    
    overlap = len(goal_keywords & event_keywords)
    relevance = min(1.0, overlap / len(goal_keywords))
    
    # 任务完成事件特殊处理
    if event.type == "task.finished":
        task_id = event.data.get("task_id")
        if task_id in goal.get("related_task_ids", []):
            relevance = max(relevance, 0.9)
    
    return relevance

def calculate_attention_score(
    event: Event,
    current_goal: Optional[Dict] = None
) -> float:
    """综合注意力分数"""
    
    # 1. 基础优先级
    priority = EVENT_PRIORITY_MAP.get(event.type, EventPriority.NORMAL)
    priority_score = priority.value
    
    # 2. 时间新鲜度 (指数衰减)
    age = time.time() - event.timestamp
    recency = recency_score(age)
    
    # 3. 目标相关性
    goal_relevance = 0.0
    if current_goal:
        goal_relevance = goal_relevance_score(event, current_goal)
    
    # 4. 加权综合
    score = (
        AttentionConfig.PRIORITY_WEIGHT * priority_score +
        AttentionConfig.RECENCY_WEIGHT * recency +
        AttentionConfig.GOAL_WEIGHT * goal_relevance
    )
    
    return score
```

### 2.5 动态 Top-K

```python
def dynamic_top_k(total_events: int, max_k: int = AttentionConfig.MAX_K) -> int:
    """
    动态调整每轮处理事件数
    
    公式: k = min(max_k, ceil(sqrt(total_events)))
    
    效果:
    - events=1   → k=1
    - events=2   → k=2  (不会卡住第二个事件)
    - events=4   → k=2
    - events=9   → k=3
    - events=25  → k=5
    - events=100 → k=5 (上限保护)
    """
    return min(max_k, math.ceil(math.sqrt(total_events)))
```

### 2.6 核心 API

```python
class AttentionManager:
    def __init__(self, goal_manager=None):
        self.goal_manager = goal_manager
    
    def score_event(self, event: Event, current_goal: Optional[Dict]) -> ScoredEvent:
        """为单个事件计算注意力分数"""
        score = calculate_attention_score(event, current_goal)
        return ScoredEvent(event=event, attention_score=score)
    
    def select_attention_events(
        self,
        events: List[Event],
        current_goal: Optional[Dict] = None
    ) -> List[Event]:
        """
        选择高注意力事件
        1. 计算分数
        2. 排序
        3. 动态 Top-K 选择
        """
        if not events:
            return []
        
        # 1. 评分
        scored = [self.score_event(e, current_goal) for e in events]
        
        # 2. 排序 (高到低)
        scored.sort(key=lambda x: x.attention_score, reverse=True)
        
        # 3. 动态 Top-K
        k = dynamic_top_k(len(events))
        selected = scored[:k]
        
        # 日志
        for s in selected:
            logger.debug(f"[Attention] {s.event.type}: score={s.attention_score:.3f}")
        
        return [s.event for s in selected]
```

### 2.7 两阶段 ACK 集成 (含重试机制)

```python
class CognitionLoop:
    def tick(self):
        tick_id = generate_tick_id()
        start_time = time.time()
        
        # 1. 获取 pending + 可重试的 failed 事件
        pending_events = self.event_store.get_pending_and_retryable()
        
        # 2. 获取当前目标
        active_goal = self.goal_manager.get_active_goal()
        goal_dict = active_goal.to_dict() if active_goal else None
        
        # 3. Attention 筛选
        attention_events = self.attention_manager.select_attention_events(
            pending_events, goal_dict
        )
        
        # 4. 标记为 processing
        if attention_events:
            self.event_store.mark_processing(
                [e.event_id for e in attention_events],
                worker_id=self.worker_id
            )
        
        # 5. 处理
        for event in attention_events:
            try:
                result = self.process_event(event)
                
                # 5a. 成功 → 标记 done
                self.event_store.mark_done(event.event_id)
                
            except Exception as e:
                # 5b. 失败 → 重试计数 + 1
                retry_count = (event.retry_count or 0) + 1
                
                if retry_count >= EventConfig.MAX_RETRY:
                    # 超过阈值 → 标记为 dead (死信)
                    self.event_store.mark_dead(
                        event.event_id, 
                        error=str(e),
                        retry_count=retry_count
                    )
                    logger.error(
                        f"Event {event.event_id} marked as DEAD after "
                        f"{retry_count} retries"
                    )
                else:
                    # 可重试 → 标记为 failed，等待下次
                    self.event_store.mark_failed(
                        event.event_id,
                        error=str(e),
                        retry_count=retry_count
                    )
                    logger.warning(
                        f"Event {event.event_id} failed, retry {retry_count}/"
                        f"{EventConfig.MAX_RETRY}"
                    )
        
        # 6. Trace 日志
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"[Trace] tick={tick_id} "
            f"goal={active_goal.goal_id if active_goal else 'none'} "
            f"attention_events={len(attention_events)} "
            f"time={elapsed_ms:.1f}ms"
        )
```

### 2.8 事件重试机制

#### 状态流转

```
                    first time
                         ↓
                    ┌─────────┐
         ┌─────────│ PENDING │←────────────────────┐
         │         └────┬────┘                     │
         │              │ processing()              │ retry
         │              ↓                           │
         │         ┌─────────┐      fail+retry     │
         │    ┌────│PROCESSING│←────────────────────┘
         │    │    └────┬────┘
         │    │         │ process success
         │    │         ↓
         │    │    ┌─────────┐
         │    └────│  DONE   │
         │    crash└─────────┘
         │
         │         fail+retry_count≥MAX
         │              ↓
         │         ┌─────────┐
         └────────→│ FAILED  │
                   └────┬────┘
         retry_count++  │
              ↓         │ retry_count≥MAX
         ┌─────────┐    ↓
         │ DEAD    │←───┘
         └─────────┘
         (不再处理，可人工审查)
```

#### 核心 API

```python
class EventStore:
    def get_pending_and_retryable(self, limit: int = 100) -> List[Event]:
        """
        获取待处理事件 + 可重试的失败事件
        只返回未过期的事件
        
        可重试条件:
        - status = 'failed'
        - retry_count < MAX_RETRY
        - 距离上次失败超过 RETRY_DELAY
        - 未过期 (expires_at > now)
        """
        now = time.time()
        cutoff = now - EventConfig.RETRY_DELAY
        
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT * FROM events
                WHERE (status = 'pending'
                       OR (status = 'failed' 
                           AND retry_count < ?
                           AND processed_at < ?))
                  AND expires_at > ?  -- 未过期
                ORDER BY created_at ASC
                LIMIT ?
            """, (EventConfig.MAX_RETRY, cutoff, now, limit)).fetchall()
            
            return [self._row_to_event(r) for r in rows]
    
    def mark_processing(self, event_ids: List[str], worker_id: str):
        """标记为处理中"""
        with sqlite3.connect(self.db_path) as conn:
            for event_id in event_ids:
                conn.execute("""
                    UPDATE events
                    SET status = 'processing',
                        processing_by = ?,
                        processed_at = ?
                    WHERE event_id = ?
                """, (worker_id, time.time(), event_id))
            conn.commit()
    
    def mark_done(self, event_id: str):
        """标记为完成"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE events
                SET status = 'done',
                    processed_at = ?,
                    processing_by = NULL
                WHERE event_id = ?
            """, (time.time(), event_id))
            conn.commit()
    
    def mark_failed(self, event_id: str, error: str, retry_count: int):
        """标记为失败 (可重试)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE events
                SET status = 'failed',
                    retry_count = ?,
                    last_error = ?,
                    processed_at = ?,
                    processing_by = NULL
                WHERE event_id = ?
            """, (retry_count, error, time.time(), event_id))
            conn.commit()
    
    def mark_dead(self, event_id: str, error: str, retry_count: int):
        """标记为死信 (不再处理)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE events
                SET status = 'dead',
                    retry_count = ?,
                    last_error = ?,
                    processed_at = ?,
                    processing_by = NULL
                WHERE event_id = ?
            """, (retry_count, error, time.time(), event_id))
            conn.commit()
    
    def reset_processing_on_startup(self, worker_id: str = None):
        """
        启动时重置 processing 状态
        将本 worker 或所有 processing 事件重置为 pending/failed
        """
        with sqlite3.connect(self.db_path) as conn:
            if worker_id:
                # 只重置本 worker 的事件
                conn.execute("""
                    UPDATE events
                    SET status = CASE 
                            WHEN retry_count >= ? THEN 'dead'
                            ELSE 'failed'
                         END,
                        processing_by = NULL,
                        retry_count = retry_count + 1
                    WHERE status = 'processing' AND processing_by = ?
                """, (EventConfig.MAX_RETRY, worker_id))
            else:
                # 重置所有 processing (crash recovery)
                conn.execute("""
                    UPDATE events
                    SET status = CASE 
                            WHEN retry_count >= ? THEN 'dead'
                            ELSE 'failed'
                         END,
                        processing_by = NULL,
                        retry_count = retry_count + 1
                    WHERE status = 'processing'
                """, (EventConfig.MAX_RETRY,))
            conn.commit()
```

#### 死信队列监控

```python
def monitor_dead_letters(db_path: str) -> List[Event]:
    """监控死信事件，可发送告警"""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT * FROM events
            WHERE status = 'dead'
            ORDER BY processed_at DESC
            LIMIT 10
        """).fetchall()
        
        return [row_to_event(r) for r in rows]

# 使用示例
dead_events = monitor_dead_letters('db/events.db')
if dead_events:
    logger.error(f"ALERT: {len(dead_events)} dead letter events detected!")
    for e in dead_events:
        logger.error(f"  Dead: {e.event_id} | {e.type} | {e.last_error}")
```

#### 清理策略 (含死信 + 过期事件)

```python
def cleanup_old_events(db_path: str, days: int = 30):
    """
    清理旧事件:
    - done 事件: 30天后删除
    - dead 事件: 7天后删除 (保留一段时间用于排查)
    - expired 事件: 立即删除 (已过期无需保留)
    """
    now = time.time()
    done_cutoff = now - (days * 24 * 60 * 60)
    dead_cutoff = now - (7 * 24 * 60 * 60)  # 死信保留7天
    
    with sqlite3.connect(db_path) as conn:
        # 清理 expired (立即删除)
        c0 = conn.execute(
            "DELETE FROM events WHERE status = 'expired' OR expires_at < ?",
            (now,)
        )
        
        # 清理 done
        c1 = conn.execute(
            "DELETE FROM events WHERE status = 'done' AND processed_at < ?",
            (done_cutoff,)
        )
        
        # 清理 dead
        c2 = conn.execute(
            "DELETE FROM events WHERE status = 'dead' AND processed_at < ?",
            (dead_cutoff,)
        )
        
        conn.commit()
        
    logger.info(
        f"Cleanup: {c0.rowcount} expired + {c1.rowcount} done + "
        f"{c2.rowcount} dead events deleted"
    )
```

---

## Trace 日志规范

### 格式 (增强版)

```
[Trace] tick={tick_id} goal={goal_id} events={n} tasks={m} queue={q} mem={p}% time={ms}ms
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| tick | str | 本轮认知的唯一标识 |
| goal | str | 当前活跃目标的 ID (若无则为 'none') |
| events | int | 本轮处理的高注意力事件数 |
| tasks | int | 本轮生成的任务数 |
| queue | int | 当前待处理事件队列大小 |
| mem | float | 系统内存使用百分比 |
| time | float | 本轮执行耗时 (毫秒) |

### 输出示例

```
[Trace] tick=abc123 goal=goal_001 events=3 tasks=2 queue=17 mem=24% time=45.2ms
[Trace] tick=abc124 goal=goal_001 events=5 tasks=1 queue=12 mem=25% time=38.7ms
[Trace] tick=abc125 goal=none events=2 tasks=0 queue=8 mem=23% time=12.3ms
[Trace] tick=abc126 goal=goal_002 events=4 tasks=3 queue=24 mem=31% time=52.1ms
```

### 用途

- **性能监控**: 识别慢 tick
- **调试追踪**: 通过 tick_id 串联日志
- **目标跟踪**: 观察 goal 切换频率
- **负载分析**: events/tasks/queue 比例
- **内存泄漏**: 监控 mem 趋势
- **队列堆积**: queue 持续增长 = 处理不过来

### 实现代码

```python
import time
import psutil

def cognition_tick(self):
    tick_id = generate_tick_id()
    start_time = time.time()
    
    # ... cognition logic ...
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    # 获取队列大小
    queue_size = self.event_store.count_pending()
    
    # 获取内存使用
    memory_percent = psutil.virtual_memory().percent
    
    # Trace 日志 (增强版)
    logger.info(
        f"[Trace] tick={tick_id} "
        f"goal={active_goal.goal_id if active_goal else 'none'} "
        f"events={len(attention_events)} "
        f"tasks={len(new_tasks)} "
        f"queue={queue_size} "           # 待处理事件数
        f"mem={memory_percent:.0f}% "    # 内存使用率
        f"time={elapsed_ms:.1f}ms"
    )
```

---

## 文件结构

```
agent/
├── goals/                          # NEW MODULE
│   ├── __init__.py
│   ├── models.py                   # Goal, GoalStatus, GoalPriority
│   ├── goal_store.py              # SQLite persistence
│   └── goal_manager.py            # Goal lifecycle + auto-completion
│
├── attention/                      # NEW MODULE
│   ├── __init__.py
│   ├── config.py                  # Event priority config
│   ├── scoring.py                 # Scoring algorithms (exp decay, keyword)
│   └── attention_manager.py       # Attention management + dynamic top-k
│
├── bus/                           # MODIFIED
│   ├── __init__.py
│   └── event_bus.py               # Add: EventStatus, two-phase ACK, retry
│
├── cognition/                     # MODIFIED
│   └── cognition_loop.py          # Add: Trace logging
│
├── db/
│   ├── events.db                  # Add: status, processed_at, processing_by, retry_count, last_error, expires_at
│   ├── tasks.db                   # (existing)
│   ├── memory.db                  # (existing)
│   └── goals.db                   # NEW
│
└── launcher.py                    # (modify: add Goal recovery)
```

---

## 实施顺序

### Phase 1: Event Bus 改造 (基础)

```
1. bus/event_bus.py
   - Add EventStatus enum (pending/processing/done/failed/dead/expired)
   - Add retry_count, last_error, expires_at columns
   - Add two-phase ACK methods
   - Add retry mechanism
   - Add TTL handling

2. db/events.db
   - Migration: add status, processed_at, processing_by, retry_count, last_error, expires_at

3. Test: event lifecycle with retry + TTL
   pending → processing → fail → retry → dead
   pending → expired (auto)
```

### Phase 2: Goal Persistence (核心)

```
1. goals/models.py
2. goals/goal_store.py
3. goals/goal_manager.py
   - Atomic activation
   - Auto-completion check

4. launcher.py
   - Add Goal recovery

5. Test: restart recovery, auto-completion
```

### Phase 3: Attention System (优化)

```
1. attention/config.py
2. attention/scoring.py
   - Exponential decay
   - Keyword relevance

3. attention/attention_manager.py
   - Dynamic top-k

4. cognition_loop.py
   - Integrate Attention
   - Add Trace logging

5. Test: priority ordering, dynamic k
```

### Phase 4: 集成测试

```
1. End-to-end test
2. Crash recovery test
3. Dead letter monitoring test
4. Performance test (1000+ events)
5. Cleanup job test (old events)
```

---

## 运行示例

### 启动恢复

```
[14:00:00] System Startup
[14:00:00] Event Recovery: 3 processing events → failed/dead
[14:00:00] Task Recovery: 2 pending tasks loaded
[14:00:00] Goal Recovery: {
    "status": "resumed",
    "recovered_goal": "goal_xxx",
    "description": "完成 Aeon v3.1 架构设计"
}
```

### Attention 处理

```
[14:15:00] Cognition Tick
[14:15:00] Raw events: 12 (pending+retryable)
[14:15:00] Attention Scoring:
           - message.received: score=0.92 (priority=0.8, recency=0.95, goal=0.9)
           - task.failed: score=0.88 (priority=1.0, recency=0.85, goal=0.0)
           - cognition.tick: score=0.12 (priority=0.1, recency=0.45, goal=0.0)
           ...
[14:15:00] Dynamic Top-K: sqrt(12)=3.46 → k=3
[14:15:00] Selected 3 events for processing
[14:15:00] Marked 3 events as processing
[14:15:00] Processing complete
[14:15:00] Marked 3 events as done
[Trace] tick=abc123 goal=goal_xxx events=3 tasks=2 time=45.2ms
```

### 事件重试与死信

```
[14:20:00] Processing event: evt_001
[14:20:00] Event evt_001 failed: Connection timeout
[14:20:00] Marked evt_001 as failed, retry 1/3
...
[14:21:00] Retrying event: evt_001 (retry 2/3)
[14:21:00] Event evt_001 failed again
[14:21:00] Marked evt_001 as failed, retry 2/3
...
[14:22:00] Retrying event: evt_001 (retry 3/3)
[14:22:00] Event evt_001 failed for the last time
[14:22:00] ALERT: Event evt_001 marked as DEAD after 3 retries
[14:22:00] Dead letter: evt_001 | type=message.send | error=Connection timeout
```

### Goal 自动完成与失败

```
[14:25:00] Task Finished: task_001
[14:25:00] Checking goal completion...
[14:25:00] Goal goal_xxx: 3/3 tasks finished
[14:25:00] Auto-completing goal_xxx
[14:25:00] Goal goal_xxx completed (auto_completed=True)
[14:25:00] Activating next pending goal...
[14:25:00] Goal goal_yyy activated

[14:30:00] Planning for goal: goal_zzz
[14:30:00] ERROR: Planner could not generate any tasks
[14:30:00] Goal goal_zzz marked as FAILED (reason: unplannable)
[14:30:00] Activating next pending goal...
```

---

## 数据库迁移脚本

### events.db

```sql
-- 添加状态字段
ALTER TABLE events ADD COLUMN status TEXT DEFAULT 'pending';
ALTER TABLE events ADD COLUMN processed_at REAL;
ALTER TABLE events ADD COLUMN processing_by TEXT;
ALTER TABLE events ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE events ADD COLUMN last_error TEXT;
ALTER TABLE events ADD COLUMN expires_at REAL;  -- TTL 过期时间

-- 创建索引
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_processed ON events(processed_at);
CREATE INDEX idx_events_retry ON events(retry_count);
CREATE INDEX idx_events_expires ON events(expires_at);

-- 迁移现有数据 (设置默认 TTL 为 5 分钟)
UPDATE events SET status = 'done' WHERE processed = 1;
UPDATE events SET status = 'pending' WHERE processed = 0 OR processed IS NULL;
UPDATE events SET expires_at = created_at + 300 WHERE expires_at IS NULL;

-- 清理旧字段 (可选)
-- ALTER TABLE events DROP COLUMN processed;
```

### goals.db

```sql
CREATE TABLE goals (
    goal_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    parent_goal_id TEXT,
    sub_goals TEXT,
    context TEXT,
    success_criteria TEXT,
    created_at REAL,
    activated_at REAL,
    completed_at REAL,
    related_task_ids TEXT,
    auto_completed INTEGER DEFAULT 0
);

CREATE INDEX idx_goals_status ON goals(status);
CREATE INDEX idx_goals_priority ON goals(priority);
CREATE INDEX idx_goals_parent ON goals(parent_goal_id);
```

---

## 未来优化方向 (Future Work)

### Priority Queue 替代 SQLite Scan

**当前方案 (v3.1)**:
```
SQLite Table (events)
    ↓
SELECT * WHERE status='pending' AND expires_at > now
    ↓
Python 层排序 (attention score)
    ↓
取 Top-K
```

**问题**: 事件量大时，`SELECT + Python 排序` 会成为瓶颈

**未来方案 (v4.0)**:
```
Priority Queue (Redis / RabbitMQ / 内存堆)
    ↓
直接 pop 最高优先级事件
    ↓
无需扫描全表
```

**优势**:
- O(log n) 取事件 vs O(n log n) 扫描排序
- 天然支持优先级
- 可横向扩展 (多 worker)

**触发条件**:
- events.db > 100MB
- 单轮 cognition tick > 500ms
- 事件产生速度 > 处理速度

**结论**: 当前 SQLite 完全够用，但架构预留了升级空间

---

**Document Version**: 1.7 (Reviewed + Retry + TTL + Top-K Fix + Goal Protection + Chinese Keywords + Enhanced Trace)
**Last Updated**: 2026-04-06
**Author**: Kimi Claw (虾虾)
**Reviewer**: 朋朋
**Changes**: 
- Fixed: Event Bus 堆积问题 (processed status)
- Fixed: Recency 指数衰减
- Fixed: Goal 原子激活
- Fixed: Goal Relevance keyword overlap
- Fixed: 中文分词问题 (必须手动提供 keywords)
- Fixed: 两阶段 ACK
- Fixed: Goal-Task 自动同步 (含无任务保护)
- Fixed: 动态 Top-K (ceil instead of int)
- Added: Trace 日志规范 (增强版，含 queue 和 mem)
- Added: 事件重试机制 (retry_count, failed/dead 状态, 死信监控)
- Added: TTL 机制 (expires_at, 过期自动标记, 按类型配置)
