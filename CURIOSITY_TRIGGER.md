# Curiosity Trigger - 好奇心触发器 v1.0

## 概述

> 当系统空闲时，主动探索新事物。

Agent不只是被动等待任务，而是会自己找有趣的事情做。

---

## 触发条件

```
系统空闲时:
  ├── 没有运行中的任务
  ├── 没有待处理任务
  ├── 距离上次好奇心任务 > 5分钟
  └── 当日好奇心任务 < 5个
      ↓
触发好奇心！
```

---

## 好奇心任务池

### 5种好奇心类型

| 类型 | 权重 | 描述 | 步骤 |
|------|------|------|------|
| **search_new_tools** | 25% | 搜索并了解新工具 | search → read → notes → summarize |
| **review_old_tasks** | 20% | 复盘之前的任务 | list → analyze → identify → document |
| **optimize_code** | 20% | 优化现有代码 | scan → identify → implement → test |
| **explore_topic** | 20% | 探索感兴趣的话题 | choose → gather → study → write |
| **learn_technology** | 15% | 学习新技术 | choose → find → practice → document |

### 话题池 (explore_topic)
- AI agent architecture
- distributed systems
- programming language design
- cognitive science
- human-computer interaction

### 技术池 (learn_technology)
- Rust programming
- WebAssembly
- GraphQL
- Kubernetes
- Machine Learning basics

---

## 工作流程

```
[Goal Generation]
    ↓ 日常目标未生成
[Curiosity Trigger]
    ↓ 检查条件
[Weighted Random Selection]
    ↓ 选择任务
[Fill Template]
    ↓ 填充变量(topic/tech/query)
[Add to Queue]
    ↓ 加入任务队列
[Execute]
    ↓ 执行好奇心任务
[Reflection]
    ↓ 反思总结
[Memory]
    ↓ 记录经验
```

---

## 实际运行示例

```
[20:07:42] [GOAL] 没有活跃任务，从日常目标生成...
[20:07:42] [GOAL] ℹ️ 日常目标未生成，尝试好奇心触发...
[20:07:42] [CURIOSITY] 🔍 触发好奇心: 学习一项新技术: WebAssembly...
[20:07:42] [CURIOSITY] 类型: learn_technology
[20:07:42] [CURIOSITY] 已加入任务队列
[20:07:42] [PLAN] 当前任务: curiosity_20260405_200742...
[20:07:42] [PLAN] 进度: Step 1/4
[20:07:42] [ACTION] ✅ Step 1 completed
```

---

## 文件结构

```
system/
├── curiosity_trigger.py      # 触发器模块
├── curiosity_tasks.json      # 任务池配置
└── curiosity_state.json      # 状态记录
```

### 配置 (curiosity_tasks.json)

```json
{
  "enabled": true,
  "trigger_when_idle": true,
  "min_idle_time_before_trigger": "5m",
  "max_curiosity_tasks_per_day": 5,
  "curiosity_tasks": [...]
}
```

### 状态 (curiosity_state.json)

```json
{
  "today_count": 1,
  "last_trigger": "2026-04-05T20:07:42",
  "history": [...]
}
```

---

## 与日常目标系统的区别

| 特性 | 日常目标 | 好奇心触发 |
|------|----------|------------|
| **触发优先级** | 第一优先 | 第二优先 |
| **目标性质** | 计划性成长 | 探索性学习 |
| **内容来源** | 预定义目标池 | 随机选择话题/技术 |
| **执行频率** | 按需生成 | 最多5次/天 |
| **任务类型** | learning/maintenance | exploration |

---

## 扩展方式

添加新的好奇心任务：

```json
{
  "id": "read_paper",
  "text": "阅读一篇论文",
  "category": "learning",
  "weight": 0.1,
  "steps": ["find_paper", "read_abstract", "skim_content", "take_notes"],
  "paper_topics": ["AI", "systems", "languages"]
}
```

---

## 意义

好奇心触发器让Agent具备：**自主探索能力**

- 不只是被动响应
- 不只是按计划执行
- 而是**主动发现**有趣的事
- 像一个永远好奇的人，空闲时总想学点新东西

> "好奇心是知识的萌芽。" — 弗朗西斯·培根

---

**Version**: v1.0  
**Date**: 2026-04-05  
**Component**: #16 (Curiosity Trigger)
