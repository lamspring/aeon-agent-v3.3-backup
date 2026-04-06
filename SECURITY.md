# Security Layer - 安全层

## 概述

Agent权限很高，为防止失控，增加了两层安全保护：

1. **Rate Limiter** - 限流器 (防止疯狂调用API)
2. **Action Approval** - 操作审批 (高风险操作需确认)

---

## Rate Limiter 限流器

### 位置
文件: `system/rate_limiter.py`  
配置: `system/rate_limiter.json`

### 限制项

```json
{
  "api_calls_per_minute": 10,      // 每分钟最多10次API调用
  "api_calls_per_hour": 100,       // 每小时最多100次
  "tasks_created_per_heartbeat": 3, // 每次心跳最多3个新任务
  "subtasks_per_task": 5,          // 每个任务最多5个子任务
  "max_pending_tasks": 20,         // 最多20个待处理任务
  "max_tree_depth": 3              // 任务树最大深度3
}
```

### 集成点

在以下位置检查限流：

1. **TaskQueue.add_task()** - 创建任务时
2. **TaskQueue.spawn_subtask()** - 产生子任务时

### 示例输出

```
[RATE_LIMIT] Task creation blocked: Too many pending tasks: 20/20
[RATE_LIMIT] Subtask spawn blocked: Max tree depth reached: 3
```

---

## Action Approval 操作审批

### 位置
文件: `system/action_approval.py`  
配置: `system/action_approval.json`

### 风险分级

| 等级 | 操作 | 处理方式 |
|------|------|----------|
| **High** | exec, write, edit, delete, sessions_spawn, message_send | ❌ 拒绝，需手动审批 |
| **Medium** | web_search, kimi_search, browser_open | ⚠️ 允许，但记录日志 |
| **Low** | read, sessions_list, session_status 等 | ✅ 直接通过 |

### 升级机制

违规3次自动关闭Gate：
```json
{
  "escalation": {
    "after_violations": 3,
    "action": "gate_close"
  }
}
```

### 示例输出

```
exec: risk=high, allowed=False, approval=True
  → HIGH RISK: exec requires manual approval from 朋朋

read: risk=low, allowed=True, approval=False
  → Low risk action
```

---

## 安全流程

```
用户请求/心跳触发
        ↓
[1] Gate Check (OPEN?)
        ↓ YES
[2] Risk Check (工具/文件权限)
        ↓ PASS
[3] Rate Limiter (API/任务频率)
        ↓ PASS
[4] Action Approval (风险分级)
        ↓ APPROVED
    执行操作
```

---

## 日志记录

### Rate Limiter日志
文件: `system/rate_limiter_state.json`

```json
{
  "api_calls": ["2026-04-05T19:30:00", ...],
  "tasks_created": ["2026-04-05T19:25:00", ...],
  "last_reset": "2026-04-05T19:00:00"
}
```

### Action Approval日志
文件: `logs/action_approval_log.json`

```json
[
  {
    "timestamp": "2026-04-05T19:30:00",
    "action_type": "HIGH_RISK",
    "tool": "exec",
    "decision": "BLOCKED_PENDING",
    "reason": "Requires manual approval"
  }
]
```

---

## 手动控制

### 关闭Rate Limiter (危险)
```bash
# 编辑配置
nano system/rate_limiter.json
# 设置 "enabled": false
```

### 批准高风险操作
```python
from system.action_approval import ActionApproval
approval = ActionApproval()
approval.approve_action("approval_id", approved=True)
```

### 重置限流计数
```python
from system.rate_limiter import RateLimiter
limiter = RateLimiter()
limiter.reset()  # 危险操作！
```

---

## 测试命令

```bash
cd /root/.openclaw/workspace/agent

# 测试限流器
python3 system/rate_limiter.py

# 测试审批系统
python3 system/action_approval.py
```

---

**Version**: v1.0  
**Date**: 2026-04-05  
**Purpose**: 防止Agent失控，保护API资源
