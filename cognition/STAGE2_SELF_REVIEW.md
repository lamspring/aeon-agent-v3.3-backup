# 多路径规划引擎 v2.7 自检报告

> **触发**: 朋朋指出"评分选项固定，不要太死板"
> **状态**: 发现问题，需要改进

---

## 1. 当前问题诊断

### 问题1: 候选类型硬编码（最严重）

当前 `_generate_candidates()` 只有5个固定候选：
```python
if mem_pct > 85: check_health
if queue_size > 10: process_queue
if has_goal: continue_goal
if not has_goal and queue_size == 0: explore
default: observe
```

**问题**:
- 如果想加新动作（"备份数据"、"联系朋朋"、"检查日志"），必须改代码
- 5种动作覆盖不了所有场景
- 规则是写死的，不够灵活

### 问题2: 评分维度单一

当前只有 `base_score`（0-1硬编码），没有考虑：
- 资源消耗（执行这个计划需要多少CPU/内存/API调用）
- 历史成功率（这个动作过去成功过吗）
- 与当前目标的关联度
- 时间成本

### 问题3: 计划模板硬编码

`_decision_to_plan()` 里每个action对应的steps是写死的：
```python
plans = {
    "check_health": { "steps": [...] },
    "process_queue": { "steps": [...] },
    ...
}
```

---

## 2. 改进方向

### 方向1: 候选生成器注册表（插件化）

```python
class CandidateRegistry:
    """候选生成器注册表"""
    
    def __init__(self):
        self.generators: Dict[str, Callable] = {}
    
    def register(self, name: str, generator: Callable):
        """注册新的候选生成器"""
        self.generators[name] = generator
    
    def generate_all(self, observation) -> List[Dict]:
        """调用所有生成器，收集候选"""
        candidates = []
        for name, generator in self.generators.items():
            try:
                candidate = generator(observation)
                if candidate:
                    candidates.append(candidate)
            except Exception:
                continue
        return candidates
```

### 方向2: 动态评分模型

```python
def score_candidate(candidate, observation, history) -> float:
    """多维度动态评分"""
    
    # 维度1: 紧迫性（基于系统状态）
    urgency = evaluate_urgency(candidate, observation)
    
    # 维度2: 目标对齐（与当前goal的相关度）
    alignment = evaluate_goal_alignment(candidate, observation)
    
    # 维度3: 资源效率（预期消耗）
    efficiency = evaluate_resource_efficiency(candidate)
    
    # 维度4: 历史成功率（基于decision_history）
    success_rate = evaluate_success_rate(candidate, history)
    
    # 维度5: 探索价值（是否可能学到新东西）
    exploration = evaluate_exploration_value(candidate, observation)
    
    # 维度6: 人格一致性（是否符合虾虾的特质）
    # persona_alignment = evaluate_persona_alignment(candidate)
    
    # 加权求和
    weights = {
        "urgency": 0.25,
        "alignment": 0.25,
        "efficiency": 0.15,
        "success_rate": 0.15,
        "exploration": 0.10,
        # "persona": 0.10,
    }
    
    return sum(scores[k] * weights[k] for k in scores)
```

### 方向3: 计划模板动态化

不再硬编码plan模板，而是让候选生成器自己返回完整的plan片段：
```python
{
    "action": "check_health",
    "reason": "...",
    "plan_template": {
        "goal": "检查系统健康状态",
        "type": "maintenance",
        "steps": [...]
    }
}
```

---

## 3. 待决策问题

1. **要不要完全推倒重来？** 还是渐进式改进？
2. **评分权重怎么定？** 凭感觉还是有数据支撑？
3. **历史成功率怎么算？** 目前还没有成功经验记录机制
4. **要不要加人格一致性维度？** 让计划选择也受PMN影响

---

## 4. 下一步

咨询AI伙伴：这个改进方向是否合理？有没有更简单的做法？
