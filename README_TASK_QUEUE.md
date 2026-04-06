# Agent任务队列架构 v5.0

## 核心概念

**AI只负责生成任务，不直接执行。执行权交给心跳系统。**

## 4核心组件

```
┌─────────────────────────────────────────────────────────┐
│  1. Task Generator (AI)                                 │
│  Function: 思考并生成任务，写入pending队列               │
│  File: tasks/generator.py                               │
└─────────────────────────┬───────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  2. Task Queue (任务队列)                               │
│  Function: 管理pending/running/finished三个队列          │
│  File: tasks/queue.py                                   │
└─────────────────────────┬───────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  3. Task Worker (执行器)                                │
│  Function: 执行running任务的具体步骤                     │
│  File: tasks/worker.py                                  │
└─────────────────────────┬───────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  4. Task Storage (存储)                                 │
│  Files: tasks/queue/*.json                              │
│  - pending.json: 待处理任务队列                         │
│  - running.json: 正在执行的任务 (只有一个)              │
│  - finished.json: 已完成的任务历史                      │
└─────────────────────────────────────────────────────────┘
```

## 目录结构

```
agent/
├── heartbeat_queue.py        # 任务队列版心跳处理器
│
├── tasks/                    # 4组件目录
│   ├── generator.py          # Task Generator - AI生成任务
│   ├── queue.py              # Task Queue - 队列管理
│   ├── worker.py             # Task Worker - 任务执行
│   │
│   ├── queue/                # Task Storage - 队列存储
│   │   ├── pending.json      # 待处理任务
│   │   ├── running.json      # 正在执行
│   │   └── finished.json     # 已完成
│   │
│   └── task_history/         # 任务归档
│
└── ... (其他系统文件)
```

## 心跳流程 (任务队列版)

```
Heartbeat Trigger
      ↓
Gate Check
      ↓
Risk Check
      ↓
Queue Check (核心)
      ├── IF running exists → Continue Task
      └── IF running empty → Get from pending
      ↓
Worker Execute
      ↓
Memory Update
      ↓
Sleep
```

## 伪代码

```python
def heartbeat():
    gate_check()
    risk_check()
    
    queue = TaskQueue()
    worker = TaskWorker()
    
    if queue.has_running_task():
        # 有正在运行的任务，继续执行
        running = queue.get_running()
        result = worker.execute_step(running['step'])
        
        if result['finished']:
            queue.move_to_finished(running)
    else:
        # 没有运行任务，从pending取新任务
        task = queue.pop_next_task()
        
        if task:
            # 有pending任务，开始执行
            queue.set_running(task)
            worker.execute_step(0)
        else:
            # pending为空，AI生成新任务
            new_task = ai_think_and_generate()
            # 新任务写入pending，下次心跳执行
```

## 队列文件格式

### pending.json - 待处理队列
```json
[
  {
    "task_id": "task_001",
    "type": "research",
    "goal": "find new AI agent frameworks",
    "priority": 3,
    "created": "2026-04-05T16:00:00",
    "source": "curiosity"
  }
]
```

### running.json - 正在执行
```json
{
  "task_id": "task_001",
  "type": "research",
  "goal": "find new AI agent frameworks",
  "step": 2,
  "total_steps": 4,
  "progress": 0.5,
  "started_at": "2026-04-05T16:00:00"
}
```

### finished.json - 已完成
```json
[
  {
    "task_id": "task_001",
    "type": "research",
    "goal": "find new AI agent frameworks",
    "status": "done",
    "completed": "2026-04-05T17:30:00",
    "result": "success"
  }
]
```

## 任务类型

| Type | Steps | Description |
|------|-------|-------------|
| research | search, read, analyze, summarize | 研究型任务 |
| learn | find_resource, study, practice, review | 学习型任务 |
| build | design, code, test, deploy | 构建型任务 |
| explore | discover, experiment, evaluate, report | 探索型任务 |

## 执行流程示例

### 场景1: 有pending任务
```
心跳1:
  [QUEUE] No running task
  [QUEUE] Got task: task_001 (research)
  [WORKER] Executing step 1/4: search
  → running.json updated

心跳2:
  [QUEUE] Found running task
  [WORKER] Executing step 2/4: read
  → running.json updated

...(steps 3, 4)

心跳5:
  [QUEUE] Found running task
  [WORKER] ✅ Task finished
  → move to finished.json
  → running.json cleared
```

### 场景2: pending为空
```
心跳N:
  [QUEUE] No running task
  [QUEUE] No pending tasks
  [AI] Thinking about new tasks...
  [GENERATOR] Task created: task_XXX (build)
  → pending.json updated

心跳N+1:
  [QUEUE] No running task
  [QUEUE] Got task: task_XXX
  → start execution
```

## 关键设计

### 1. 分离生产与消费
- **Generator (AI)**: 只生产任务，不执行
- **Worker (系统)**: 只执行任务，不生成
- **Queue (中间层)**: 协调生产与消费

### 2. 单一任务执行
- running.json 只能有一个任务
- 保证系统专注，不堆积
- 任务完成后才取下一个

### 3. 优先级调度
- pending队列按priority排序
- 高优先级(5)优先执行
- 支持动态优先级调整

### 4. 自循环机制
- pending为空时，AI自动生成
- 系统可持续运行
- 不需要人工干预

## 使用方式

```bash
# 手动触发心跳
cd /root/.openclaw/workspace/agent
python3 heartbeat_queue.py

# 查看队列状态
cat tasks/queue/pending.json
cat tasks/queue/running.json
cat tasks/queue/finished.json

# AI生成新任务
python3 tasks/generator.py

# 查看任务历史
ls tasks/task_history/
```

## 架构演进

| Version | Architecture | Key Feature |
|---------|--------------|-------------|
| v4.0 | 8-step loop | State machine |
| **v5.0** | **Task Queue** | **Separation of concerns** |

---
**Version**: 5.0 (Task Queue)  
**Architecture**: Producer-Consumer Pattern  
**Last Updated**: 2026-04-05  
**Authorized By**: 朋朋
