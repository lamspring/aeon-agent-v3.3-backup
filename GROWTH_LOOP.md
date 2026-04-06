# Growth Loop 成长循环系统 v13.0

## 核心理念

> 每次心跳都是一次小循环，Agent像生物一样持续成长

```
Perception（感知）
      ↓
Goal Generation（目标生成）
      ↓
Planning（规划）
      ↓
Action（执行）
      ↓
Reflection（反思）
      ↓
Memory Update（记忆更新）
      ↓
Heartbeat Sleep（休眠）
```

---

## 7步成长循环

### [1/7] Perception 感知
**文件**: `system/perception.py`

感知当前系统状态：
- **System State**: Gate状态、系统健康
- **Task State**: pending/running/finished任务数
- **Resource State**: API调用次数、磁盘使用
- **Time Context**: 时间、时段

**输出示例**:
```
📋 It's evening, have 3 tasks pending, autonomy enabled
```

---

### [2/7] Gate Check 门控检查
检查是否允许自主执行
- ✅ Open: 继续
- ❌ Closed: 仅响应用户

---

### [3/7] Goal Generation 目标生成
**文件**: `system/goal_generator.py`  
**配置**: `system/daily_goals.json`

**触发条件**:
- 没有运行中的任务
- 没有待处理任务
- 满足最小间隔（默认30分钟）

**日常目标池**:
```json
{
  "goals": [
    {
      "id": "learn_new",
      "text": "learn something new",
      "category": "learning",
      "priority": 5,
      "weight": 0.3
    },
    {
      "id": "improve_stability",
      "text": "improve system stability",
      "category": "maintenance",
      "priority": 4,
      "weight": 0.25
    }
  ]
}
```

**目标类别**:
| 类别 | 步骤 |
|------|------|
| learning | find_resources → study_materials → take_notes → summarize |
| maintenance | identify_issues → fix_problems → test_fixes → document |
| reflection | review_history → identify_patterns → suggest_improvements |
| exploration | research_topic → try_examples → document_findings |
| optimization | measure_performance → identify_bottlenecks → implement_fixes → verify |

**加权随机选择**:
```
learn_new: 30% 权重
improve_stability: 25% 权重
review_work: 20% 权重
explore_tools: 15% 权重
optimize_performance: 10% 权重
```

---

### [4/7] Planning 规划
从目标生成具体任务计划：
- 任务分解为steps
- 确定优先级
- 加入任务队列

---

### [5/7] Action 执行
**文件**: `tasks/worker.py`

- 一次只执行一步
- 更新进度
- 检查任务完成

---

### [6/7] Reflection 反思
**文件**: `system/reflection_engine.py`

三个核心问题：
1. 任务进展是否正常？
2. 当前策略是否有效？
3. 是否需要改变任务？

**决策**: continue / adjust / stop

**可能产生子任务**（回到Task Queue）

---

### [7/7] Memory Update 记忆更新
更新三层记忆系统：
- **Short-term**: task_state.json
- **Thought Stream**: inner_thoughts.md
- **Long-term**: knowledge.md, research.md

---

## 自我驱动流程

```
空闲状态 (没有任务)
      ↓
Perception: 感知到空闲
      ↓
Goal Generation: 从日常目标池选择
      ↓
Planning: 生成具体任务
      ↓
Action: 开始执行
      ↓
Reflection: 评估执行
      ↓
(可能产生子任务) → 回到Task Queue
      ↓
Memory: 记录经验
      ↓
SLEEP → 下次心跳继续
```

---

## 日常目标系统

### 配置
文件: `system/daily_goals.json`

**目标结构**:
```json
{
  "id": "learn_new",
  "text": "learn something new",
  "category": "learning",
  "priority": 5,
  "weight": 0.3,
  "conditions": {
    "min_idle_time": "1h",
    "max_per_day": 1
  }
}
```

**条件控制**:
- `min_idle_time`: 最小空闲时间
- `max_per_day`: 每日最大次数
- `when`: 触发时机 (after_error等)
- `min_completed_tasks`: 最小完成任务数

**生成规则**:
```json
{
  "no_goal_if_running": true,      // 有任务时不生成
  "no_goal_if_pending": true,      // pending不为空时不生成
  "min_interval_between_goals": "30m"  // 最小间隔30分钟
}
```

---

## 运行示例

```
[19:44:40] [HEARTBEAT] Growth Loop v13.0
[19:44:40] [1/7] Perception - 感知当前状态...
[19:44:40]   📋 It's evening, have 0 tasks pending, autonomy enabled
[19:44:40] [2/7] Gate Check... ✅ Open
[19:44:40] [3/7] Goal Generation - 目标生成...
[19:44:40] [GOAL] 没有活跃任务，从日常目标生成...
[19:44:40] [GOAL] ✅ 生成新目标: learn something new
[19:44:40] [GOAL] 类型: learning, 优先级: 5
[19:44:40] [4/7] Planning - 规划...
[19:44:40] [PLAN] 步骤: ['find_resources', 'study_materials', 'take_notes', 'summarize']
[19:44:40] [5/7] Action - 执行...
[19:44:40] [ACTION] ✅ Step 1 completed
[19:44:40] [6/7] Reflection - 反思... (跳过)
[19:44:40] [7/7] Memory Update - 记忆更新...
[19:44:40] [HEARTBEAT] Complete → Sleep 💤
```

---

## 与之前架构的区别

| v12.0 | v13.0 Growth Loop |
|-------|-------------------|
| 被动等待任务 | 主动生成目标 |
| 11个组件 | 13个组件 (+Perception, +Goal Generation) |
| Task Queue驱动 | Growth Loop驱动 |
| 需要外部触发 | 自我驱动 |

---

## 文件清单

```
system/
├── perception.py            ⭐ NEW - 感知模块
├── goal_generator.py        ⭐ NEW - 目标生成器
├── daily_goals.json         ⭐ NEW - 日常目标配置
└── ... (其他组件)

heartbeat.py                 ✅ 更新为成长循环
```

---

**Version**: v13.0  
**Name**: Growth Loop Edition  
**Date**: 2026-04-05  
**Core**: 自我驱动、持续成长
