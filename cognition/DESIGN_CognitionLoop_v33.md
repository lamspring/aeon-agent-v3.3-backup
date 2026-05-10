# CognitionLoop 模块化拆分设计 v1.0

> 目标：将 1997 行的 CognitionLoop 拆分为 5 个独立模块，通过 EventBus 通信
> 日期：2026-04-30
> 作者：虾虾

---

## 拆分原则

1. **单一职责**：每个模块只做一件事
2. **接口通信**：模块间通过 EventBus 发消息，不直接调用
3. **可替换**：任何模块可以被 mock 版本替换，不影响其他模块
4. **可测试**：每个模块可以独立单元测试

---

## 5 个模块

### 1. PerceptionModule（感知模块）

**职责：**
- 读取环境信息（时间、系统状态、用户输入）
- 检测外部事件（消息、文件变化、系统告警）
- 维护对话上下文（DialogueReader + ContextInjector）

**输入：**
- 当前 tick_count
- 上一次 tick 的 elapsed_time
- EventBus 队列状态
- 用户对话记录（来自 DialogueReader）
- 系统状态（来自 WorldInput）

**输出（发布到 EventBus）：**
```json
{
  "type": "perception.observation",
  "data": {
    "environment": {...},
    "dialogue_context": {...},
    "system_state": {...},
    "user_input_detected": true/false,
    "active_topics": [...]
  }
}
```

**关键方法：**
```python
class PerceptionModule:
    def observe(self, tick_count: int) -> Dict:
        """生成当前观察快照"""
    
    def get_user_context(self) -> Dict:
        """获取用户上下文（话题、情绪）"""
    
    def check_health(self) -> bool:
        """检查感知模块健康状态"""
```

---

### 2. PlanningModule（规划模块）

**职责：**
- 根据观察结果生成目标（GoalGenerator）
- 将目标分解为任务（Planner）
- 任务排序和优先级管理
- 任务状态跟踪

**输入（订阅 EventBus）：**
- `perception.observation` — 环境观察
- `goal.completed` — 目标完成事件
- `goal.failed` — 目标失败事件

**输出（发布到 EventBus）：**
```json
{
  "type": "plan.new_plan",
  "data": {
    "goal_id": "...",
    "goal_description": "...",
    "steps": [
      {"step_id": "...", "action": "...", "type": "tool/system", "params": {...}}
    ],
    "total_steps": 5,
    "estimated_duration": 300
  }
}
```

**关键方法：**
```python
class PlanningModule:
    def plan(self, observation: Dict, active_goal: Optional[Goal]) -> Dict:
        """根据观察生成计划"""
    
    def generate_goal(self, context: Dict) -> Optional[Goal]:
        """生成新目标（当没有活跃目标时）"""
    
    def decompose(self, goal: Goal) -> List[Step]:
        """将目标分解为步骤"""
```

---

### 3. ExecutionModule（执行模块）

**职责：**
- 执行计划中的单个步骤
- 调用 ToolAdapter（search/fetch/finance/message）
- 调用 SystemBridge（系统命令）
- 记录执行结果

**输入（订阅 EventBus）：**
- `plan.new_plan` — 新计划
- `plan.step_ready` — 步骤就绪

**输出（发布到 EventBus）：**
```json
{
  "type": "execution.step_result",
  "data": {
    "step_id": "...",
    "success": true/false,
    "result": {...},
    "error": "...",
    "duration_ms": 1500
  }
}
```

**关键方法：**
```python
class ExecutionModule:
    def execute_step(self, step: Step, context: Dict) -> Result:
        """执行单个步骤"""
    
    def execute_tool(self, tool_name: str, params: Dict) -> ToolResult:
        """调用工具"""
    
    def execute_system(self, cmd: str, context: str) -> SystemResult:
        """执行系统命令"""
```

---

### 4. ReflectionModule（反思模块）

**职责：**
- 对执行结果进行反思（MiMo 深度反思 + 本地简单反思）
- 评估目标完成质量
- 生成改进建议
- 记录到思维流

**输入（订阅 EventBus）：**
- `execution.step_result` — 步骤执行结果
- `goal.completed` — 目标完成
- `goal.failed` — 目标失败

**输出（发布到 EventBus）：**
```json
{
  "type": "reflection.insight",
  "data": {
    "depth": "simple/mimo",
    "insights": ["洞察1", "洞察2"],
    "action_items": ["建议1"],
    "mood": "...",
    "patterns": ["重复模式1"]
  }
}
```

**关键方法：**
```python
class ReflectionModule:
    def reflect_simple(self, step_result: Dict, plan: Dict) -> Dict:
        """简单反思（本地规则）"""
    
    def reflect_deep(self, tick_count: int) -> Dict:
        """MiMo 深度反思"""
    
    def log_to_thought_stream(self, insight: Dict) -> None:
        """记录到思维流"""
```

---

### 5. OrchestratorModule（编排模块）

**职责：**
- 协调其他 4 个模块的执行顺序
- 管理 tick 生命周期
- 处理异常和超时
- 维护整体状态机

**状态机：**
```
idle -> perceiving -> planning -> executing -> reflecting -> idle
```

**关键方法：**
```python
class OrchestratorModule:
    def tick(self) -> None:
        """一次完整的 OODA 循环"""
    
    def transition(self, from_state: State, to_state: State) -> None:
        """状态转换"""
    
    def handle_exception(self, module: str, error: Exception) -> None:
        """异常处理"""
    
    def get_status(self) -> Dict:
        """获取整体状态"""
```

---

## 模块间通信图

```
┌──────────────────────────────────────────────────────┐
│              OrchestratorModule（编排）                 │
│                  tick() → 协调所有模块                   │
└────────────┬──────────────┬──────────────┬───────────┘
             │              │              │
             ▼              ▼              ▼
┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│ Perception     │ │ Planning       │ │ Execution      │
│ 感知           │ │ 规划           │ │ 执行           │
│                │ │                │ │                │
│ observe()      │ │ plan()         │ │ execute_step() │
│ get_context()  │ │ generate_goal│ │ execute_tool() │
└───────┬────────┘ └───────┬────────┘ └───────┬────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
              ┌────────────────────┐
              │ Reflection         │
              │ 反思               │
              │                    │
              │ reflect_simple()   │
              │ reflect_deep()     │
              └────────────────────┘
```

---

## EventBus 消息流

```
tick_start
  ↓
[EventBus] perception.observation  (PerceptionModule 发布)
  ↓
[EventBus] plan.new_plan / plan.no_action  (PlanningModule 发布)
  ↓
[EventBus] execution.step_result  (ExecutionModule 发布)
  ↓
[EventBus] reflection.insight  (ReflectionModule 发布)
  ↓
tick_end
```

---

## 与现有代码的对应关系

| 现有方法 | 拆分后归属 |
|----------|-----------|
| `_observe()` | PerceptionModule.observe() |
| `_plan()` | PlanningModule.plan() |
| `_act()` | ExecutionModule.execute_step() |
| `_self_reflect()` | ReflectionModule.reflect_simple() |
| `tick()` | OrchestratorModule.tick() |
| `process_pending()` | PerceptionModule（EventBus处理） |
| `GoalGenerator` | PlanningModule.generate_goal() |
| `CuriosityTrigger` | PlanningModule（可拆出 CuriositySubmodule） |
| `PerformanceMonitor` | OrchestratorModule（埋点） |

---

## 迁移计划

### Phase 1：接口定义（今天）
- [x] 定义 5 个模块的接口
- [ ] 定义 EventBus 消息格式
- [ ] 画模块依赖图

### Phase 2：骨架实现（明天）
- [ ] 创建 5 个模块文件（空壳 + 接口）
- [ ] 实现 OrchestratorModule 的状态机
- [ ] 让 Orchestrator 能跑通一个空的 tick 循环

### Phase 3：逐个迁移（本周）
- [ ] 迁移 PerceptionModule（从 _observe()）
- [ ] 迁移 PlanningModule（从 _plan() + GoalGenerator）
- [ ] 迁移 ExecutionModule（从 _act()）
- [ ] 迁移 ReflectionModule（从 _self_reflect()）

### Phase 4：集成测试（下周）
- [ ] 跑通完整 OODA 循环
- [ ] 对比 v3.2 和 v3.3 的性能
- [ ] 修复集成问题

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| EventBus 消息丢失 | 中 | 高 | 添加 ACK 机制 |
| 模块间循环依赖 | 低 | 高 | 严格单向依赖 |
| 性能下降 | 中 | 中 | 基准测试 + 优化 |
| 集成复杂度爆炸 | 中 | 高 | 小步迭代，每步可回滚 |

---

## 代码结构

```
agent/cognition/
├── __init__.py
├── orchestrator.py      # OrchestratorModule
├── perception.py        # PerceptionModule
├── planning.py            # PlanningModule
├── execution.py           # ExecutionModule
├── reflection.py          # ReflectionModule
├── novel_analyzer.py      # NovelAnalyzer（已完成）
└── tool_adapter.py        # ToolAdapter（已有）
```

---

**下一步：开始实现 Phase 2 — 创建 5 个模块文件空壳。**
