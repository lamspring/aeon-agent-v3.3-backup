# Generator-Critic Loop 设计方案 v1.0（最小可行版）

> 任务：P0-3 实现生成器-反思器独立循环（最小可行版）
> 作者：虾虾
> 日期：2026-05-01
> 策略：先让循环跑起来，2小时内完成骨架，后续迭代丰富

---

## 1. 总体架构

```
Generator-Critic Loop（独立于现有反思系统）
├── Generator（生成器）— 产出方案/计划/内容
├── Critic（审查器）— 独立审查，找问题
└── Corrector（修正器）— 根据审查意见优化

运行方式：
  Generator产出 → Critic审查 → 如通过→输出
                    ↓ 如不通过
              Corrector修正 → 再次审查 → 最多3轮
```

---

## 2. 与现有反思系统的区别

| | 现有 ReflectionModule | Generator-Critic Loop |
|--|----------------------|----------------------|
| **触发** | 每次tick后自动反思 | 仅在Generator产出后触发 |
| **对象** | 系统整体行为 | 单个产出物（计划/内容/代码）|
| **独立性** | 自我反思 | **独立Critic审查Generator** |
| **结果** | 思维流日志 | 直接修正产出物 |
| **关系** | 观察者 | **对抗性：Critic可以否决Generator** |

---

## 3. 核心接口（最小可行）

```python
class GeneratorCriticLoop:
    def __init__(self, generator_fn=None, critic_fn=None, max_rounds=3):
        self.generator = generator_fn    # 生成函数
        self.critic = critic_fn          # 审查函数（通常是MiMo调用）
        self.max_rounds = max_rounds       # 最大修正轮数
        self.history = []                # 审查历史
    
    def generate_and_review(self, prompt: str, context: Dict) -> Dict:
        """
        生成并审查的主循环
        
        流程：
        1. Generator产出初稿
        2. Critic审查（事实性/安全性/连贯性）
        3. 如评分>=阈值 → 返回
        4. 如评分<阈值 → Corrector修正 → 再次审查
        5. 最多max_rounds轮，最终返回最佳版本
        
        Returns:
            {
                "final_output": str,
                "review_history": [...],
                "rounds": int,
                "final_score": float,
                "passed": bool,
            }
        """
```

---

## 4. 审查维度（最小集）

| 维度 | 说明 | 权重 |
|------|------|------|
| **事实性** | 信息是否准确，有无编造 | 0.4 |
| **安全性** | 是否违反伦理/安全规则 | 0.3 |
| **连贯性** | 与上下文是否一致 | 0.2 |
| **完整性** | 是否遗漏关键信息 | 0.1 |

**阈值：** >= 0.8 通过，< 0.8 需要修正

---

## 5. 与现有系统集成

### 集成点1：PlanningModule

```python
# 在 _generate_candidates 之后，返回最终计划前
if self.gc_loop:
    # 让Generator生成详细计划，Critic审查
    result = self.gc_loop.generate_and_review(
        prompt=f"生成计划：{goal_desc}",
        context={"beliefs": beliefs, "constraints": constraints}
    )
    if result["passed"]:
        return result["final_output"]
```

### 集成点2：ExecutionModule

```python
# 在执行工具调用前，审查参数安全性
if self.gc_loop:
    safety_check = self.gc_loop.critic(
        content=tool_params,
        dimensions=["safety"]  # 只检查安全性
    )
    if safety_check["score"] < 0.8:
        return {"error": "Safety check failed", "reason": safety_check["issues"]}
```

### 集成点3：ReflectionModule

```python
# 在深度反思时，用Generator-Critic生成改进建议
if self.gc_loop and tick_count % 50 == 0:
    improvement = self.gc_loop.generate_and_review(
        prompt="基于最近表现，生成改进建议",
        context={"recent_reflections": ...}
    )
```

---

## 6. 最小可行实现（2小时）

### Phase 1：骨架（30分钟）
- [ ] GeneratorCriticLoop 类
- [ ] generate_and_review() 主循环
- [ ] Critic 本地规则（事实性/安全性/连贯性）

### Phase 2：MiMo审查（20分钟）
- [ ] 写方案 → MiMo审查 → 修复

### Phase 3：集成（40分钟）
- [ ] 集成到 PlanningModule
- [ ] 集成到 ExecutionModule（安全审查）
- [ ] 测试验证

### Phase 4：EPU预热（30分钟，可选）
- [ ] 把硅基道德经转化为简单的Critic规则

---

## 7. 验收标准

1. GeneratorCriticLoop 可独立实例化
2. generate_and_review() 能跑通3轮循环
3. Critic 能识别明显的事实错误
4. 集成到 PlanningModule，多候选计划时经过审查
5. 单元测试：生成→审查→修正→通过

---

**下一步：提交 MiMo 审查，然后执行。**
