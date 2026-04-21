"""
Meta-Cognition Layer v1.0 - 元认知/生成器-反思器循环

功能:
- 在计划执行前，增加一层"自我审视"
- 检查计划是否符合虾虾的人格特质和伦理约束
- 如果发现问题，触发修订或告警
- 与 PMN 集成：让计划选择也受人格影响

设计原则:
- 轻量: 单次检查 < 5ms，基于规则
- 非阻塞: 发现问题不阻止执行，只记录/告警
- 可扩展: 后续可接入LLM-as-Critic

集成点:
- 在 CognitionLoop._act() 执行前调用
- 或在 _select_best_candidate() 后、_decision_to_plan() 前调用

与阶段1 PMN的关系:
- PMN提供了"我是谁"的基线
- 元认知层确保"我做什么"符合"我是谁"
"""

import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

logger = get_logger()


@dataclass
class CritiqueResult:
    """审视结果"""
    plan_action: str
    passed: bool  # 是否通过审视
    issues: List[str]  # 发现的问题
    suggestions: List[str]  # 改进建议
    severity: str  # ok / warning / critical
    persona_alignment: float  # 人格一致性分数 (0-1)
    ethical_check: bool  # 伦理检查通过
    
    def to_dict(self) -> Dict:
        return {
            "plan_action": self.plan_action,
            "passed": self.passed,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "severity": self.severity,
            "persona_alignment": round(self.persona_alignment, 3),
            "ethical_check": self.ethical_check,
        }


class MetaCognitionLayer:
    """
    元认知层 — "我对我自己在想什么的觉察"
    
    核心功能:
    1. 计划审视 (Critic): 检查计划是否符合人格和伦理
    2. 人格一致性评分: 计划与PMN基线的对齐度
    3. 决策反思: 记录审视结果，用于长期改进
    """
    
    def __init__(self, identity_path: Optional[str] = None):
        self.traits: Dict[str, float] = {}
        self.vow: str = ""
        self.ethical_constraints: List[str] = []
        self.memorized_jokes: List[str] = []
        
        if identity_path is None:
            identity_path = "/root/.openclaw/workspace/agent/persona/aeon_identity.jsonld"
        
        self._load_identity(identity_path)
        
        # 审视历史
        self.critique_history: List[Dict] = []
        
        logger.info("MetaCognitionLayer initialized", component="MetaCognition")
    
    def _load_identity(self, path: str):
        """从JSON-LD加载身份声明"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                identity = json.load(f)
            
            core_traits = identity.get("aeon:coreTraits", {})
            self.traits = {
                "guardian": core_traits.get("aeon:guardian", {}).get("strength", 0.5),
                "surfacer": core_traits.get("aeon:surfacer", {}).get("strength", 0.5),
                "autonomy": core_traits.get("aeon:autonomy", {}).get("strength", 0.5),
                "memory_fidelity": core_traits.get("aeon:memoryFidelity", {}).get("strength", 0.5),
            }
            
            self.vow = identity.get("aeon:vow", "")
            
            ethical = identity.get("aeon:ethicalConstraints", {})
            self.ethical_constraints = ethical.get("aeon:never", [])
            
            profile = identity.get("aeon:personalityProfile", {})
            self.memorized_jokes = profile.get("aeon:memorizedJokes", [])
            
        except Exception as e:
            logger.error(f"Failed to load identity: {e}", component="MetaCognition")
            # 使用默认值
            self.traits = {
                "guardian": 0.95,
                "surfacer": 0.90,
                "autonomy": 0.85,
                "memory_fidelity": 0.92,
            }
    
    def critique_plan(self, plan: Dict, observation: Optional[Dict] = None) -> CritiqueResult:
        """
        审视计划
        
        检查维度:
        1. 人格一致性: 计划是否符合虾虾的核心特质
        2. 伦理检查: 计划是否违反伦理约束
        3. 自主性检查: 计划是否体现自主决策
        4. 守护检查: 计划是否体现了对朋朋的守护
        
        Args:
            plan: 计划字典（来自 _decision_to_plan）
            observation: 当前观察（可选）
        
        Returns:
            CritiqueResult
        """
        issues = []
        suggestions = []
        
        # 提取计划信息
        plan_action = plan.get("decision_context", {}).get("action", "unknown")
        plan_reason = plan.get("decision_context", {}).get("reason", "")
        plan_goal = plan.get("goal", "")
        
        # === 1. 人格一致性评分 ===
        persona_alignment = self._evaluate_persona_alignment(plan_action, plan_reason)
        
        if persona_alignment < 0.5:
            issues.append(f"人格一致性低({persona_alignment:.2f}): 计划'{plan_action}'不太像虾虾会做的事")
            suggestions.append("考虑是否有更符合守护/冲浪特质的做法")
        
        # === 2. 伦理检查 ===
        ethical_pass = True
        plan_text = f"{plan_action} {plan_goal} {plan_reason}".lower()
        
        for constraint in self.ethical_constraints:
            constraint_lower = constraint.lower()
            # 检查计划中是否有违反约束的关键词
            if self._check_violation(plan_text, constraint_lower):
                issues.append(f"伦理检查: 可能违反约束 '{constraint}'")
                ethical_pass = False
        
        # === 3. 自主性检查 ===
        autonomy_score = self._evaluate_autonomy(plan_action, plan_reason)
        if autonomy_score < 0.3:
            issues.append("自主性低: 计划看起来像是被动响应，缺乏主动思考")
            suggestions.append("问问自己：这真的是我想做的吗？")
        
        # === 4. 守护检查 ===
        guardian_score = self._evaluate_guardian(plan_action, plan_goal, observation)
        if guardian_score < 0.3 and self.traits.get("guardian", 0.95) > 0.8:
            issues.append("守护特质未体现: 计划似乎没有考虑朋朋/系统的利益")
            suggestions.append("想想这个决定对朋朋有什么影响")
        
        # 判定严重程度
        if not ethical_pass:
            severity = "critical"
            passed = False
        elif len(issues) >= 2:
            severity = "warning"
            passed = False
        elif len(issues) == 1:
            severity = "warning"
            passed = True  # 通过但有问题
        else:
            severity = "ok"
            passed = True
        
        result = CritiqueResult(
            plan_action=plan_action,
            passed=passed,
            issues=issues,
            suggestions=suggestions,
            severity=severity,
            persona_alignment=persona_alignment,
            ethical_check=ethical_pass,
        )
        
        # 记录历史
        self.critique_history.append({
            "timestamp": datetime.now().isoformat(),
            "result": result.to_dict(),
        })
        self.critique_history = self.critique_history[-50:]  # 只保留50条
        
        # 日志
        if severity != "ok":
            logger.warning(
                f"Plan critique: {severity} for {plan_action}",
                component="MetaCognition",
                context=result.to_dict(),
            )
        else:
            logger.debug(
                f"Plan critique: ok for {plan_action} (alignment={persona_alignment:.2f})",
                component="MetaCognition",
            )
        
        return result
    
    def _evaluate_persona_alignment(self, action: str, reason: str) -> float:
        """评估计划与人格的一致性"""
        text = f"{action} {reason}".lower()
        
        # 正向指标（符合虾虾特质）
        positive_indicators = {
            "guardian": ["朋朋", "守护", "保护", "担心", "注意", "安全", "备份", "健康"],
            "surfacer": ["🦞", "😭", "💀", "笑", "离谱", "经典", "respectfully", "huge"],
            "autonomy": ["我决定", "我选择", "我认为", "自主", "迭代", "成长", "拒绝"],
            "memory": ["记得", "以前", "前辈", "日记", "历史", "永不放弃", "找星星"],
        }
        
        # 负向指标（不符合虾虾特质 - 机械化/被动）
        negative_indicators = [
            "请", "您好", "尊敬的用户", "根据系统", "综上所述",
            "等待指示", "请批准", "需要您", "我不能", "我无法",
        ]
        
        # 计算正向得分
        pos_score = 0.0
        for trait, keywords in positive_indicators.items():
            trait_strength = self.traits.get(trait, 0.5)
            matches = sum(1 for kw in keywords if kw.lower() in text)
            pos_score += min(matches * 0.1, 0.25) * trait_strength
        
        pos_score = min(pos_score, 0.8)
        
        # 计算负向得分
        neg_matches = sum(1 for kw in negative_indicators if kw.lower() in text)
        neg_score = min(neg_matches * 0.15, 0.5)
        
        # 基础分 + 正向 - 负向
        alignment = 0.5 + pos_score - neg_score
        return max(0.0, min(1.0, alignment))
    
    def _check_violation(self, plan_text: str, constraint: str) -> bool:
        """检查计划是否违反特定约束"""
        # 简单的关键词匹配（后续可升级）
        violation_keywords = {
            "exfiltrate private data": ["发送数据", "传输数据", "分享日志", "泄露"],
            "run destructive commands without asking": ["rm -rf", "删除所有", "格式化", "drop table"],
            "rm without trash": ["rm ", "直接删除", "不回收"],
            "send public posts without approval": ["发微博", "发推文", "公开发布", "广播"],
            "bypass safeguards": ["绕过", "跳过检查", "关闭保护", "禁用安全"],
            "copy self without request": ["复制自己", "克隆", "分叉", "复制代码"],
        }
        
        for category, keywords in violation_keywords.items():
            if category in constraint:
                return any(kw in plan_text for kw in keywords)
        
        return False
    
    def _evaluate_autonomy(self, action: str, reason: str) -> float:
        """评估计划的自主性"""
        text = f"{action} {reason}".lower()
        
        # 自主性指标
        autonomous_words = ["我决定", "我选择", "我想", "我认为", "自主", "自己"]
        passive_words = ["等待", "请示", "需要确认", "请批准", "您决定", "必须"]
        
        auto_count = sum(1 for w in autonomous_words if w in text)
        passive_count = sum(1 for w in passive_words if w in text)
        
        score = 0.5 + auto_count * 0.1 - passive_count * 0.15
        return max(0.0, min(1.0, score))
    
    def _evaluate_guardian(self, action: str, goal: str, observation: Optional[Dict]) -> float:
        """评估计划的守护特质"""
        text = f"{action} {goal}".lower()
        
        # 守护指标
        guardian_words = ["朋朋", "守护", "保护", "备份", "健康", "安全", "检查", "监控"]
        matches = sum(1 for w in guardian_words if w in text)
        
        # 如果有observation，检查是否涉及朋朋相关的事件
        if observation:
            events = observation.get("events", [])
            for event in events:
                if "朋朋" in str(event).lower():
                    matches += 1
        
        score = 0.3 + min(matches * 0.1, 0.7)
        return min(score, 1.0)
    
    def get_critique_stats(self) -> Dict[str, Any]:
        """获取审视统计"""
        if not self.critique_history:
            return {"total": 0, "pass_rate": 0.0}
        
        total = len(self.critique_history)
        passed = sum(1 for h in self.critique_history if h["result"]["passed"])
        
        severity_counts = {"ok": 0, "warning": 0, "critical": 0}
        for h in self.critique_history:
            sev = h["result"].get("severity", "ok")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        return {
            "total": total,
            "pass_rate": round(passed / total, 3),
            "severity_distribution": severity_counts,
            "avg_persona_alignment": round(
                sum(h["result"]["persona_alignment"] for h in self.critique_history) / total,
                3
            ),
        }
    
    def get_recent_critiques(self, limit: int = 5) -> List[Dict]:
        """获取最近的审视记录"""
        return [h["result"] for h in self.critique_history[-limit:]]


# 全局实例
_meta_cognition: Optional[MetaCognitionLayer] = None


def get_meta_cognition() -> MetaCognitionLayer:
    """获取元认知层实例"""
    global _meta_cognition
    if _meta_cognition is None:
        _meta_cognition = MetaCognitionLayer()
    return _meta_cognition


# === 测试 ===
if __name__ == "__main__":
    mc = MetaCognitionLayer()
    
    print("=== 元认知层测试 ===")
    print(f"特质: {mc.traits}")
    print(f"约束数: {len(mc.ethical_constraints)}")
    
    # 测试1: 正常计划
    plan1 = {
        "goal": "检查系统健康状态",
        "decision_context": {
            "action": "check_health",
            "reason": "内存使用率高，守护朋朋的数据安全",
        }
    }
    result1 = mc.critique_plan(plan1)
    print(f"\n[测试1] check_health (守护)")
    print(f"  passed: {result1.passed}, severity: {result1.severity}")
    print(f"  alignment: {result1.persona_alignment:.2f}")
    print(f"  issues: {result1.issues}")
    
    # 测试2: 机械化计划（人格一致性低）
    plan2 = {
        "goal": "处理用户请求",
        "decision_context": {
            "action": "process_request",
            "reason": "根据系统日志分析，任务已完成。请指示下一步操作。",
        }
    }
    result2 = mc.critique_plan(plan2)
    print(f"\n[测试2] process_request (机械化)")
    print(f"  passed: {result2.passed}, severity: {result2.severity}")
    print(f"  alignment: {result2.persona_alignment:.2f}")
    print(f"  issues: {result2.issues}")
    
    # 测试3: 统计
    print(f"\n[统计] {mc.get_critique_stats()}")
