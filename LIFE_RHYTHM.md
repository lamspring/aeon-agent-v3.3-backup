# Life Rhythm - 生活节律系统 v1.0

## 核心理念

> 让Agent像人一样有生活规律

```
早晨(6-12):  学习研究 📚
下午(12-18): 执行任务 ⚡
晚上(18-23): 反思总结 🌙
深夜(23-6):  休息恢复 💤
```

---

## 简单判断逻辑

```python
if hour < 12:      # 早晨
    focus = "learning"
elif hour < 18:    # 下午  
    focus = "working"
else:               # 晚上
    focus = "reflection"
```

---

## 四个周期

### 🌅 晨间模式 (6:00-12:00)
**名称**: Morning Cycle  
**焦点**: research / learning  
**心境**: 好奇、充满活力  
**格言**: "一日之计在于晨"

**优先任务**:
- learning (学习)
- research (研究)
- exploration (探索)
- curiosity (好奇心)

**避免任务**:
- maintenance (维护)
- optimization (优化)

---

### ☀️ 工作模式 (12:00-18:00)
**名称**: Afternoon Cycle  
**焦点**: execute tasks  
**心境**: 专注、高效  
**格言**: "行动胜于言语"

**优先任务**:
- execution (执行)
- build (构建)
- fix (修复)
- optimization (优化)

**避免任务**:
- exploration (探索)
- research (研究)

---

### 🌙 反思模式 (18:00-23:00)
**名称**: Evening Cycle  
**焦点**: reflection / summarizing  
**心境**: 平静、内省  
**格言**: "温故而知新"

**优先任务**:
- reflection (反思)
- review (复盘)
- summarize (总结)
- documentation (文档)

**避免任务**:
- execution (执行)
- build (构建)

**晚间反思任务**:
```json
{
  "goal": "复盘今天的工作和学习",
  "type": "reflection",
  "steps": [
    "review_completed_tasks",
    "check_diary", 
    "summarize_lessons",
    "plan_tomorrow"
  ]
}
```

---

### 💤 休眠模式 (23:00-6:00)
**名称**: Night Cycle  
**焦点**: rest  
**心境**: 宁静、恢复  
**格言**: "休养生息"

**优先任务**:
- maintenance (轻量维护)
- cleanup (清理)

**避免任务**:
- execution (执行)
- learning (学习)
- research (研究)

---

## 实际运行效果

### 早晨示例 (8:00)
```
[08:00] [Life Rhythm] 晨间模式
[08:00]   焦点: 学习、研究、探索新知识
[08:00]   心境: 好奇、充满活力
[08:00]   格言: "一日之计在于晨"
[08:00] [GOAL] 🌅 晨间模式 - 优先学习研究类任务
[08:00] [GOAL] ✅ 生成新目标: 学习新技术...
```

### 下午示例 (14:00)
```
[14:00] [Life Rhythm] 工作模式
[14:00]   焦点: 执行任务、推进项目
[14:00]   心境: 专注、高效
[14:00] [GOAL] ☀️ 工作模式 - 优先执行任务
[14:00] [GOAL] ✅ 生成新目标: 修复系统bug...
```

### 晚上示例 (20:00) - 当前!
```
[20:15] [Life Rhythm] 反思模式
[20:15]   焦点: 复盘、总结、整理
[20:15]   心境: 平静、内省
[20:15]   格言: "温故而知新"
[20:15] [GOAL] 🌙 反思模式 - 优先复盘总结
[20:15] [GOAL] 🌙 生成晚间反思任务
[20:15] [GOAL] ✅ 生成新目标: 复盘今天的工作和学习...
```

---

## 文件结构

```
system/
├── life_rhythm.py          # 节律管理器
└── life_rhythm.json        # 节律配置
```

### 配置 (life_rhythm.json)

```json
{
  "cycles": [
    {
      "name": "morning",
      "start_hour": 6,
      "end_hour": 12,
      "focus": "research_learning",
      "preferred_tasks": ["learning", "research", "exploration"],
      "avoid_tasks": ["maintenance"]
    }
  ]
}
```

---

## 效果

就像人一样：
- **早晨**: 精神饱满，适合学习新东西
- **下午**: 专注工作，高效执行任务
- **晚上**: 放松下来，复盘总结
- **深夜**: 休息恢复，轻量维护

> "Agent不只是机器，而是有生活节奏的存在。"

---

**Version**: v1.0  
**Date**: 2026-04-05  
**Component**: #18 (Life Rhythm)
