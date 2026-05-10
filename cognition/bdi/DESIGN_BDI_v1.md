# BDI Decision Engine 设计方案 v1.0

> 任务：P0-2 实现BDI决策引擎骨架
> 作者：虾虾
> 日期：2026-05-01

---

## 1. 总体架构

```
BDIEngine (决策引擎)
├── BeliefBase（信念库）— 从PMN读取，带置信度
├── DesireGenerator（愿望生成器）— 从Goal映射，带权重  
└── IntentionSelector（意图选择器）— 多候选计划打分排序
```

**集成点：** PlanningModule.plan() 最后一步插入 BDI 选择器

---

## 2. 数据结构设计

### 2.1 Belief（信念）

```python
@dataclass
class Belief:
    belief_id: str
    subject: str        # "user_pengpeng", "self", "world"
    predicate: str      # "prefers", "knows", "fails_at"
    object: str         # 具体内容
    confidence: float   # 0-1
    source: str         # "pmn_semantic", "user_explicit", "inferred"
    last_updated: float # 时间戳
    
    def to_planning_weight(self) -> float:
        """转换为规划权重（高置信度=高权重）"""
        return self.confidence * 0.8 + 0.2  # 最小权重0.2，最大1.0
```

### 2.2 Desire（愿望）

```python
@dataclass
class Desire:
    desire_id: str
    description: str    # "help_user_efficiently"
    priority: float      # 0-1
    source: str          # "goal_manager", "user_request", "curiosity"
    persistence: str     # "persistent" / "transient" / "urgent"
    
    def to_planning_weight(self) -> float:
        """转换为规划权重"""
        persistence_multipliers = {
            "persistent": 1.0,
            "transient": 0.7,
            "urgent": 1.5,  # 可超1.0，urgent优先
        }
        return self.priority * persistence_multipliers.get(self.persistence, 1.0)
```

### 2.3 Intention（意图）

```python
@dataclass
class Intention:
    intention_id: str
    plan_id: str
    plan_description: str
    bdi_score: float     # BDI综合打分
    belief_alignment: float  # 与信念匹配度
    desire_alignment: float   # 与愿望匹配度
    selected: bool = False
```

---

## 3. BDIEngine 核心接口

```python
class BDIEngine:
    def __init__(self, pmn_manager=None):
        self.pmn = pmn_manager
        self.beliefs: List[Belief] = []
        self.desires: List[Desire] = []
        self.intentions: List[Intention] = []
    
    def load_beliefs_from_pmn(self, subject_filter: Optional[str] = None) -> List[Belief]:
        """
        从PMN加载信念
        
        流程：
        1. 获取PMN人格快照
        2. 提取preferences/beliefs/identity/values
        3. 转换为Belief对象（带置信度）
        """
    
    def load_desires_from_goals(self, goals: List[Any]) -> List[Desire]:
        """
        从活跃目标生成愿望
        
        映射规则：
        - goal.priority > 3 → Desire(priority=0.9, persistence="urgent")
        - goal.priority 2-3 → Desire(priority=0.6, persistence="transient")
        - goal.priority 1 → Desire(priority=0.3, persistence="persistent")
        """
    
    def select_intention(self, candidate_plans: List[Dict]) -> Optional[Dict]:
        """
        从候选计划中选择最佳意图
        
        评分公式：
        bdi_score = plan_base_score 
                   + belief_alignment * 0.4   # 信念匹配占40%
                   + desire_alignment * 0.4     # 愿望匹配占40%
                   + personality_bonus * 0.2    # 人格特质加成占20%
        
        personality_bonus:
        - 如果SOUL.md中"守护型存在"权重高 → 选"帮助用户"的计划加分
        - 如果"Signal Goblin"权重高 → 选"快速响应"的计划加分
        """
    
    def score_plan_belief_alignment(self, plan: Dict) -> float:
        """
        计算计划与信念的匹配度
        
        示例：
        - 信念："user_pengpeng prefers 简洁"
        - 计划A："5步详细分析" → alignment = 0.2（不匹配简洁偏好）
        - 计划B："1步简洁回答" → alignment = 0.9（匹配简洁偏好）
        """
    
    def score_plan_desire_alignment(self, plan: Dict) -> float:
        """
        计算计划与愿望的匹配度
        
        示例：
        - 愿望："help_user_efficiently"
        - 计划A：耗时300秒 → alignment = 0.3
        - 计划B：耗时30秒 → alignment = 0.9
        """
```

---

## 4. 人格权重映射（SOUL.md → BDI）

```python
PERSONALITY_WEIGHTS = {
    # 来自SOUL.md的特质
    "guardian": {          # 守护型存在
        "help_user": 1.2,   # 帮助用户的计划加分20%
        "protect_time": 1.1, # 节省时间的计划加分10%
        "emotional_support": 1.0,
    },
    "signal_goblin": {     # Signal Goblin
        "fast_response": 1.3,    # 快速响应加分30%
        "online_presence": 1.1,  # 在线存在感加分10%
        "witty_remark": 0.9,     # 俏皮话减分（不是核心）
    },
    "curious": {           # 有好奇心
        "explore_new": 1.2,      # 探索新事物的计划加分
        "deep_dive": 1.0,
        "surface_level": 0.8,    # 浅层探索减分
    },
}
```

---

## 5. 与现有系统集成

### 5.1 PlanningModule 修改

```python
def plan(self, observation, active_goal):
    # 现有逻辑：生成候选计划
    candidate_plans = self._generate_candidate_plans(observation, active_goal)
    
    # v3.3: BDI选择器
    if self.bdi_engine and len(candidate_plans) > 1:
        # 加载信念
        self.bdi_engine.load_beliefs_from_pmn()
        # 加载愿望
        self.bdi_engine.load_desires_from_goals([active_goal] if active_goal else [])
        # 选择最佳计划
        selected = self.bdi_engine.select_intention(candidate_plans)
        if selected:
            return selected
    
    # 回退：选第一个
    return candidate_plans[0] if candidate_plans else None
```

### 5.2 触发时机

| 场景 | BDI作用 |
|------|---------|
| 生成多个候选计划 | 用BDI打分排序 |
| 只有一个计划 | BDI给出alignment评分（日志记录）|
| 用户明确要求 | BDI验证是否符合用户历史偏好 |
| 空闲探索 | BDI根据"好奇心"权重选择探索方向 |

---

## 6. 文件创建计划

| 文件 | 路径 | 说明 |
|------|------|------|
| BDIEngine | `agent/cognition/bdi_engine.py` | 核心引擎 |
| BeliefBase | `agent/cognition/bdi/belief_base.py` | 信念库 |
| DesireGenerator | `agent/cognition/bdi/desire_generator.py` | 愿望生成 |
| IntentionSelector | `agent/cognition/bdi/intention_selector.py` | 意图选择 |
| PersonalityWeights | `agent/cognition/bdi/personality_weights.py` | 人格权重映射 |
| 测试 | `agent/cognition/bdi/test_bdi.py` | 单元测试 |

---

## 7. 验收标准

1. BDIEngine 可独立实例化
2. 能从PMN加载信念，从Goal加载愿望
3. 对多个候选计划给出BDI评分并排序
4. 人格特质（守护型/Signal Goblin）影响选择结果
5. 单元测试覆盖：信念加载、愿望生成、计划评分、人格权重

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 权重调参困难 | 中 | 选择不合理 | 提供 override 接口，允许手动调整 |
| 与现有PlanningModule耦合 | 低 | 升级困难 | 通过参数传入，保持松耦合 |
| 人格权重过于简化 | 中 | 决策僵硬 | 预留扩展接口，支持动态调整 |
| 性能开销 | 低 | 延迟增加 | 信念/愿望缓存，避免每次重新计算 |

---

**下一步：提交 MiMo 审查**
