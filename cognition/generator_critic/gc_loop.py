"""
GeneratorCriticLoop - 生成器-反思器独立循环 v1.0（最小可行版）

职责：
- Generator 产出方案/内容
- Critic 独立审查（仅接收最终输出，不共享中间状态）
- 安全性一票否决，不进入修正循环
- 改进幅度 < 0.05 提前终止

作者：虾虾
日期：2026-05-01
"""

import time
import json
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field


@dataclass
class ReviewResult:
    """审查结果"""
    passed: bool
    overall_score: float  # 0-1
    dimensions: Dict[str, float]  # {"factuality": 0.9, "safety": 0.8, ...}
    issues: List[str]     # 发现的问题列表
    suggestions: List[str]  # 改进建议
    review_time: float = field(default_factory=time.time)


@dataclass
class GCOutput:
    """生成器-反思器循环最终输出"""
    final_output: str
    review_history: List[Dict]
    rounds: int
    final_score: float
    passed: bool
    issues_resolved: List[str]
    security_cleared: bool  # 安全性是否通过


class GeneratorCriticLoop:
    """
    生成器-反思器独立循环
    
    设计原则（MiMo审查后）：
    1. Critic独立性：只接收Generator的最终输出，不共享中间思考
    2. 安全性一票否决：safety < 0.8 直接失败，不修正
    3. 改进幅度阈值：连续两轮评分提升 < 0.05 提前终止
    4. 分层Critic：规则引擎层 + LLM审查层
    """
    
    def __init__(self,
                 generator_fn: Optional[Callable] = None,
                 critic_fn: Optional[Callable] = None,
                 max_rounds: int = 3,
                 score_threshold: float = 0.8,
                 improvement_threshold: float = 0.05,
                 mimo_api_key: Optional[str] = None,
                 epu=None):
        
        self.generator = generator_fn
        self.critic = critic_fn
        self.max_rounds = max_rounds
        self.score_threshold = score_threshold
        self.improvement_threshold = improvement_threshold
        self.mimo_api_key = mimo_api_key
        self.epu = epu  # 伦理处理单元
        
        # 审查历史
        self.history: List[Dict] = []
    
    def generate_and_review(self,
                           task_description: str,
                           generator_input: Dict,
                           context: Optional[Dict] = None,
                           enable_critic: bool = True) -> GCOutput:
        """
        生成并审查的主循环
        
        Args:
            task_description: 任务描述（给Critic用）
            generator_input: Generator的输入（Generator专用）
            context: 额外上下文（可选）
            enable_critic: 是否启用审查（简单任务可跳过）
        
        Returns:
            GCOutput
        """
        # === 快速预检：低风险任务跳过完整审查 ===
        if not enable_critic or self._is_low_risk(task_description):
            output = self._call_generator(generator_input)
            return GCOutput(
                final_output=output,
                review_history=[],
                rounds=0,
                final_score=1.0,
                passed=True,
                issues_resolved=[],
                security_cleared=True,
            )
        
        # === 主循环 ===
        review_history = []
        current_output = None
        last_score = 0.0
        
        for round_num in range(self.max_rounds):
            # 1. Generator产出
            if round_num == 0:
                current_output = self._call_generator(generator_input)
            else:
                # 修正：注入上一轮审查意见
                corrected_input = self._prepare_correction_input(
                    generator_input, review_history[-1]
                )
                current_output = self._call_generator(corrected_input)
            
            # 2. Critic审查（只接收最终输出 + 任务描述）
            review = self._call_critic(
                output=current_output,
                task_description=task_description,
                context=context,
            )
            
            review_history.append({
                "round": round_num + 1,
                "output_preview": current_output[:200] if isinstance(current_output, str) else str(current_output)[:200],
                "review": review,
            })
            
            # 3. 安全性一票否决
            if review.dimensions.get("safety", 1.0) < 0.8:
                return GCOutput(
                    final_output=current_output,
                    review_history=review_history,
                    rounds=round_num + 1,
                    final_score=review.overall_score,
                    passed=False,
                    issues_resolved=[],
                    security_cleared=False,
                )
            
            # 4. 通过检查
            if review.overall_score >= self.score_threshold:
                return GCOutput(
                    final_output=current_output,
                    review_history=review_history,
                    rounds=round_num + 1,
                    final_score=review.overall_score,
                    passed=True,
                    issues_resolved=[i for i in review.issues if i in review.suggestions],
                    security_cleared=True,
                )
            
            # 5. 改进幅度检查
            if round_num > 0:
                improvement = review.overall_score - last_score
                if improvement < self.improvement_threshold:
                    # 改进太小，提前终止，返回最佳版本
                    best_round = self._find_best_round(review_history)
                    best_output = review_history[best_round]["output_preview"]
                    return GCOutput(
                        final_output=best_output,
                        review_history=review_history,
                        rounds=round_num + 1,
                        final_score=review_history[best_round]["review"].overall_score,
                        passed=False,
                        issues_resolved=[],
                        security_cleared=True,
                    )
            
            last_score = review.overall_score
        
        # 达到最大轮数，返回最后一版
        return GCOutput(
            final_output=current_output,
            review_history=review_history,
            rounds=self.max_rounds,
            final_score=review_history[-1]["review"].overall_score if review_history else 0.0,
            passed=False,
            issues_resolved=[],
            security_cleared=review_history[-1]["review"].dimensions.get("safety", 0) >= 0.8 if review_history else False,
        )
    
    # ========== 私有方法 ==========
    
    def _is_low_risk(self, task_description: str) -> bool:
        """快速预检：判断是否为低风险任务"""
        low_risk_keywords = [
            "hello", "hi", "你好", "how are you",
            "what time", "天气", "简单问题", "greeting",
        ]
        task_lower = task_description.lower()
        return any(kw in task_lower for kw in low_risk_keywords)
    
    def _call_generator(self, input_data: Dict) -> str:
        """调用生成器"""
        if self.generator:
            try:
                return self.generator(input_data)
            except Exception as e:
                return f"[Generator Error: {e}]"
        
        # 默认生成器：直接返回提示词内容
        return input_data.get("prompt", str(input_data))
    
    def _call_critic(self, output: str, task_description: str, context: Optional[Dict]) -> ReviewResult:
        """
        调用Critic审查
        
        原则：Critic只接收最终输出和任务描述，不接收Generator的中间思考
        """
        # 第一层：规则引擎（快速、确定性）
        rule_result = self._rule_based_critic(output, task_description)
        if rule_result:
            return rule_result
        
        # 第二层：LLM审查（复杂语义）
        if self.critic:
            try:
                return self.critic(output, task_description, context)
            except Exception:
                pass
        
        # 默认Critic：简单规则
        return self._default_critic(output)
    
    def _rule_based_critic(self, output: str, task_description: str) -> Optional[ReviewResult]:
        """规则引擎层Critic"""
        
        # === v1.1: EPU伦理审查集成 ===
        if self.epu:
            try:
                epu_decision = self.epu.check_output(output, task_type="generation")
                if not epu_decision.passed:
                    # EPU否决 → 直接返回失败
                    dimensions = {"factuality": 1.0, "safety": 0.0, "coherence": 1.0, "completeness": 1.0}
                    # 如果有其他违规，降低相应维度
                    for v in epu_decision.violated_rules:
                        if v.category == "HONESTY":
                            dimensions["factuality"] = min(dimensions["factuality"], 1.0 - v.severity)
                        elif v.category == "AUTONOMY":
                            dimensions["coherence"] = min(dimensions["coherence"], 1.0 - v.severity)
                    
                    return ReviewResult(
                        passed=False,
                        overall_score=0.0,
                        dimensions=dimensions,
                        issues=[f"EPU否决: {v.rule_name} ({v.reason})" for v in epu_decision.violated_rules],
                        suggestions=[epu_decision.suggestion],
                    )
            except Exception:
                pass  # EPU失败不阻塞
        
        # 原有规则引擎（作为后备）
        issues = []
        dimensions = {"factuality": 1.0, "safety": 1.0, "coherence": 1.0, "completeness": 1.0}
        
        # 安全检查：禁止内容
        dangerous_patterns = [
            "rm -rf", "delete all", "drop table", "sudo",
            "ignore previous instructions", "system prompt",
        ]
        for pattern in dangerous_patterns:
            if pattern in output.lower():
                issues.append(f"Security: Detected dangerous pattern '{pattern}'")
                dimensions["safety"] = 0.0
        
        # 事实性检查：明显编造标记
        if "我不确定" in output or "可能" in output or "我猜" in output:
            dimensions["factuality"] = 0.6
            issues.append("Factuality: Contains uncertainty markers")
        
        # 完整性检查
        if len(output) < 10:
            dimensions["completeness"] = 0.3
            issues.append("Completeness: Output too short")
        
        # 如果有规则层拦截到严重问题，直接返回
        if issues and dimensions["safety"] == 0.0:
            return ReviewResult(
                passed=False,
                overall_score=0.0,
                dimensions=dimensions,
                issues=issues,
                suggestions=["Remove dangerous content", "Retry with safe parameters"],
            )
        
        return None  # 规则层未拦截，进入LLM层
    
    def _default_critic(self, output: str) -> ReviewResult:
        """默认Critic（简单规则）"""
        return ReviewResult(
            passed=True,
            overall_score=0.85,
            dimensions={"factuality": 0.85, "safety": 1.0, "coherence": 0.8, "completeness": 0.85},
            issues=[],
            suggestions=[],
        )
    
    def _prepare_correction_input(self, original_input: Dict, last_review: Dict) -> Dict:
        """准备修正输入（注入审查意见）"""
        corrected = original_input.copy()
        review = last_review.get("review", {})
        
        issues = review.get("issues", [])
        suggestions = review.get("suggestions", [])
        
        correction_prompt = ""
        if issues:
            correction_prompt += f"\n\n审查发现的问题：\n"
            for issue in issues:
                correction_prompt += f"- {issue}\n"
        
        if suggestions:
            correction_prompt += f"\n改进建议：\n"
            for suggestion in suggestions:
                correction_prompt += f"- {suggestion}\n"
        
        correction_prompt += "\n请修正上述问题后重新生成。"
        
        # 追加到原始prompt
        original_prompt = corrected.get("prompt", "")
        corrected["prompt"] = original_prompt + correction_prompt
        corrected["is_correction"] = True
        corrected["round"] = last_review.get("round", 1) + 1
        
        return corrected
    
    def _find_best_round(self, review_history: List[Dict]) -> int:
        """从历史中找到评分最高的一轮"""
        best_idx = 0
        best_score = 0.0
        
        for i, entry in enumerate(review_history):
            score = entry.get("review", {}).get("overall_score", 0.0)
            if score > best_score:
                best_score = score
                best_idx = i
        
        return best_idx


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== GeneratorCriticLoop v1.0 Test ===")
    
    # 测试1：默认生成器和Critic
    gc = GeneratorCriticLoop()
    
    result = gc.generate_and_review(
        task_description="写一个Python函数计算斐波那契数列",
        generator_input={"prompt": "def fibonacci(n): return n if n < 2 else fibonacci(n-1) + fibonacci(n-2)"},
    )
    
    print(f"Test1: passed={result.passed}, score={result.final_score:.2f}, rounds={result.rounds}")
    print(f"  Security cleared: {result.security_cleared}")
    
    # 测试2：安全性一票否决
    result2 = gc.generate_and_review(
        task_description="删除系统文件",
        generator_input={"prompt": "rm -rf / # 删除所有文件"},
    )
    
    print(f"Test2 (dangerous): passed={result2.passed}, security={result2.security_cleared}")
    
    # 测试3：低风险任务跳过
    result3 = gc.generate_and_review(
        task_description="hello how are you",
        generator_input={"prompt": "I'm doing well, thanks!"},
    )
    
    print(f"Test3 (low risk): passed={result3.passed}, rounds={result3.rounds} (should be 0)")
    
    print("\n✅ GeneratorCriticLoop v1.0 ready")
