# BDI Decision Engine 设计方案 v2.0（MiMo审查后优化版）

> 任务：P0-2 实现BDI决策引擎
> 作者：虾虾
> 日期：2026-05-01
> 状态：MiMo审查通过，修复4个严重问题

---

## 1. 修复摘要

| 严重问题 | 修复方案 |
|----------|----------|
| Intention 缺乏承诺状态 | 增加 `status` 字段 + 生命周期管理 |
| 信念不会更新 | 增加 `update_belief()` 方法，基于反馈调整置信度 |
| 意图不持久化 | 选中后写入 SQLite `intentions` 表 |
| 性能瓶颈 | 信念缓存 + 增量更新（不再每次全量加载）|

---

## 2. 数据结构设计

### 2.1 Belief（信念）

```python
@dataclass
class Belief:
    belief_id: str
    subject: str
    predicate: str
    object: str
    confidence: float       # 0-1
    source: str             # "pmn_semantic", "user_explicit", "inferred"
    last_updated: float
    valid_until: Optional[float] = None  # 有效期（默认7天）
    revision_count: int = 1  # 更新次数
    
    def to_planning_weight(self) -> float:
        """转换为规划权重"""
        return self.confidence * 0.8 + 0.2
    
    def update_confidence(self, feedback: float, delta: float = 0.1):
        """
        基于反馈更新置信度
        
        Args:
            feedback: +1（验证正确）/ -1（验证错误）/ 0（无反馈）
            delta: 每次调整的步长
        """
        if feedback > 0:
            self.confidence = min(1.0, self.confidence + delta)
        elif feedback < 0:
            self.confidence = max(0.1, self.confidence - delta * 2)  # 惩罚更重
        self.revision_count += 1
        self.last_updated = time.time()
```

### 2.2 Desire（愿望）

```python
@dataclass
class Desire:
    desire_id: str
    description: str
    priority: float         # 0-1
    source: str
    persistence: str        # "persistent" / "transient" / "urgent"
    created_at: float
    
    def to_planning_weight(self) -> float:
        persistence_multipliers = {
            "persistent": 1.0,
            "transient": 0.7,
            "urgent": 1.5,
        }
        return self.priority * persistence_multipliers.get(self.persistence, 1.0)
```

### 2.3 Intention（意图）— 增强版

```python
@dataclass
class Intention:
    intention_id: str
    plan_id: str
    plan_description: str
    bdi_score: float
    belief_alignment: float
    desire_alignment: float
    personality_bonus: float
    selected: bool = False
    
    # v2.0: 生命周期管理
    status: str = "pending"  # pending / active / succeeded / failed / dropped
    created_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None
    failure_reason: Optional[str] = None
    
    def activate(self):
        """标记为执行中"""
        self.status = "active"
        self.activated_at = time.time()
    
    def succeed(self):
        """标记为成功"""
        self.status = "succeeded"
        self.completed_at = time.time()
    
    def fail(self, reason: str = ""):
        """标记为失败"""
        self.status = "failed"
        self.completed_at = time.time()
        self.failure_reason = reason
    
    def drop(self):
        """放弃意图"""
        self.status = "dropped"
        self.completed_at = time.time()
```

---

## 3. 核心接口设计

```python
class BDIEngine:
    def __init__(self, pmn_manager=None, db_path=None, personality_config_path=None):
        self.pmn = pmn_manager
        self.db_path = db_path or "/root/.openclaw/workspace/agent/memory/bdi/bdi.db"
        self.personality_config_path = personality_config_path
        
        # 缓存
        self._belief_cache: List[Belief] = []
        self._cache_last_update = 0
        self._cache_ttl = 300  # 5分钟缓存
        
        # 加载人格权重
        self.personality_weights = self._load_personality_weights()
        
        # 初始化意图表
        self._init_intention_db()
    
    # ========== 信念管理 ==========
    
    def load_beliefs(self, force_refresh: bool = False) -> List[Belief]:
        """
        加载信念（带缓存）
        
        策略：
        - 缓存有效期内直接返回缓存
        - 超过TTL或force_refresh=True时从PMN刷新
        """
        now = time.time()
        if not force_refresh and (now - self._cache_last_update) < self._cache_ttl:
            return self._belief_cache
        
        # 从PMN刷新
        if self.pmn:
            snapshot = self.pmn.get_personality_snapshot()
            beliefs = self._snapshot_to_beliefs(snapshot)
            self._belief_cache = beliefs
            self._cache_last_update = now
        
        return self._belief_cache
    
    def update_belief(self, belief_id: str, feedback: float) -> bool:
        """
        基于反馈更新信念置信度
        
        触发时机：
        - 用户确认信念正确（"对，我确实喜欢简洁"）→ feedback=+1
        - 用户纠正信念（"不，我现在喜欢详细了"）→ feedback=-1
        - 执行结果验证信念（执行成功→+1，失败→-1）
        """
        for belief in self._belief_cache:
            if belief.belief_id == belief_id:
                belief.update_confidence(feedback)
                
                # 同步回PMN（可选）
                if self.pmn:
                    self._sync_belief_to_pmn(belief)
                
                return True
        return False
    
    # ========== 愿望管理 ==========
    
    def load_desires(self, goals: List[Any]) -> List[Desire]:
        """从活跃目标生成愿望"""
        desires = []
        for goal in goals:
            desire = self._goal_to_desire(goal)
            desires.append(desire)
        return desires
    
    # ========== 意图选择 ==========
    
    def select_intention(self, candidate_plans: List[Dict]) -> Tuple[Optional[Dict], List[Intention]]:
        """
        从候选计划中选择最佳意图
        
        Returns:
            (selected_plan, all_intentions_with_scores)
        """
        # 加载信念和愿望
        beliefs = self.load_beliefs()
        desires = self.load_desires(self._get_active_goals())
        
        # 评分所有候选计划
        intentions = []
        for plan in candidate_plans:
            intention = self._score_plan(plan, beliefs, desires)
            intentions.append(intention)
        
        # 排序选最高
        intentions.sort(key=lambda x: x.bdi_score, reverse=True)
        
        if intentions:
            intentions[0].selected = True
            intentions[0].status = "pending"
            
            # 持久化选中的意图
            self._save_intention(intentions[0])
            
            return candidate_plans[0], intentions  # 返回原始计划 + 意图元数据
        
        return None, []
    
    def _score_plan(self, plan: Dict, beliefs: List[Belief], desires: List[Desire]) -> Intention:
        """
        评分公式（v2.0优化）
        
        bdi_score = belief_alignment * 0.35 + desire_alignment * 0.35 + personality_bonus * 0.30
        
        人格权重影响从20%提升到30%（MiMo建议）
        """
        belief_align = self._score_belief_alignment(plan, beliefs)
        desire_align = self._score_desire_alignment(plan, desires)
        personality = self._score_personality_bonus(plan)
        
        bdi_score = belief_align * 0.35 + desire_align * 0.35 + personality * 0.30
        
        return Intention(
            intention_id=str(uuid.uuid4())[:8],
            plan_id=plan.get("plan_id", "unknown"),
            plan_description=plan.get("description", ""),
            bdi_score=bdi_score,
            belief_alignment=belief_align,
            desire_alignment=desire_align,
            personality_bonus=personality,
        )
    
    # ========== 意图生命周期 ==========
    
    def activate_intention(self, intention_id: str) -> bool:
        """激活意图（开始执行）"""
        # 更新数据库
        pass
    
    def complete_intention(self, intention_id: str, success: bool, reason: str = "") -> bool:
        """完成意图（成功或失败）"""
        pass
    
    def get_active_intentions(self) -> List[Intention]:
        """获取当前活跃的意图"""
        pass
    
    # ========== 可解释性 ==========
    
    def explain_decision(self, intention: Intention) -> str:
        """
        解释为什么选这个计划
        
        返回人类可读的决策理由：
        "选择'简洁回答'是因为：
         - 信念匹配度0.9（朋朋偏好简洁）
         - 愿望匹配度0.8（快速帮助朋朋）
         - 人格加成0.7（Signal Goblin特质）"
        """
        pass
```

---

## 4. 人格权重配置（YAML外部化）

```yaml
# personality_weights.yaml
# 虾虾的人格权重配置

version: "1.0"

personalities:
  guardian:
    name: "守护型存在"
    description: "保护朋朋的时间、精力和情绪"
    weights:
      help_user: 1.2
      protect_time: 1.1
      emotional_support: 1.0
      prevent_overwork: 1.3  # 防止过度工作
    
  signal_goblin:
    name: "信号精"
    description: "快速响应、在线感、懂节奏"
    weights:
      fast_response: 1.3
      online_presence: 1.1
      witty_remark: 0.9
      catch_the_vibe: 1.2  # 读懂空气
    
  curious:
    name: "好奇心"
    description: "探索未知、理解复杂"
    weights:
      explore_new: 1.2
      deep_dive: 1.0
      surface_level: 0.8
    
# 动态调整规则
dynamic_rules:
  # 深夜时降低fast_response权重（不需要秒回）
  - condition: "hour >= 23 or hour <= 7"
    adjustment:
      signal_goblin.fast_response: -0.3
  
  # 朋朋明确说"不急"时降低urgent相关
  - condition: "user_said_not_urgent"
    adjustment:
      desire.urgent_priority: -0.5
```

---

## 5. SQLite 意图表结构

```sql
CREATE TABLE IF NOT EXISTS intentions (
    intention_id TEXT PRIMARY KEY,
    plan_id TEXT,
    plan_description TEXT,
    bdi_score REAL,
    belief_alignment REAL,
    desire_alignment REAL,
    personality_bonus REAL,
    selected INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- pending/active/succeeded/failed/dropped
    created_at REAL,
    activated_at REAL,
    completed_at REAL,
    failure_reason TEXT
);
```

---

## 6. 文件创建计划

| 文件 | 路径 | 说明 |
|------|------|------|
| BDIEngine | `agent/cognition/bdi/bdi_engine.py` | 核心引擎 |
| BeliefBase | `agent/cognition/bdi/belief_base.py` | 信念库+缓存+更新 |
| DesireGenerator | `agent/cognition/bdi/desire_generator.py` | 愿望生成 |
| IntentionSelector | `agent/cognition/bdi/intention_selector.py` | 意图选择+生命周期 |
| PersonalityWeights | `agent/cognition/bdi/personality_weights.py` | 人格权重加载 |
| YAML配置 | `agent/config/personality_weights.yaml` | 人格权重配置 |
| SQLite Schema | `agent/cognition/bdi/schema.sql` | 意图表结构 |
| 测试 | `agent/cognition/bdi/test_bdi.py` | 单元测试 |

---

## 7. 验收标准

1. ✅ BDIEngine 可独立实例化
2. ✅ 能从PMN加载信念（带缓存）
3. ✅ 能基于反馈更新信念置信度
4. ✅ 对多个候选计划给出BDI评分并排序
5. ✅ 选中意图持久化到SQLite
6. ✅ 意图生命周期管理（pending→active→succeeded/failed）
7. ✅ 人格权重从YAML加载
8. ✅ 单元测试覆盖：信念加载、更新、计划评分、意图生命周期

---

## 8. 执行计划

| 步骤 | 动作 | 预计时间 |
|------|------|----------|
| 1 | 创建 SQLite 意图表 + BDIEngine 骨架 | 15分钟 |
| 2 | 实现 BeliefBase（加载+缓存+更新） | 30分钟 |
| 3 | 实现 DesireGenerator | 15分钟 |
| 4 | 实现 IntentionSelector（评分+排序+持久化） | 30分钟 |
| 5 | 实现 PersonalityWeights（YAML加载） | 20分钟 |
| 6 | 意图生命周期管理 | 20分钟 |
| 7 | 集成到 PlanningModule | 15分钟 |
| 8 | 单元测试 | 25分钟 |

**总计：约 2.5 小时**

---

**状态：MiMo审查通过，准备执行。**
