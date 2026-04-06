# Weekly Reflection - 每周反思系统

## 设计

> 每周日晚上8点，自动总结本周

```
每周日 20:00
    ↓
收集本周数据
    ↓
调用AI模型
    ↓
生成周报
    ↓
保存到 memory/weekly_reflections.md
```

---

## 收集的数据

| 来源 | 内容 | 用途 |
|------|------|------|
| `logs/execution_log.txt` | 执行日志 | 了解本周做了什么 |
| `tasks/queue/finished.json` | 已完成任务 | 统计任务完成情况 |
| `memory/diary.md` | 日记 | 了解内心活动和思考 |
| `memory/long_term.md` | 长期记忆 | 参考历史经验 |

---

## 周报格式

```markdown
## 周报 YYYY-MM-DD

### 本周做了什么
- 完成的功能A
- 修复的问题B
- 新增的系统C

### 学到了什么
- 技术洞察1
- 设计原则2
- 经验教训3

### 遇到的问题
- 挑战A及解决方案
- 待优化的问题B

### 下周目标
- 🎯 目标1
- 🎯 目标2
```

---

## 执行方式

### 手动执行
```bash
cd /root/.openclaw/workspace/agent
python3 run_weekly_reflection.py
```

### cron设置 (每周日20:00)
```bash
# 编辑crontab
crontab -e

# 添加
0 20 * * 0 cd /root/.openclaw/workspace/agent && python3 run_weekly_reflection.py
```

---

## 文件结构

```
system/
├── weekly_reflection.json      # 配置
└── weekly_reflection.py        # 数据收集

memory/
└── weekly_reflections.md       # 周报存档

temp/
└── weekly_reflection_prompt.txt # 当前提示词

run_weekly_reflection.py        # 执行入口
```

---

## 本周示例

```markdown
## 周报 2026-04-05

### 本周做了什么
- 🏗️ 完成了Agent核心架构v10.0→v16.0
- 🛡️ 实现了三道安全保护系统
- 🌅 实现了生活节律系统
- ...

### 学到了什么
- 安全优先的设计理念
- 节律适应的重要性
- ...

### 下周目标
- 🎯 让每周反思自动运行
- 🎯 测试真实场景运行
```

---

**每周日晚上，回顾过去，规划未来。** 🗓️

**Version**: v1.0  
**Date**: 2026-04-05
