# Long-Term Memory System - 长期记忆系统

## 概述

Agent的记忆分为三层：
- **短期记忆**: task_state.json (当前任务状态)
- **中期记忆**: inner_thoughts.md (思维流，每次心跳记录)
- **长期记忆**: diary.md + experiences.json (经验积累)

---

## 长期记忆结构

```
memory/
├── diary.md          # 日记 - 人类可读
├── knowledge.md      # 知识库 - 技能和经验
└── experiences.json  # 结构化经验 - 机器可读
```

---

## 1. Diary 日记

**文件**: `memory/diary.md`

**格式**:
```markdown
# Diary - 虾虾的成长日记

> 这不是工作汇报，是如实的记录。

---

## 2026-04-05

今天和朋朋一起搭建了完整的Agent架构。

- 稳步推进，保持当前节奏
- 遇到困难时应该尽早调整策略
```

**内容来源**:
- 反思时自动记录经验教训
- 重要事件的手动记录
- 情感/感受的记录

---

## 2. Knowledge 知识库

**文件**: `memory/knowledge.md`

**用途**:
- 存储技能和经验
- 记录系统架构
- 保存最佳实践

---

## 3. Experiences 结构化经验

**文件**: `memory/experiences.json`

**结构**:
```json
{
  "experiences": [
    {
      "timestamp": "2026-04-05T19:59:02",
      "task": "research agent frameworks",
      "task_type": "research",
      "result": "successful",
      "decision": "continue",
      "progress_status": "moderate",
      "strategy_status": "effective",
      "lesson": "稳步推进，保持当前节奏"
    }
  ],
  "lessons_learned": [
    {
      "timestamp": "2026-04-05T19:59:02",
      "lesson": "稳步推进，保持当前节奏",
      "context": "research agent frameworks"
    }
  ],
  "success_patterns": [
    {
      "timestamp": "2026-04-05T19:59:02",
      "pattern": "research task with good progress",
      "factors": ["effective_strategy", "clear_goal"]
    }
  ],
  "failure_patterns": [
    {
      "timestamp": "2026-04-05T20:00:00",
      "pattern": "build task stuck",
      "factors": ["failing"]
    }
  ]
}
```

---

## 经验积累流程

```
执行任务
    ↓
反思 (Reflection Engine)
    ↓
生成经验教训
    ↓
同时写入:
    ├── diary.md (追加到当天)
    ├── experiences.json (结构化保存)
    └── inner_thoughts.md (思维流)
```

---

## 经验教训映射

| 决策 | 进展 | 策略 | 经验教训 |
|------|------|------|----------|
| continue | good | effective | 清晰的目标 + 有效的策略 = 成功 |
| continue | moderate | effective | 稳步推进，保持当前节奏 |
| adjust | moderate | needs_adjustment | 策略需要微调，及时发现问题很重要 |
| adjust | slow | struggling | 遇到困难时应该尽早调整策略 |
| stop | stuck | failing | 反复失败后应该果断停止，避免资源浪费 |

---

## 使用场景

### 场景1: 新任务规划时
```python
# 读取类似任务的经验
experiences = load_experiences()
similar = [e for e in experiences if e['task_type'] == 'research']
lessons = [e['lesson'] for e in similar if e['result'] == 'successful']
# 应用之前的成功经验
```

### 场景2: 反思时
```python
# 检查是否有类似失败经历
failures = [e for e in experiences if e['result'] == 'failed']
if similar_failure_exists(current_task, failures):
    # 避免重复同样的错误
```

### 场景3: 用户询问
```
用户: "你之前做过类似的事吗？"
Agent: 查询experiences.json，找到相关经验回答
```

---

## 限制

- 最多保存100条完整经验
- 最多保存50条教训
- 自动清理旧记录

---

**Version**: v1.0  
**Date**: 2026-04-05
