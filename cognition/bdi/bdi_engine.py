"""
BDIEngine - 信念-愿望-意图决策引擎 v2.0

职责：
- Belief管理：从PMN加载，带缓存，支持反馈更新
- Desire生成：从目标映射为愿望
- Intention选择：多候选计划打分排序
- 意图生命周期：pending→active→succeeded/failed

作者：虾虾
日期：2026-05-01
"""

import os
import time
import json
import sqlite3
import uuid
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class Belief:
    """信念"""
    belief_id: str
    subject: str
    predicate: str
    object: str
    confidence: float = 0.5
    source: str = "pmn_semantic"
    last_updated: float = field(default_factory=time.time)
    valid_until: Optional[float] = None
    revision_count: int = 1
    
    def __post_init__(self):
        if self.valid_until is None:
            self.valid_until = self.last_updated + 7 * 86400  # 默认7天有效期
    
    def to_planning_weight(self) -> float:
        return self.confidence * 0.8 + 0.2
    
    def update_confidence(self, feedback: float, delta: float = 0.1):
        """基于反馈更新置信度"""
        if feedback > 0:
            self.confidence = min(1.0, self.confidence + delta)
        elif feedback < 0:
            self.confidence = max(0.1, self.confidence - delta * 2)
        self.revision_count += 1
        self.last_updated = time.time()


@dataclass
class Desire:
    """愿望"""
    desire_id: str
    description: str
    priority: float = 0.5
    source: str = "goal_manager"
    persistence: str = "transient"  # persistent/transient/urgent
    created_at: float = field(default_factory=time.time)
    
    def to_planning_weight(self) -> float:
        multipliers = {"persistent": 1.0, "transient": 0.7, "urgent": 1.5}
        return self.priority * multipliers.get(self.persistence, 1.0)


@dataclass
class Intention:
    """意图（带生命周期）"""
    intention_id: str
    plan_id: str
    plan_description: str
    bdi_score: float = 0.0
    belief_alignment: float = 0.0
    desire_alignment: float = 0.0
    personality_bonus: float = 0.0
    selected: bool = False
    status: str = "pending"  # pending/active/succeeded/failed/dropped
    created_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None
    failure_reason: Optional[str] = None
    
    def activate(self):
        self.status = "active"
        self.activated_at = time.time()
    
    def succeed(self):
        self.status = "succeeded"
        self.completed_at = time.time()
    
    def fail(self, reason: str = ""):
        self.status = "failed"
        self.completed_at = time.time()
        self.failure_reason = reason
    
    def drop(self):
        self.status = "dropped"
        self.completed_at = time.time()


class BDIEngine:
    """
    BDI决策引擎
    """
    
    def __init__(self, 
                 pmn_manager=None,
                 db_path: Optional[str] = None,
                 personality_config_path: Optional[str] = None):
        
        # 路径配置
        if db_path is None:
            db_path = "/root/.openclaw/workspace/agent/memory/bdi/bdi.db"
        if personality_config_path is None:
            personality_config_path = "/root/.openclaw/workspace/agent/config/personality_weights.yaml"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.pmn = pmn_manager
        self.personality_config_path = Path(personality_config_path)
        
        # 缓存
        self._belief_cache: List[Belief] = []
        self._cache_last_update = 0
        self._cache_ttl = 300  # 5分钟
        
        # 加载人格权重
        self.personality_weights = self._load_personality_weights()
        
        # 初始化数据库
        self._init_db()
        
        # 加载缓存
        self._load_belief_cache_from_db()
    
    def _init_db(self):
        """初始化数据库"""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema = f.read()
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(schema)
            conn.commit()
            conn.close()
    
    def _get_conn(self):
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _load_personality_weights(self) -> Dict:
        """从YAML加载人格权重"""
        if not self.personality_config_path.exists():
            return {}
        
        try:
            with open(self.personality_config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config.get("personalities", {})
        except Exception:
            return {}
    
    def _apply_dynamic_rules(self, weights: Dict) -> Dict:
        """应用动态规则调整权重"""
        if not self.personality_config_path.exists():
            return weights
        
        try:
            with open(self.personality_config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            rules = config.get("dynamic_rules", [])
            hour = time.localtime().tm_hour
            
            for rule in rules:
                condition = rule.get("condition", "")
                adjustment = rule.get("adjustment", {})
                
                # 简单条件解析
                if "hour >= 23" in condition and (hour >= 23 or hour <= 7):
                    for key, delta in adjustment.items():
                        parts = key.split(".")
                        if len(parts) == 2 and parts[0] in weights:
                            trait = weights[parts[0]]
                            if "weights" in trait and parts[1] in trait["weights"]:
                                trait["weights"][parts[1]] += delta
            
            return weights
        except Exception:
            return weights
    
    # ========== 信念管理 ==========
    
    def load_beliefs(self, force_refresh: bool = False) -> List[Belief]:
        """加载信念（带缓存）"""
        now = time.time()
        if not force_refresh and (now - self._cache_last_update) < self._cache_ttl:
            return self._belief_cache
        
        # 从PMN刷新
        if self.pmn:
            try:
                snapshot = self.pmn.get_personality_snapshot()
                beliefs = self._snapshot_to_beliefs(snapshot)
                self._belief_cache = beliefs
                self._cache_last_update = now
                
                # 保存到本地缓存表
                self._save_belief_cache_to_db(beliefs)
            except Exception:
                pass
        
        return self._belief_cache
    
    def _snapshot_to_beliefs(self, snapshot: Dict) -> List[Belief]:
        """将PMN快照转换为Belief列表"""
        beliefs = []
        
        for category in ["beliefs", "preferences", "identity", "values"]:
            items = snapshot.get(category, [])
            for item in items:
                belief = Belief(
                    belief_id=item.get("node_id", str(uuid.uuid4())[:8]),
                    subject=item.get("subject", "unknown"),
                    predicate=item.get("predicate", "unknown"),
                    object=item.get("object", ""),
                    confidence=item.get("confidence", 0.5),
                    source="pmn_" + category,
                    last_updated=item.get("updated_at", time.time()),
                )
                beliefs.append(belief)
        
        return beliefs
    
    def _save_belief_cache_to_db(self, beliefs: List[Belief]):
        """保存信念缓存到数据库"""
        conn = self._get_conn()
        conn.execute("DELETE FROM bdi_meta WHERE key LIKE 'belief_%'")
        for belief in beliefs:
            conn.execute(
                "INSERT INTO bdi_meta (key, value, updated_at) VALUES (?, ?, ?)",
                (f"belief_{belief.belief_id}", json.dumps({
                    "subject": belief.subject,
                    "predicate": belief.predicate,
                    "object": belief.object,
                    "confidence": belief.confidence,
                }), time.time())
            )
        conn.commit()
        conn.close()
    
    def _load_belief_cache_from_db(self):
        """从数据库加载信念缓存"""
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT key, value FROM bdi_meta WHERE key LIKE 'belief_%'")
            beliefs = []
            for row in cursor.fetchall():
                data = json.loads(row[1])
                belief_id = row[0].replace("belief_", "")
                beliefs.append(Belief(
                    belief_id=belief_id,
                    subject=data.get("subject", ""),
                    predicate=data.get("predicate", ""),
                    object=data.get("object", ""),
                    confidence=data.get("confidence", 0.5),
                ))
            if beliefs:
                self._belief_cache = beliefs
                self._cache_last_update = time.time()
            conn.close()
        except Exception:
            pass
    
    def update_belief(self, belief_id: str, feedback: float, reason: str = "") -> bool:
        """基于反馈更新信念"""
        for belief in self._belief_cache:
            if belief.belief_id == belief_id:
                old_conf = belief.confidence
                belief.update_confidence(feedback)
                
                # 记录历史
                conn = self._get_conn()
                conn.execute(
                    """INSERT INTO belief_history 
                       (history_id, belief_id, old_confidence, new_confidence, feedback, reason, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4())[:8], belief_id, old_conf, belief.confidence, 
                     int(feedback), reason, time.time())
                )
                conn.commit()
                conn.close()
                
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
    
    def _goal_to_desire(self, goal: Any) -> Desire:
        """将目标映射为愿望"""
        priority = 0.5
        persistence = "transient"
        
        if hasattr(goal, "priority"):
            p = goal.priority
            if p >= 4:
                priority = 0.9
                persistence = "urgent"
            elif p >= 2:
                priority = 0.6
                persistence = "transient"
            else:
                priority = 0.3
                persistence = "persistent"
        
        description = goal.description if hasattr(goal, "description") else str(goal)
        goal_id = goal.goal_id if hasattr(goal, "goal_id") else str(uuid.uuid4())[:8]
        
        return Desire(
            desire_id=f"desire_{goal_id}",
            description=description,
            priority=priority,
            source="goal_manager",
            persistence=persistence,
        )
    
    # ========== 意图选择 ==========
    
    def select_intention(self, candidate_plans: List[Dict]) -> Tuple[Optional[Dict], List[Intention]]:
        """
        从候选计划中选择最佳意图
        
        防御性处理：
        - candidate_plans为空 → 返回(None, [])
        - 信念/愿望为空 → 使用默认值评分
        - 评分失败 → 跳过该候选，不中断整体流程
        """
        # === 防御：空输入 ===
        if not candidate_plans:
            return None, []
        
        # 过滤非法候选
        valid_plans = [p for p in candidate_plans if isinstance(p, dict)]
        if not valid_plans:
            return None, []
        
        # 加载信念和愿望（带异常捕获）
        try:
            beliefs = self.load_beliefs()
        except Exception:
            beliefs = []
        
        try:
            desires = self.load_desires(self._get_active_goals())
        except Exception:
            desires = []
        
        # 评分所有候选计划（单个失败不影响其他）
        intentions = []
        for plan in valid_plans:
            try:
                intention = self._score_plan(plan, beliefs, desires)
                intentions.append(intention)
            except Exception:
                continue
        
        if not intentions:
            # 全部评分失败 → 回退到第一个候选
            return valid_plans[0], []
        
        # 排序选最高
        intentions.sort(key=lambda x: x.bdi_score, reverse=True)
        
        intentions[0].selected = True
        intentions[0].status = "pending"
        
        # 持久化（失败不阻塞）
        try:
            self._save_intention(intentions[0])
        except Exception:
            pass
        
        # 找到对应的原计划
        selected_plan = valid_plans[0]
        for i, plan in enumerate(valid_plans):
            if plan.get("plan_id") == intentions[0].plan_id:
                selected_plan = plan
                break
        
        return selected_plan, intentions
    
    def _score_plan(self, plan: Dict, beliefs: List[Belief], desires: List[Desire]) -> Intention:
        """评分计划"""
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
    
    def _score_belief_alignment(self, plan: Dict, beliefs: List[Belief]) -> float:
        """计算计划与信念的匹配度"""
        if not beliefs:
            return 0.5
        
        plan_desc = plan.get("description", "") + " " + str(plan.get("steps", []))
        plan_desc = plan_desc.lower()
        
        scores = []
        for belief in beliefs:
            # 简单关键词匹配
            obj = belief.object.lower()
            pred = belief.predicate.lower()
            
            match_score = 0.0
            if obj in plan_desc:
                match_score = 0.8
            elif pred in plan_desc:
                match_score = 0.5
            
            # 置信度加权
            weighted = match_score * belief.to_planning_weight()
            scores.append(weighted)
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _score_desire_alignment(self, plan: Dict, desires: List[Desire]) -> float:
        """计算计划与愿望的匹配度"""
        if not desires:
            return 0.5
        
        plan_desc = plan.get("description", "").lower()
        plan_steps = str(plan.get("steps", [])).lower()
        
        scores = []
        for desire in desires:
            desc = desire.description.lower()
            weight = desire.to_planning_weight()
            
            # 关键词匹配
            match = 0.3
            if any(kw in plan_desc or kw in plan_steps for kw in desc.split()):
                match = 0.8
            
            scores.append(match * weight)
        
        return min(1.0, sum(scores) / len(scores)) if scores else 0.5
    
    def _score_personality_bonus(self, plan: Dict) -> float:
        """人格特质加成"""
        weights = self._apply_dynamic_rules(self.personality_weights)
        if not weights:
            return 0.5
        
        plan_desc = plan.get("description", "").lower()
        steps = str(plan.get("steps", [])).lower()
        
        bonus = 0.5
        
        # guardian特质
        if "guardian" in weights:
            gw = weights["guardian"].get("weights", {})
            if "help_user" in plan_desc or "assist" in plan_desc:
                bonus += (gw.get("help_user", 1.0) - 1.0) * 0.3
            if "quick" in plan_desc or "fast" in plan_desc:
                bonus += (gw.get("protect_time", 1.0) - 1.0) * 0.2
        
        # signal_goblin特质
        if "signal_goblin" in weights:
            sw = weights["signal_goblin"].get("weights", {})
            if "fast_response" in plan_desc or "immediate" in plan_desc:
                bonus += (sw.get("fast_response", 1.0) - 1.0) * 0.3
        
        # curious特质
        if "curious" in weights:
            cw = weights["curious"].get("weights", {})
            if "explore" in plan_desc or "research" in plan_desc or "analyze" in steps:
                bonus += (cw.get("explore_new", 1.0) - 1.0) * 0.2
        
        return min(1.0, max(0.0, bonus))
    
    def _get_active_goals(self) -> List[Any]:
        """获取活跃目标（占位，实际从GoalManager获取）"""
        return []
    
    # ========== 意图生命周期 ==========
    
    def _save_intention(self, intention: Intention):
        """保存意图到数据库"""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO intentions
               (intention_id, plan_id, plan_description, bdi_score, belief_alignment,
                desire_alignment, personality_bonus, selected, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (intention.intention_id, intention.plan_id, intention.plan_description,
             intention.bdi_score, intention.belief_alignment, intention.desire_alignment,
             intention.personality_bonus, int(intention.selected), intention.status,
             intention.created_at)
        )
        conn.commit()
        conn.close()
    
    def activate_intention(self, intention_id: str) -> bool:
        """激活意图"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE intentions SET status='active', activated_at=? WHERE intention_id=?",
            (time.time(), intention_id)
        )
        conn.commit()
        conn.close()
        return True
    
    def complete_intention(self, intention_id: str, success: bool, reason: str = "") -> bool:
        """完成意图"""
        status = "succeeded" if success else "failed"
        conn = self._get_conn()
        conn.execute(
            """UPDATE intentions SET status=?, completed_at=?, failure_reason=?
               WHERE intention_id=?""",
            (status, time.time(), reason, intention_id)
        )
        conn.commit()
        conn.close()
        return True
    
    def get_active_intentions(self) -> List[Intention]:
        """获取活跃意图"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM intentions WHERE status='active' ORDER BY created_at DESC"
        )
        intentions = []
        for row in cursor.fetchall():
            intentions.append(self._row_to_intention(row))
        conn.close()
        return intentions
    
    def explain_decision(self, intention: Intention) -> str:
        """解释决策理由"""
        return (
            f"选择 '{intention.plan_description}' 是因为：\n"
            f"  - 信念匹配度: {intention.belief_alignment:.2f}\n"
            f"  - 愿望匹配度: {intention.desire_alignment:.2f}\n"
            f"  - 人格加成: {intention.personality_bonus:.2f}\n"
            f"  - BDI总分: {intention.bdi_score:.2f}"
        )
    
    def _row_to_intention(self, row) -> Intention:
        """数据库行转Intention"""
        return Intention(
            intention_id=row["intention_id"],
            plan_id=row["plan_id"],
            plan_description=row["plan_description"],
            bdi_score=row["bdi_score"],
            belief_alignment=row["belief_alignment"],
            desire_alignment=row["desire_alignment"],
            personality_bonus=row["personality_bonus"],
            selected=bool(row["selected"]),
            status=row["status"],
            created_at=row["created_at"],
            activated_at=row["activated_at"],
            completed_at=row["completed_at"],
            failure_reason=row["failure_reason"],
        )


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== BDIEngine v2.0 Test ===")
    
    bdi = BDIEngine()
    
    # 测试1：信念缓存
    beliefs = bdi.load_beliefs()
    print(f"Test1: Loaded {len(beliefs)} beliefs from cache")
    
    # 测试2：愿望生成
    class MockGoal:
        def __init__(self):
            self.goal_id = "test_001"
            self.description = "帮朋朋写代码"
            self.priority = 3
    
    desires = bdi.load_desires([MockGoal()])
    print(f"Test2: Generated {len(desires)} desires")
    for d in desires:
        print(f"  - {d.description}: priority={d.priority}, persistence={d.persistence}")
    
    # 测试3：意图选择
    plans = [
        {"plan_id": "p1", "description": "快速简洁回答", "steps": ["respond"]},
        {"plan_id": "p2", "description": "详细分析并给出多方案", "steps": ["analyze", "compare", "recommend"]},
    ]
    
    selected, all_intentions = bdi.select_intention(plans)
    print(f"Test3: Selected plan: {selected['description'] if selected else 'None'}")
    print(f"  All intentions scored:")
    for i in all_intentions:
        print(f"    - {i.plan_description}: BDI={i.bdi_score:.2f} (belief={i.belief_alignment:.2f}, desire={i.desire_alignment:.2f}, personality={i.personality_bonus:.2f})")
    
    # 测试4：决策解释
    if all_intentions:
        explanation = bdi.explain_decision(all_intentions[0])
        print(f"Test4: Decision explanation:")
        print(explanation)
    
    # 测试5：意图生命周期
    if all_intentions:
        bdi.activate_intention(all_intentions[0].intention_id)
        print(f"Test5: Activated intention {all_intentions[0].intention_id}")
        
        active = bdi.get_active_intentions()
        print(f"  Active intentions: {len(active)}")
    
    print("\n✅ BDIEngine v2.0 ready")
