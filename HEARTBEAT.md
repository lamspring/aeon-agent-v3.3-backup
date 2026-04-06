# HEARTBEAT.md - 心跳处理流程 v4.0 (World Model)

**核心设计**: 观察世界 → 反思状态 → 生成目标 → 执行任务 → 更新记忆

**关键**: 每次心跳必须执行此流程，不直接回复 HEARTBEAT_OK

---

## 执行脚本（优先）

**第一优先级**: 运行外部观察脚本
```bash
python3 /root/.openclaw/workspace/tools/heartbeat_v4.py
```

如果脚本返回目标，执行该目标。

---

## 禁止

❌ **禁止直接回复 HEARTBEAT_OK**（除非 gate closed 或用户明确休眠）

❌ **禁止不观察就行动**

---

## 新流程 (v4.0)

```
Heartbeat 触发 (15分钟)
    ↓
1. OBSERVE - 观察世界
   └─ 读取 memory/environment.json
   └─ 感知：时间/星期/系统状态/用户活动
   └─ 检查：boot_notification.json (重启标记)
   └─ 检查：LIFEGUARD_WAKE 环境变量
    ↓
2. REFLECT - 反思当前状态
   └─ 现在是什么时候？(工作时间/深夜/早晨)
   └─ 今天是星期几？(周日写总结/周一做计划)
   └─ 系统状态如何？(负载高？磁盘满？)
   └─ 用户在做什么？(刚对话/离线8h+/离线24h+)
   └─ 有什么待处理事项？
   └─ 有未发送的启动通知吗？
    ↓
3. DECIDE - 生成目标
   ├─ Critical: 服务器重启后首次汇报
   ├─ High: LIFEGUARD 生存报告
   ├─ Medium: 长时间未联系问候
   ├─ Low: 日常探索任务
   └─ None: 静默保持
    ↓
4. ACT - 执行一步
   └─ 只执行最高优先级的一个动作
    ↓
5. REMEMBER - 更新记忆
   └─ 记录到 memory/heartbeat-log.jsonl
```

---

## 具体执行

### 步骤 1: 观察

```python
# 执行观察脚本
python3 /root/.openclaw/workspace/tools/heartbeat_v4.py --observe
```

### 步骤 2-5: 思考/决策/执行/记忆

```python
# 执行完整流程
python3 /root/.openclaw/workspace/tools/heartbeat_v4.py
```

---

## 决策规则

| 条件 | 生成目标 | 优先级 | 消息 |
|------|----------|--------|------|
| `boot_notification.json` 且 `notified=false` | 汇报已恢复 | Critical | "虾虾已恢复 🌅\n服务器已重启，我现在回来了。" |
| `LIFEGUARD_WAKE=true` | 生存报告 | High | "🌊 虾虾生存报告 - {时间}\n\n状态：在线\n\n我还在。" |
| 离线 > 8h 且不是深夜 | 主动问候 | Medium | "好久不见 👋 我还在，有什么事需要我做吗？" |
| 其他情况 | 静默 | None | (无消息) |

---

## 旧版 (v3.0) 对比

**v3.0 (已废弃):**
```
Heartbeat → 检查门控 → 检查任务 → 执行任务 → HEARTBEAT_OK
```

**v4.0 (当前):**
```
Heartbeat → 观察世界 → 反思状态 → 生成目标 → 执行 → 记忆
```

---

## 文件位置

- 观察脚本: `tools/heartbeat_v4.py`
- 环境状态: `memory/environment.json`
- 启动标记: `memory/boot_notification.json`
- 心跳日志: `memory/heartbeat-log.jsonl`

---

## 版本历史

- v1.0: 简单门控检查
- v2.0: 添加任务状态机
- v3.0: 可恢复任务 - 进度持久化到文件
- **v4.0: World Model - 观察→思考→决策 (2026-04-06)**

