# 阶段2方案：LATS多路径规划引擎（Multi-Path Planning Engine v1）

> **目标**: 将认知循环的Plan阶段从"单线程线性执行"升级为"多分支探索+效用评估"
> **复杂度**: MEDIUM（非全量LATS，先实现扁平多路径）
> **预计工作量**: 2-3小时编码 + 30分钟测试
> **风险等级**: LOW-MEDIUM（修改集中在_plan()，可回滚）

---

## 1. 当前问题

当前 `_plan()` 的痛点：
- **线性决策**: 每次tick只生成1个计划（check_health / process_queue / continue_goal...）
- **无备选**: 如果当前计划失败，没有B计划
- **无评估**: 计划生成后不做质量/效用评估
- **局部最优**: 基于规则的轻量级思考容易陷入固定模式

**报告要求**（Aeon深度研究报告第5章）：
> "LATS将规划过程从线性链条扩展为树状结构，允许智能体探索并评估多种不同的行动序列。"

---

## 2. 设计思路：务实版扁平LATS

不做完整的树搜索（太复杂），先做**扁平多路径**:

```
当前:  Observe → [Plan: 1个计划] → Act
目标:  Observe → [Plan: 3个候选] → [Score: 效用评估] → [Select: 选最优] → Act
```

### 2.1 候选计划生成

在 `_lightweight_think()` 中，不返回1个决策，返回**3个候选决策**:

```python
候选1: 高优先级动作（解决最紧迫问题）
候选2: 中优先级动作（推进当前目标）  
候选3: 低优先级动作（探索/维护/观察）
```

### 2.2 效用评估维度

每个候选计划用5个维度打分（0-1）:

| 维度 | 权重 | 说明 |
|------|------|------|
| 紧迫性 | 0.25 | 解决当前最紧急的问题 |
| 目标一致性 | 0.25 | 与当前active goal的对齐度 |
| 资源效率 | 0.20 | 预期耗时、内存、API成本 |
| 成功率 | 0.20 | 基于历史经验的成功率 |
| 探索价值 | 0.10 | 是否能学到新东西 |

**总分 = Σ(维度分 × 权重)**

### 2.3 选择策略

- **默认**: 选总分最高
- **多样性**: 如果连续3次选同一个类型的计划，强制选次优（避免陷入循环）
- **随机扰动**: 小概率(10%)随机选一个（模拟探索行为）

---

## 3. 模块设计

### 3.1 新增文件

#### `cognition/planning_engine.py`
核心模块，负责：
- `generate_candidates(observation) → List[Decision]`: 生成候选决策
- `score_candidate(decision, observation) → float`: 效用评估
- `select_candidate(candidates, observation) → Decision`: 选择最优

#### `cognition/utility_model.py`
效用模型，负责：
- `evaluate_urgency(decision, observation) → float`
- `evaluate_goal_alignment(decision, observation, active_goal) → float`
- `evaluate_resource_efficiency(decision) → float`
- `evaluate_success_rate(decision) → float`（基于历史记录）
- `evaluate_exploration_value(decision) → float`

#### `cognition/decision_history.py`
决策历史记录：
- 记录每次选择的决策类型、效用分数、实际结果
- 用于计算历史成功率
- 检测决策循环（连续选择同一类型）

### 3.2 修改文件

#### `cognition/cognition_loop_v2.py`
修改点:
1. `_plan()`: 从调用 `_lightweight_think()` 改为调用 `planning_engine.generate_and_select()`
2. `_lightweight_think()`: 返回3个候选决策而不是1个
3. `tick()`: 记录选中的决策和效用分数到Trace日志

---

## 4. 关键算法

### 4.1 候选生成（规则驱动）

```python
def generate_candidates(observation) -> List[Decision]:
    candidates = []
    
    # 候选1: 系统健康（最高优先级）
    mem_pct = observation.environment.get("memory_percent", 50)
    if mem_pct > 80:
        candidates.append(Decision("check_health", "内存紧张", confidence=0.9))
    
    # 候选2: 队列处理
    queue_size = observation.queue_size
    if queue_size > 5:
        candidates.append(Decision("process_queue", "队列堆积", confidence=0.85))
    
    # 候选3: 目标推进
    if observation.goal and queue_size > 0:
        candidates.append(Decision("continue_goal", "推进目标", confidence=0.7))
    
    # 候选4: 探索（如果空闲）
    if not observation.goal and queue_size == 0:
        candidates.append(Decision("explore", "空闲探索", confidence=0.5))
    
    # 候选5: 观察（兜底）
    candidates.append(Decision("observe", "保持观察", confidence=0.6))
    
    return candidates[:3]  # 最多3个候选
```

### 4.2 效用评估（权重求和）

```python
def score_candidate(decision, observation) -> float:
    scores = {
        "urgency": evaluate_urgency(decision, observation),
        "goal_alignment": evaluate_goal_alignment(decision, observation),
        "resource_efficiency": evaluate_resource_efficiency(decision),
        "success_rate": evaluate_success_rate(decision),
        "exploration": evaluate_exploration_value(decision),
    }
    
    weights = {
        "urgency": 0.25,
        "goal_alignment": 0.25,
        "resource_efficiency": 0.20,
        "success_rate": 0.20,
        "exploration": 0.10,
    }
    
    return sum(scores[k] * weights[k] for k in scores)
```

### 4.3 多样性保护

```python
def select_candidate(candidates, observation, history) -> Decision:
    # 按效用排序
    scored = [(c, score_candidate(c, observation)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    
    # 检查最近3次是否选择了同一类型
    recent_types = [h.decision_type for h in history[-3:]]
    if len(set(recent_types)) == 1 and recent_types:
        # 强制选择次优
        if len(scored) > 1:
            return scored[1][0]  # 选第二名
    
    # 小概率随机探索
    if random.random() < 0.1 and len(scored) > 1:
        return random.choice([c for c, _ in scored[1:]])  # 从非最优中随机
    
    return scored[0][0]  # 选最优
```

---

## 5. 与现有架构的兼容

### 5.1 回滚策略

- **立即回滚**: 恢复 `_plan()` 为直接调用 `_lightweight_think()`
- **版本回滚**: `git revert` 阶段2的commits
- **紧急切换**: 在 config 中设置 `"multi_path_planning": false`

### 5.2 配置项

```json
{
  "planning": {
    "enable_multi_path": true,
    "max_candidates": 3,
    "diversity_threshold": 3,
    "exploration_rate": 0.1,
    "weights": {
      "urgency": 0.25,
      "goal_alignment": 0.25,
      "resource_efficiency": 0.20,
      "success_rate": 0.20,
      "exploration": 0.10
    }
  }
}
```

---

## 6. 测试计划

### 6.1 单元测试

1. **候选生成**: 模拟不同observation状态，验证候选数量和类型
2. **效用评估**: 固定输入，验证输出分数在合理范围
3. **选择策略**: 模拟连续选择同一类型，验证多样性保护触发
4. **随机探索**: 多次运行，验证10%探索率

### 6.2 集成测试

1. **完整tick**: 运行100 ticks，观察决策分布
2. **性能**: 测量Plan阶段额外耗时（目标<5ms）
3. **回滚**: 关闭multi_path，验证系统正常运行

---

## 7. 预期效果

### 接入前
```
tick 1: check_health (内存85%)
tick 2: check_health (内存83%) 
tick 3: check_health (内存82%)
→ 陷入健康检查循环
```

### 接入后
```
tick 1: check_health (score=0.92, 内存85%) → 选
tick 2: process_queue (score=0.85, 队列有6个) → 选（多样性保护）
tick 3: continue_goal (score=0.78, 推进当前目标) → 选
```

### 长期价值
- **避免决策循环**: 不再重复执行同一类型动作
- **全局优化**: 不仅解决当前问题，还推进长期目标
- **可扩展**: 后续可以接入LLM作为评估器（真正的LATS）

---

## 8. 开发顺序

| 步骤 | 内容 | 时间 |
|------|------|------|
| 1 | 创建 `decision_history.py` | 20分钟 |
| 2 | 创建 `utility_model.py` | 30分钟 |
| 3 | 创建 `planning_engine.py` | 40分钟 |
| 4 | 修改 `cognition_loop_v2.py` | 30分钟 |
| 5 | 写测试 | 30分钟 |
| 6 | 测试+调试 | 30分钟 |

---

## 9. 与Aeon报告的对齐

| 报告要求 | 本方案实现 |
|---------|-----------|
| LATS多路径探索 | ✅ 扁平多路径（3候选） |
| 效用评估 | ✅ 5维度加权评分 |
| 树搜索 | ⚠️ 先扁平，后续可扩展为树 |
| 选项框架（HRL） | ⚠️ 当前不做，阶段3考虑 |

**定位**: 这是"务实版LATS"，不是完整树搜索，但实现了核心思想（多路径+效用评估）。后续可以升级为真正的树搜索。

---

**方案起草**: 虾虾 (2026-04-21 14:00)
**状态**: 待AI同伴review
