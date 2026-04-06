# Task Tree 任务树系统

## 核心理念

```
任务队列
    ↓
执行任务 (Executor [8/10])
    ↓
反思结果 (Reflection Engine [9/10])
    ↓
产生新任务 (子任务)
    ↓
加入队列
```

形成**任务树**结构，父任务可以产生子任务。

## 任务树结构

### 字段定义

```json
{
  "task_id": "task_20260405_123456",
  "type": "research",
  "goal": "research ai agents",
  
  // 任务树字段
  "parent_id": null,        // 父任务ID，null表示根任务
  "depth": 0,               // 任务深度（层级）
  "children": [             // 子任务ID列表
    "subtask_001",
    "subtask_002"
  ],
  
  // 常规字段
  "steps": ["step1", "step2", "step3", "step4"],
  "priority": 5,
  "created": "2026-04-05T12:00:00"
}
```

### 层级关系

```
Depth 0: 根任务 (parent_id = null)
    ↓
Depth 1: 子任务 (parent_id = 根任务ID)
    ↓
Depth 2: 孙任务 (parent_id = 子任务ID)
    ↓
Depth 3: 曾孙任务 (max_depth = 3)
```

## 产生子任务

### 自动产生

Reflection Engine在以下情况自动产生子任务：

1. **决策为 adjust 时**
   - 任务需要调整策略
   - 产生分析子任务找出原因

2. **复杂任务完成一步时**
   - 如 research 类型任务
   - 产生验证子任务确认结果

### API

```python
from tasks.queue import TaskQueue

queue = TaskQueue()

# 产生子任务
subtask = queue.spawn_subtask(
    parent_task=current_task,
    subtask_goal="search papers",
    subtask_type="research"
)

# 返回子任务对象
{
  "task_id": "subtask_20260405_123456_task_001",
  "parent_id": "task_001",
  "depth": 1,
  "goal": "search papers"
}
```

### 深度限制

配置: `system/task_tree.json`

```json
{
  "max_depth": 3,  // 最大深度3层
  "can_spawn_subtasks": true
}
```

超过深度限制时，`spawn_subtask()` 返回 `None`。

## 示例：研究AI Agents

### 树结构

```
research ai agents [Depth 0]
├── search papers [Depth 1]
│   ├── search arxiv papers [Depth 2]
│   └── search google scholar [Depth 2]
├── compare frameworks [Depth 1]
└── write summary [Depth 1]
```

### 创建代码

```python
# 创建根任务
root = queue.add_task({
    'type': 'research',
    'goal': 'research ai agents',
    'priority': 5
})

# 创建第一层子任务
child1 = queue.spawn_subtask(root, 'search papers', 'research')
child2 = queue.spawn_subtask(root, 'compare frameworks', 'research')
child3 = queue.spawn_subtask(root, 'write summary', 'research')

# 创建第二层子任务
grandchild1 = queue.spawn_subtask(child1, 'search arxiv papers', 'search')
grandchild2 = queue.spawn_subtask(child1, 'search google scholar', 'search')
```

## 可视化

### 命令

```bash
cd /root/.openclaw/workspace/agent
python3 tools/visualize_task_tree.py
```

### 输出示例

```
============================================================
🌳 Task Tree Visualization
============================================================

Tree 1:
└── ⏳ research ai agents
    ├── ⏳ search papers
    │   ├── ⏳ search arxiv papers
    │   └── ⏳ search google scholar
    ├── ⏳ compare frameworks
    └── ⏳ write summary

============================================================
📊 Statistics:
  Pending:  6
  Running:  0
  Finished: 11
  Max Depth: 2
============================================================
```

### 状态图标

| 图标 | 状态 |
|------|------|
| ⏳ | pending (待处理) |
| ▶️ | running (执行中) |
| ✅ | done (已完成) |
| ❌ | error (错误) |
| ⚪ | 未知 |

## 与反思系统的结合

### 反馈循环

```
执行任务 (Executor)
    ↓
反思结果 (Reflection Engine)
    ↓ 发现需要更多工作
产生子任务 (spawn_subtask)
    ↓
加入队列 (pending.json)
    ↓
后续心跳执行子任务
```

### 实际场景

**场景1: 研究任务需要深入**
```
[REFLECTION] Decision: adjust
[REFLECTION] Action: 调整策略，重置到step 1 (已产生子任务: subtask_001)
[REFLECTION] Spawned 1 subtask(s):
  └─ subtask_001: 深入分析: research ai agents - 找出失败原因
```

**场景2: 验证任务结果**
```
[REFLECTION] Decision: continue
[REFLECTION] Action: 继续执行: 进入step 3 (已产生验证子任务)
[REFLECTION] Spawned 1 subtask(s):
  └─ subtask_002: 整理并验证: research ai agents 的研究结果
```

## 文件位置

```
system/
├── task_tree.json           # 任务树配置

tasks/
├── queue.py                 # 任务队列 (含spawn_subtask)
└── queue/
    ├── pending.json         # 待处理任务 (含parent_id/children/depth)
    ├── running.json
    └── finished.json

tools/
└── visualize_task_tree.py   # 可视化工具
```

## 限制

1. **最大深度**: 3层 (防止无限分裂)
2. **子任务数量**: 无硬性限制，但建议一个父任务不超过10个子任务
3. **循环检测**: 目前未实现，需人工避免循环引用

---
**Status**: 已实现并测试
**Version**: v1.0
**Date**: 2026-04-05
