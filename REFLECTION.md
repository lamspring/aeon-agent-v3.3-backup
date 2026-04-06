# Self-Reflection Engine 自我反思引擎

## 核心设计

反馈循环：
```
任务执行 (Executor)
    ↓
结果评估
    ↓
反思总结 (Reflection Engine)
    ↓
调整策略
    ↓
继续任务 (或终止)
```

## 架构位置

在心跳循环中的位置（第9步）：
```
[8/10] Executor         ← 执行一步任务
    ↓
[9/10] Reflection Engine ← 自我反思 ⭐
    ↓
[10/10] Memory Update    ← 记录记忆
```

## 三个核心问题

每次反思回答三个问题：

### 1. 任务进展是否正常？
评估标准：
- `good` (≥75%): 接近完成，进展顺利
- `moderate` (≥50%): 过半完成，稳步推进
- `slow` (≥25%): 进展较慢，需要关注
- `stuck` (<25%): 进展停滞，需要调整

### 2. 当前策略是否有效？
评估标准：
- `effective` (retry=0): 首次执行，策略有效
- `needs_adjustment` (retry=1): 首次重试，策略需微调
- `struggling` (retry=2): 多次重试，策略需要较大调整
- `failing` (retry≥3): 反复失败，策略完全无效

### 3. 是否需要改变任务？
决策选项：
- `continue`: 继续执行，进入下一步
- `adjust`: 调整策略，重置到step 1
- `stop`: 终止任务，移入finished队列

## 决策逻辑

```python
if retry_count >= 3:
    decision = "stop"      # 终止任务
elif retry_count >= 1:
    decision = "adjust"    # 调整策略
else:
    decision = "continue"  # 继续执行
```

## 触发时机

配置在 `system/reflection.json`：
```json
{
  "enabled": true,
  "trigger_on": {
    "task_complete": true,      # 任务完成时
    "task_stuck": true,         # 任务卡住时
    "every_n_heartbeats": 4     # 每4次心跳
  }
}
```

**注意**: 每4次心跳触发，避免变成"哲学大会"

## 反思日志格式

文件: `logs/reflection_log.md`

格式示例：
```markdown
---
time: 2026-04-05 19:05:25
task: test_stop_task

progress:
step 3 completed: step3 (step 3/4 (75%))

evaluation:
  【进展评估】moderate - 过半完成，稳步推进
  【策略评估】failing - 反复失败，策略完全无效
  【决策理由】已达最大重试次数，终止任务避免资源浪费

decision: stop
action: 终止任务: test stop decision
---
```

## 三种行动

### 1. continue - 继续任务
- 不改变任何东西
- step + 1
- 继续执行

### 2. adjust - 修改计划
- retry_count + 1
- 重置到 step 1
- 记录 last_adjustment
- 重试任务

### 3. stop - 任务终止
- 移动到 finished.json
- 标记 status = "error"
- 记录 result = "stopped_by_reflection"
- 清空 running.json
- 系统回到 idle 状态

## 实际运行示例

### 场景1: continue
```
[REFLECTION] Triggered: every_4_heartbeats
[REFLECTION] Evaluation: 
  【进展评估】good - 接近完成，进展顺利
  【策略评估】effective - 首次执行，策略有效
  【决策理由】进展正常，继续执行
[REFLECTION] Decision: continue
[REFLECTION] Action: 继续执行: 进入step 4
```

### 场景2: adjust
```
[REFLECTION] Triggered: every_4_heartbeats
[REFLECTION] Evaluation:
  【进展评估】moderate - 过半完成，稳步推进
  【策略评估】needs_adjustment - 首次重试，策略需微调
  【决策理由】策略需要调整，重新规划执行方式
[REFLECTION] Decision: adjust
[REFLECTION] Action: 调整策略: 重置到step 1，第2次尝试
[REFLECTION] Strategy adjusted
```

### 场景3: stop
```
[REFLECTION] Triggered: every_4_heartbeats
[REFLECTION] Evaluation:
  【进展评估】moderate - 过半完成，稳步推进
  【策略评估】failing - 反复失败，策略完全无效
  【决策理由】已达最大重试次数，终止任务避免资源浪费
[REFLECTION] Decision: stop
[REFLECTION] Action: 终止任务: test stop decision
[REFLECTION] Task stopped by reflection
[HEARTBEAT] Complete (stopped by reflection)
```

## Meta-Reasoning Prompt模板

给Agent的反思提示：
```
You are reviewing your own work.

Current task:
{task_goal}

Current step:
{step_name} (step {current_step}/{total_steps})

Recent results:
{step_result}

Evaluate:
1. progress quality - 进展质量评估
2. strategy effectiveness - 策略有效性评估  
3. whether to continue or adjust - 决策建议

Return decision:
continue / adjust / stop
```

## 文件位置

- **引擎**: `system/reflection_engine.py`
- **配置**: `system/reflection.json`
- **计数器**: `system/reflection_counter.json`
- **日志**: `logs/reflection_log.md`

---
**Status**: 已实现并测试  
**Version**: v1.0  
**Last Updated**: 2026-04-05
