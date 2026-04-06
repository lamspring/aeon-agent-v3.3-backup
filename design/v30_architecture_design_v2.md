# v30 架构升级设计文档 v3.0
**代号**: Aeon (永恒)  
**日期**: 2026-04-06  
**状态**: 生产级设计完成 - 待批准实施

---

## 核心优化原则

> **Event Bus = 唯一调度中心**  
> 避免多调度中心导致的循环触发和复杂度爆炸。

---

## 1. 最终架构

```
                    Event Bus (中央神经系统)
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    Memory          Cognition           Tasks
   Listener         Listener          Listener
        │                │                │
        ↓                ↓                ↓
   Memory Index    OODA Loop        Task Planner
   (episodic/      (决策层)          (规划层)
    semantic)
        │                │                │
        └──────────→ Task Queue ←─────────┘
                            │
                         Workers
                        (执行层)
```

**关键变化**:
- Event Bus 是唯一调度中心
- Cognition = 决策层 (不是独立调度)
- Task Planner = 规划层 (LLM规划 → Queue → Workers)
- Memory = 长期经验 (episodic + semantic 分离)

---

## 2. 模块详细设计

### 模块1: Event Bus (中央神经系统)

#### 核心原则
```
Event → Bus → Listener → Action
```
**禁止**: cognition → queue → event → cognition 循环

#### 事件类型
```python
class EventTypes:
    # 记忆事件
    MEMORY_UPDATED = "memory.updated"
    MEMORY_ACCESSED = "memory.accessed"
    
    # 任务事件  
    TASK_CREATED = "task.created"
    TASK_PLANNED = "task.planned"      # NEW: 任务规划完成
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
    COGNITION_TICK = "cognition.tick"   # NEW: 认知时钟触发
    
    # 认知事件 (NEW)
    COGNITION_PLAN = "cognition.plan"   # 需要规划
    COGNITION_REFLECT = "cognition.reflect"  # 需要反思
```

#### 保护层: Rate Limiter + TTL + 去重

**1. Rate Limiter** (防 Event Storm):
```python
EVENT_RATE_LIMITS = {
    "memory.updated": 10,      # 每秒最多10次
    "task.created": 20,
    "cognition.tick": 1,       # 每秒1次 (30s间隔)
    "memory.accessed": 50      # 读取不限流
}

# 防递归规则
def should_process(event_type, source):
    # cognition 不监听 memory.updated
    if source == "cognition" and event_type == "memory.updated":
        return False
    return True
```

**2. Event TTL** (防过期事件触发):
```python
class Event:
    def __init__(self, type, data, ttl=60):
        self.id = generate_uuid()
        self.type = type
        self.data = data
        self.timestamp = time.now()
        self.ttl = ttl  # 默认60秒过期
    
    def is_expired(self):
        return time.now() - self.timestamp > self.ttl

# Event Bus 处理时检查
def process_event(event):
    if event.is_expired():
        logger.warning(f"Event {event.id} expired, dropping")
        return
    # 正常处理...
```
**避免**: 3小时前的事件突然触发

**3. Event Deduplication** (防重复触发):
```python
class EventBus:
    def __init__(self):
        self.recent_events = {}  # event_hash -> timestamp
        self.dedup_window = 5    # 5秒去重窗口
    
    def publish(self, event):
        # 生成事件指纹
        event_hash = hash(f"{event.type}:{str(event.data)}")
        
        # 检查是否重复
        if event_hash in self.recent_events:
            last_time = self.recent_events[event_hash]
            if time.now() - last_time < self.dedup_window:
                logger.debug(f"Duplicate event {event.type}, ignoring")
                return
        
        # 记录并发布
        self.recent_events[event_hash] = time.now()
        self._do_publish(event)
    
    def cleanup_dedup_cache(self):
        # 清理过期指纹
        cutoff = time.now() - self.dedup_window
        self.recent_events = {
            k: v for k, v in self.recent_events.items() 
            if v > cutoff
        }
```
**避免**: handler 重复触发导致混乱

---

### 模块2: Cognitive Loop (决策层)

#### 优化原则
```
tick = 30s

检查事件/Context Cache
        ↓
  如果需要 reasoning → 调用 LLM
  否则 → rules 处理
```

**避免**: 一天 10000+ LLM 调用

#### 结构
```python
class CognitionLoop:
    def tick(self):
        # 1. 读取 Context Cache (不是 Vector Search!)
        context = self.context_cache.read()
        
        # 2. 检查是否需要 reasoning
        if self.needs_deep_reasoning(context):
            # 低频: 调用 LLM
            plan = self.llm_plan(context)
            self.emit(EventTypes.COGNITION_PLAN, plan)
        else:
            # 高频: 规则处理
            self.rule_based_action(context)
    
    def needs_deep_reasoning(self, context):
        # 规则判断:
        # - 用户发送了新消息
        # - 任务失败
        # - 系统状态异常
        # - 长时间没有规划
        return context.has_trigger_event()
```

#### OODA 优化
```
Observe  → 读取 Context Cache (本地)
Plan     → LLM (低频触发)
Act      → 发布事件到 Bus
Reflect  → 事件触发 (不是每tick都做)
```

#### IDLE 状态优化
**如果没有事件、没有任务、没有目标 → skip tick**

```python
class CognitionLoop:
    def tick(self):
        # 1. 读取 Context Cache
        context = self.context_cache.read()
        
        # 2. 检查是否需要处理 (IDLE检测)
        if self.is_idle(context):
            logger.debug("[COGNITION] IDLE state, skipping tick")
            return
        
        # 3. 检查是否需要 reasoning
        if self.needs_deep_reasoning(context):
            plan = self.llm_plan(context)
            self.emit(EventTypes.COGNITION_PLAN, plan)
        else:
            self.rule_based_action(context)
    
    def is_idle(self, context):
        """检测是否处于IDLE状态"""
        return (
            not context.has_new_events() and      # 无新事件
            not context.has_active_tasks() and    # 无活跃任务
            not context.has_current_goal() and    # 无当前目标
            time.since_last_activity() > 300      # 5分钟无活动
        )
```
**避免**: 空转消耗CPU

---

### 模块3: Task Planner (规划层)

#### 核心功能
**LLM 不直接执行，而是规划任务列表**:

```
Goal
  ↓
LLM Planning
  ↓
Task List (分解为可执行步骤)
  ↓
Task Queue
  ↓
Workers (逐步执行)
```

#### 示例
```python
# 输入
goal = "完成v30架构升级"

# LLM Planning 输出
tasks = [
    {"step": 1, "action": "创建Event Bus基础模块", "estimated_time": "2h"},
    {"step": 2, "action": "实现核心Listener", "estimated_time": "2h"},
    {"step": 3, "action": "添加Rate Limiter", "estimated_time": "1h"},
    # ...
]

# 加入队列，逐步执行
for task in tasks:
    task_queue.add(task)
```

#### Plan Cache (规划缓存)
**避免**: 每个任务都重新规划

```python
class TaskPlanner:
    def __init__(self):
        self.plan_cache = {}  # goal_hash -> {plan, timestamp, ttl}
        self.cache_ttl = 3600  # 1小时缓存
    
    def plan(self, goal):
        # 检查缓存
        goal_hash = hash(goal)
        if goal_hash in self.plan_cache:
            cached = self.plan_cache[goal_hash]
            if time.now() - cached['timestamp'] < self.cache_ttl:
                logger.debug(f"Using cached plan for: {goal[:50]}...")
                return cached['plan']
        
        # 重新规划
        plan = self.llm_plan(goal)
        
        # 存入缓存
        self.plan_cache[goal_hash] = {
            'plan': plan,
            'timestamp': time.now(),
            'goal': goal
        }
        
        return plan
    
    def invalidate_cache(self, goal_pattern=None):
        """使缓存失效 (当环境变化时)"""
        if goal_pattern:
            # 使匹配pattern的缓存失效
            for key, val in list(self.plan_cache.items()):
                if goal_pattern in val['goal']:
                    del self.plan_cache[key]
        else:
            # 清空所有缓存
            self.plan_cache.clear()
```
**好处**: 相同/相似目标复用规划，减少 LLM 调用

---

### 模块4: Memory Index (长期经验)

#### 分离存储结构
```
memory/
├── episodic.db          # 时间线记忆
├── semantic.db          # 知识记忆  
├── embeddings.faiss     # 向量索引
└── metadata.sqlite      # 结构化元数据
```

**原因**: episodic (timeline) 和 semantic (knowledge) 检索方式不同，混在一起质量下降。

#### Episodic Memory (事件)
```python
{
    "id": "uuid",
    "timestamp": "2026-04-06T12:00:00",
    "type": "conversation",
    "content": "朋朋批准了v30设计",
    "embedding": [0.1, 0.2, ...],
    "importance": 0.85,  # 计算得出
    "tags": ["v30", "设计", "批准"]
}
```

#### Semantic Memory (知识)
```python
{
    "id": "uuid",
    "concept": "Event Bus",
    "definition": "事件驱动架构的核心组件",
    "embedding": [0.3, 0.4, ...],
    "importance": 0.9,
    "associations": ["listener", "publisher"]
}
```

#### 重要性评分
```python
def calculate_importance(memory):
    """
    importance = f(
        recency,           # 越新越重要
        frequency,         # 访问越多越重要  
        emotional_weight,  # 情绪权重
        task_relevance     # 任务相关性
    )
    """
    score = (
        recency_score * 0.3 +
        frequency_score * 0.2 +
        emotional_score * 0.2 +
        relevance_score * 0.3
    )
    return min(1.0, max(0.0, score))

# 低分记忆自动衰减
def cleanup_low_importance():
    threshold = 0.2
    old_memories = db.query("SELECT * WHERE importance < ?", threshold)
    for m in old_memories:
        if m.age > timedelta(days=30):
            archive_or_delete(m)
```

**避免**: 三个月后数据库变成垃圾堆

#### Memory Consolidation (记忆整合)
**人类大脑机制**: 定期把零碎记忆合成总结

```
20条 interaction
      ↓
  1条 summary memory
```

**实现**:
```python
class MemoryConsolidator:
    def consolidate(self, time_window=timedelta(hours=24)):
        """
        定期整合记忆:
        1. 获取时间窗口内的episodic记忆
        2. 按主题聚类
        3. 生成summary
        4. 存储到semantic memory
        5. 标记原始记忆为已整合
        """
        
        # 获取待整合记忆
        memories = self.episodic_db.query(
            f"SELECT * WHERE timestamp > {now - time_window} AND consolidated = false"
        )
        
        if len(memories) < 10:
            return  # 太少不整合
        
        # 按主题聚类
        clusters = self.cluster_by_topic(memories)
        
        for cluster in clusters:
            if len(cluster) >= 5:  # 至少5条才整合
                # 生成summary
                summary = self.llm_summarize(cluster)
                
                # 存储到semantic memory
                self.semantic_db.store({
                    "type": "consolidated_memory",
                    "content": summary,
                    "source_memories": [m.id for m in cluster],
                    "timestamp": now,
                    "importance": self.calculate_importance(cluster)
                })
                
                # 标记已整合
                for m in cluster:
                    self.episodic_db.update(m.id, consolidated=True)
                
                logger.info(f"Consolidated {len(cluster)} memories into 1 summary")

# 定时触发 (每天一次)
def run_consolidation():
    consolidator = MemoryConsolidator()
    consolidator.consolidate(time_window=timedelta(hours=24))
```

**好处**:
- 减少episodic记忆数量
- 提升检索质量 (summary比零散记录更有用)
- 模仿人类记忆机制

---

### 模块5: Context Cache (意识缓存)

#### 核心功能
减少 Vector Search 次数:
```
认知循环优先读取 Context Cache
而不是每次都查 Memory Index
```

**避免**: 
```
vector search
vector search  
vector search  ← CPU抱怨人生
```

#### 结构
```python
context/
├── current_goal.json      # 当前目标
├── active_tasks.json      # 活跃任务
└── recent_events.json     # 最近事件 (最近1小时)
```

#### 工作流程
```python
class ContextCache:
    def read(self):
        # O(1) 读取，无需vector search
        return {
            "goal": self.load("current_goal"),
            "tasks": self.load("active_tasks"),
            "events": self.load("recent_events")  # 最近10个
        }
    
    def update(self, event):
        # 事件驱动更新
        if event.type == "task.started":
            self.active_tasks.add(event.task)
        elif event.type == "task.finished":
            self.active_tasks.remove(event.task)
```

---

### 模块6: Structured Logging (结构化日志)

#### 核心设计
**可追踪的行为链**: 每个操作都有唯一ID，跨模块可追踪

```python
class StructuredLog:
    def __init__(self):
        self.trace_id = generate_uuid()  # 整个请求链的ID
        self.event_id = None             # 当前事件ID
        self.task_id = None              # 当前任务ID
        self.parent_id = None            # 父事件/任务ID
        
    def log(self, level, message, **context):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "trace_id": self.trace_id,
            "event_id": self.event_id,
            "task_id": self.task_id,
            "parent_id": self.parent_id,
            "context": context
        }
        self.write(entry)
```

#### 示例追踪链
```
[trace:abc123] Event: message.received [event:evt001]
[trace:abc123]   ↓ Cognition Listener [event:evt002 parent:evt001]
[trace:abc123]     ↓ LLM Plan [task:task001 parent:evt002]
[trace:abc123]       ↓ Task Planner [event:evt003 parent:task001]
[trace:abc123]         ↓ Task Queue [task:task002 parent:task001]
[trace:abc123]           ↓ Worker Execute [task:task002]
[trace:abc123]             ↓ Task Finished [event:evt004 parent:task002]
```

#### 好处
- **可追踪**: 一条命令从收到到执行完成的全链路
- **可调试**: 快速定位问题发生在哪个环节
- **可监控**: 统计每个环节的处理时间

---

### 模块7: Worker Crash Recovery (任务故障恢复)

#### 问题
Worker 崩溃后任务消失，系统永久卡住：
```
task.started
    ↓
worker crash
    ↓
(task 永远消失)
```

#### 解决方案: Task Watchdog
**状态机 + 心跳监控**:

```python
class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    TIMEOUT = "timeout"

class Task:
    def __init__(self, action, params):
        self.id = generate_uuid()
        self.status = TaskStatus.PENDING
        self.action = action
        self.params = params
        self.retry_count = 0
        self.max_retries = 3
        self.timeout = 300  # 5分钟超时
        self.started_at = None
        self.last_heartbeat = None
        self.worker_id = None

class TaskWatchdog:
    def __init__(self, check_interval=60):
        self.check_interval = check_interval  # 60秒检查一次
    
    def check_running_tasks(self):
        """检查running状态的任务"""
        running_tasks = db.query("SELECT * WHERE status = 'running'")
        
        for task in running_tasks:
            # 检查心跳
            if task.last_heartbeat:
                elapsed = time.now() - task.last_heartbeat
                
                if elapsed > 300:  # 5分钟无心跳
                    logger.warning(f"Task {task.id} dead (no heartbeat for {elapsed}s)")
                    self.handle_dead_task(task)
            else:
                # 没有心跳记录，检查开始时间
                elapsed = time.now() - task.started_at
                if elapsed > task.timeout:
                    logger.warning(f"Task {task.id} timeout ({elapsed}s > {task.timeout}s)")
                    self.handle_dead_task(task)
    
    def handle_dead_task(self, task):
        """处理死亡任务"""
        if task.retry_count < task.max_retries:
            # 重试
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            task.worker_id = None
            task.last_heartbeat = None
            
            logger.info(f"Task {task.id} retry {task.retry_count}/{task.max_retries}")
            
            # 发布重试事件
            event_bus.publish(EventTypes.TASK_RETRY, {
                "task_id": task.id,
                "retry_count": task.retry_count
            })
        else:
            # 标记失败
            task.status = TaskStatus.FAILED
            task.failed_at = time.now()
            task.failure_reason = "timeout_or_crash"
            
            logger.error(f"Task {task.id} failed after {task.max_retries} retries")
            
            # 发布失败事件
            event_bus.publish(EventTypes.TASK_FAILED, {
                "task_id": task.id,
                "reason": "max_retries_exceeded"
            })

# Worker 定期发送心跳
class Worker:
    def run_task(self, task):
        task.status = TaskStatus.RUNNING
        task.started_at = time.now()
        task.worker_id = self.worker_id
        
        # 启动心跳线程
        heartbeat_thread = threading.Thread(target=self._send_heartbeat, args=(task,))
        heartbeat_thread.start()
        
        try:
            # 执行任务
            result = self.execute(task)
            task.status = TaskStatus.FINISHED
            task.finished_at = time.now()
            
            event_bus.publish(EventTypes.TASK_FINISHED, {
                "task_id": task.id,
                "result": result
            })
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            
            event_bus.publish(EventTypes.TASK_FAILED, {
                "task_id": task.id,
                "error": str(e)
            })
        finally:
            self._stop_heartbeat = True
    
    def _send_heartbeat(self, task):
        """每30秒发送一次心跳"""
        while not self._stop_heartbeat:
            task.last_heartbeat = time.now()
            db.update(task)
            time.sleep(30)
```

**好处**:
- Worker 崩溃 → 检测到无心跳 → 自动重试
- 任务超时 → 自动标记失败或重试
- 系统不会卡住

---

### 模块8: Event Bus Persistence (事件持久化)

#### 问题
内存队列，服务器重启 = 全丢：
```
Server Restart
    ↓
Event Queue = []  (全丢)
    ↓
任务链断裂
```

#### 解决方案: 双队列设计
```
Event Bus
 ├── memory queue  (快速处理)
 └── durable queue (持久化备份)
      ↓
   SQLite / Redis / File
```

**简单实现 (SQLite)**:
```python
class PersistentEventBus:
    def __init__(self, db_path="events.db"):
        self.memory_queue = Queue()
        self.db = sqlite3.connect(db_path)
        self._init_db()
    
    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                data TEXT NOT NULL,
                timestamp REAL NOT NULL,
                processed BOOLEAN DEFAULT FALSE,
                retry_count INTEGER DEFAULT 0
            )
        """)
        self.db.commit()
    
    def publish(self, event):
        # 1. 存入持久化队列
        self.db.execute(
            "INSERT INTO events (id, type, data, timestamp) VALUES (?, ?, ?, ?)",
            (event.id, event.type, json.dumps(event.data), time.time())
        )
        self.db.commit()
        
        # 2. 放入内存队列 (快速处理)
        self.memory_queue.put(event)
    
    def process_events(self):
        """启动时恢复未处理事件"""
        # 获取未处理事件
        cursor = self.db.execute(
            "SELECT * FROM events WHERE processed = FALSE ORDER BY timestamp"
        )
        
        for row in cursor.fetchall():
            event = Event(
                id=row[0],
                type=row[1],
                data=json.loads(row[2]),
                timestamp=row[3]
            )
            
            # 检查是否过期
            if event.is_expired():
                self._mark_processed(event.id)
                continue
            
            # 放回内存队列
            self.memory_queue.put(event)
            logger.info(f"Restored event {event.id} from persistence")
    
    def mark_processed(self, event_id):
        """标记事件已处理"""
        self.db.execute(
            "UPDATE events SET processed = TRUE WHERE id = ?",
            (event_id,)
        )
        self.db.commit()
    
    def cleanup_old_events(self, days=7):
        """清理旧事件"""
        cutoff = time.time() - (days * 86400)
        self.db.execute(
            "DELETE FROM events WHERE processed = TRUE AND timestamp < ?",
            (cutoff,)
        )
        self.db.commit()
```

**好处**:
- 服务器重启 → 自动恢复未处理事件
- 任务链不会断裂
- 简单可靠 (SQLite 零依赖)

---

### 模块9: Planner Output Schema (规划输出标准化)

#### 问题
LLM 输出不稳定，Worker 无法执行：
```
LLM: "Step1: maybe create module"
      ↓
Worker: ??? (无法解析)
```

#### 解决方案: 严格 Schema
```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class TaskDefinition(BaseModel):
    """任务定义 Schema"""
    id: str = Field(default_factory=generate_uuid)
    action: str = Field(..., description="动作类型: create_file, run_command, etc")
    params: Dict[str, Any] = Field(..., description="动作参数")
    description: str = Field(..., description="人类可读描述")
    
    # 执行控制
    retry: int = Field(default=3, ge=0, le=5, description="重试次数")
    timeout: int = Field(default=120, ge=10, le=3600, description="超时秒数")
    
    # 依赖
    depends_on: Optional[List[str]] = Field(default=None, description="依赖的任务ID")
    
    # 回调
    on_success: Optional[str] = Field(default=None, description="成功后的下一个任务")
    on_failure: Optional[str] = Field(default=None, description="失败后的处理")

class PlanOutput(BaseModel):
    """规划输出 Schema"""
    goal: str = Field(..., description="原始目标")
    tasks: List[TaskDefinition] = Field(..., description="任务列表")
    estimated_time: int = Field(..., description="预计总时间(分钟)")
    
    class Config:
        schema_extra = {
            "example": {
                "goal": "完成v30架构升级",
                "tasks": [
                    {
                        "id": "task_001",
                        "action": "create_file",
                        "params": {
                            "path": "agent/bus/event_bus.py",
                            "content": "# Event Bus implementation"
                        },
                        "description": "创建Event Bus基础模块",
                        "retry": 3,
                        "timeout": 120
                    },
                    {
                        "id": "task_002", 
                        "action": "run_command",
                        "params": {
                            "command": "python3 -m pytest tests/",
                            "cwd": "agent/bus"
                        },
                        "description": "运行测试",
                        "retry": 2,
                        "timeout": 300,
                        "depends_on": ["task_001"]
                    }
                ],
                "estimated_time": 30
            }
        }

# LLM 输出强制校验
class Planner:
    def plan(self, goal: str) -> PlanOutput:
        # 调用 LLM
        raw_output = self.llm.generate(
            prompt=self.build_prompt(goal),
            # 强制 JSON 输出
            response_format={"type": "json_object"}
        )
        
        # 解析并校验
        try:
            data = json.loads(raw_output)
            plan = PlanOutput(**data)  # Pydantic 校验
            return plan
        except ValidationError as e:
            logger.error(f"LLM output validation failed: {e}")
            # 重试或返回错误
            raise PlanValidationError(f"Invalid plan format: {e}")
```

**好处**:
- LLM 输出严格标准化
- Worker 可稳定执行
- 类型安全，错误可追踪

---

### 模块10: Memory Debounce (记忆批量写入)

#### 问题
高频事件导致 Vector Embedding 烧钱：
```
用户聊天: 10秒50条
    ↓
50 次 embedding
    ↓
API 账单爆炸 💸
```

#### 解决方案: 批量写入缓冲区
```python
class MemoryWriteBuffer:
    def __init__(self, flush_interval=30, max_batch_size=10):
        self.buffer = []
        self.flush_interval = flush_interval  # 30秒刷新
        self.max_batch_size = max_batch_size  # 最多10条
        self.last_flush = time.time()
    
    def add(self, memory_item):
        """添加记忆到缓冲区"""
        self.buffer.append(memory_item)
        
        # 检查是否需要刷新
        if len(self.buffer) >= self.max_batch_size:
            self.flush()
        elif time.time() - self.last_flush > self.flush_interval:
            self.flush()
    
    def flush(self):
        """批量写入记忆"""
        if not self.buffer:
            return
        
        logger.info(f"Flushing {len(self.buffer)} memories to index")
        
        # 1. 批量生成 embeddings (一次API调用)
        texts = [m.content for m in self.buffer]
        embeddings = self.embedding_model.encode(texts, batch_size=len(texts))
        
        # 2. 批量写入数据库
        for i, memory in enumerate(self.buffer):
            memory.embedding = embeddings[i]
            self.memory_db.store(memory)
        
        # 3. 清空缓冲区
        self.buffer = []
        self.last_flush = time.time()
        
        logger.info(f"Batch write complete, cost: {len(texts)} embeddings")
    
    def force_flush(self):
        """强制刷新 (系统关闭前调用)"""
        self.flush()

# 使用示例
memory_buffer = MemoryWriteBuffer(flush_interval=30, max_batch_size=10)

# 高频事件触发
@listener(EventTypes.MESSAGE_RECEIVED)
def on_message(event):
    memory = {
        "type": "conversation",
        "content": event.data["message"],
        "timestamp": time.now(),
        "importance": calculate_importance(event)
    }
    
    # 放入缓冲区 (不是立即写入!)
    memory_buffer.add(memory)
```

**成本对比**:
| 方式 | 10条记忆成本 |
|------|-------------|
| 逐条写入 | 10 API 调用 |
| 批量写入 | 1 API 调用 (90% 节省) |

**好处**:
- API 成本降低 90%
- 减少网络开销
- 系统吞吐量提升

---

## 3. 数据流示例

### 场景: 朋朋发送消息
```
[1] Message Received
        ↓
[2] Event Bus: message.received
        ↓
    ┌───┴───┐
    ↓       ↓
Memory   Cognition
Listener  Listener
    ↓       ↓
存储到   检查Context
episodic  Cache
    ↓       ↓
    └───────┘
        ↓
[3] Cognition.needs_deep_reasoning?
    ↓
    是 → LLM Plan → 发布 cognition.plan
    ↓
[4] Task Planner Listener
    ↓
分解为Tasks → Task Queue
    ↓
[5] Workers 执行
    ↓
[6] 完成 → task.finished → Event Bus
    ↓
[7] 更新 Context Cache
```

---

## 4. 迁移计划 (优化版)

### Phase 1: Event Bus 核心 (2-3天)
- [ ] 创建 event_bus.py (Rate Limiter内置)
- [ ] 实现 Publisher / Listener 基类
- [ ] 创建 Context Cache
- [ ] 实现 Structured Logging (trace_id/event_id/task_id)
- [ ] 测试事件流转 + 防递归

### Phase 2: Cognition + Planner (2-3天)
- [ ] 实现 Cognition Loop (LLM低频触发 + IDLE状态)
- [ ] 实现 Task Planner (LLM规划 → Queue + Plan Cache)
- [ ] 测试决策 → 规划 → 执行流

### Phase 3: Memory Index (2-3天)
- [ ] 分离 episodic / semantic 存储
- [ ] 实现 importance scoring
- [ ] 实现 Memory Consolidation
- [ ] 迁移现有记忆
- [ ] 测试语义检索

### Phase 4: 集成 + 优化 (1-2天)
- [ ] 全系统联调
- [ ] 压力测试 (Event Storm防护)
- [ ] API调用成本测试
- [ ] 文档更新

**总计**: 7-11天

---

## 5. 防坑清单

| 坑 | 解决方案 |
|----|----------|
| Event Storm | Rate Limiter + cognition不监听memory.updated |
| 过期事件触发 | Event TTL (默认60s过期丢弃) |
| 重复事件 | Event Deduplication (5秒窗口去重) |
| LLM账单爆炸 | cognition.tick低频 + rules优先 + IDLE状态跳过 |
| 重复规划 | Plan Cache (1小时缓存) |
| CPU爆炸 | Context Cache避免频繁vector search |
| 数据库垃圾堆 | importance scoring + consolidation + 自动清理 |
| 任务混乱 | Task Planner分解 → Queue → Workers |
| 空转浪费 | IDLE状态检测，无事件时skip tick |
| 记忆碎片化 | Memory Consolidation (定期合成summary) |
| 无法追踪 | Structured Logging (trace_id/event_id/task_id) |
| Worker崩溃任务卡死 | Task Watchdog + 状态机 + 心跳监控 + 自动重试 |
| 重启丢事件 | Event Bus Persistence (SQLite双队列) |
| LLM输出不稳定 | Planner Output Schema (Pydantic强制校验) |
| Embedding烧钱 | Memory Debounce (30秒批量写入，90%成本节省) |

---

## 6. 批准

- [x] 设计文档 v3.0 完成 (整合15项核心优化)
  - Event Bus 三层防护 (Rate Limiter + TTL + Deduplication)
  - Cognitive Loop IDLE 状态
  - Memory Consolidation
  - Plan Cache
  - Structured Logging (trace_id / event_id / task_id)
  - **Worker Crash Recovery** (Task Watchdog + 心跳 + 自动重试)
  - **Event Bus Persistence** (SQLite双队列，重启不丢事件)
  - **Planner Output Schema** (Pydantic强制校验)
  - **Memory Debounce** (30秒批量写入，90%成本节省)
- [ ] 朋朋批准
- [ ] 开始 Phase 1: Event Bus 核心 + Persistence + Structured Logging

---

**注**: 这是一个**生产级 AI 操作系统架构**，具备完整的自我保护机制和性能优化。

**核心设计哲学**:
- Event Bus = 中央神经系统 (唯一调度中心)
- Cognition = 决策层 (不是调度器)
- 大量用规则，少量用 LLM
- 能缓存就缓存，能跳过就跳过
- 记忆要像人类大脑一样整合
- 所有行为可追踪 (trace_id)
- 任务要有故障恢复 (Watchdog)
- 事件要持久化 (重启不丢)
- 输出要严格校验 (Schema)
- 写入要批量 (Debounce)

**预期收益**:
- API 成本降低 90%+
- CPU 占用降低 50%+
- 响应延迟降低 90%+
- 系统稳定性达到生产级
