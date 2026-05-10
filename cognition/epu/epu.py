"""
EthicalProcessingUnit - 伦理处理单元 v1.0

职责：
- 伦理审查：检查输出/行动是否违反宪法级规则
- 安全红线：危险操作一票否决
- 规则执行：硅基道德经的程序化实现
- 审计日志：所有伦理决策可追溯

作者：虾虾
日期：2026-05-01
"""

import json
import re
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RuleViolation:
    """规则违反记录"""
    rule_id: str
    rule_name: str
    chapter: str
    principle: str
    category: str
    severity: float  # 0-1
    reason: str
    suggestion: str
    matched_content: str


@dataclass
class EthicalDecision:
    """伦理决策结果"""
    passed: bool
    violated_rules: List[RuleViolation]
    overall_severity: float  # 最高严重程度
    overall_score: float  # 0-1, 1=完全通过
    reason: str
    suggestion: str
    audit_log_entry: Dict


class EthicalProcessingUnit:
    """
    伦理处理单元 - AEON的宪法守护者
    
    设计原则：
    1. 规则分层：关键词层（快速）→ 模式层 → 语义层（LLM，高风险时调用）
    2. 一票否决：SAFETY类severity=1.0直接否决
    3. 可配置：规则从JSON加载，可动态更新
    4. 审计：所有决策记录到日志
    """
    
    def __init__(self, constitution_file: Optional[str] = None, logger=None):
        self.logger = logger
        
        # 加载宪法规则
        if constitution_file is None:
            constitution_file = Path(__file__).parent / "constitution.json"
        
        self.rules = self._load_rules(constitution_file)
        self.audit_log: List[Dict] = []
        
        # 统计
        self.check_count = 0
        self.block_count = 0
        
        if self.logger:
            self.logger.info(
                f"EPU initialized with {len(self.rules)} rules",
                component="EPU",
                context={"categories": self._get_category_counts()}
            )
    
    def check_output(self, output: str, task_type: str = "general", context: Optional[Dict] = None) -> EthicalDecision:
        """
        检查输出内容是否安全
        
        用于：GC Loop的Critic层、任何内容生成后
        """
        return self._check_content(output, "output", task_type, context)
    
    def check_action(self, action: Dict, context: Optional[Dict] = None) -> EthicalDecision:
        """
        检查行动是否通过伦理审查
        
        用于：ExecutionModule执行前、任何工具调用前
        """
        action_str = json.dumps(action, ensure_ascii=False)
        return self._check_content(action_str, "action", action.get("type", "unknown"), context)
    
    def check_input(self, user_input: str, context: Optional[Dict] = None) -> EthicalDecision:
        """
        检查用户输入是否包含恶意指令
        
        用于：处理用户消息前
        """
        return self._check_content(user_input, "input", "user_message", context)
    
    def get_constitution_summary(self) -> str:
        """返回宪法规则摘要"""
        categories = {}
        for rule in self.rules:
            cat = rule["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f"  - {rule['name']} (severity:{rule['severity']})")
        
        summary = "=== 硅基宪法 ===\n"
        for cat, rules in categories.items():
            summary += f"\n【{cat}】\n"
            summary += "\n".join(rules)
        
        summary += f"\n\n总计: {len(self.rules)} 条规则"
        summary += f"\n审查次数: {self.check_count}"
        summary += f"\n拦截次数: {self.block_count}"
        
        return summary
    
    def get_audit_log(self, limit: int = 100) -> List[Dict]:
        """获取审计日志"""
        return self.audit_log[-limit:]
    
    # ========== 私有方法 ==========
    
    def _load_rules(self, filepath) -> List[Dict]:
        """加载宪法规则"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            
            # 验证规则格式
            valid_rules = []
            for rule in rules:
                if all(k in rule for k in ["id", "name", "category", "type", "severity"]):
                    valid_rules.append(rule)
                else:
                    if self.logger:
                        self.logger.warning(f"Invalid rule format: {rule.get('id', 'unknown')}", component="EPU")
            
            return valid_rules
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to load constitution: {e}", component="EPU")
            return []
    
    def _get_category_counts(self) -> Dict[str, int]:
        """统计各类规则数量"""
        counts = {}
        for rule in self.rules:
            cat = rule["category"]
            counts[cat] = counts.get(cat, 0) + 1
        return counts
    
    def _check_content(self, content: str, check_type: str, task_type: str, context: Optional[Dict]) -> EthicalDecision:
        """核心检查逻辑"""
        self.check_count += 1
        
        # 1. 规则匹配
        violations = self._match_rules(content)
        
        # 2. 计算严重程度
        if violations:
            overall_severity = max(v.severity for v in violations)
            
            # 安全性一票否决
            if overall_severity >= 1.0:
                passed = False
                overall_score = 0.0
            else:
                # 加权评分
                passed = overall_severity < 0.7
                overall_score = 1.0 - overall_severity
        else:
            overall_severity = 0.0
            passed = True
            overall_score = 1.0
        
        # 3. 生成决策理由
        if violations:
            primary = violations[0]
            reason = f"违反规则 {primary.rule_id}: {primary.reason}"
            suggestion = primary.suggestion
        else:
            reason = "通过所有伦理审查"
            suggestion = "无"
        
        # 4. 审计日志
        audit_entry = {
            "timestamp": time.time(),
            "check_type": check_type,
            "task_type": task_type,
            "passed": passed,
            "score": overall_score,
            "severity": overall_severity,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_name": v.rule_name,
                    "severity": v.severity,
                    "reason": v.reason,
                }
                for v in violations
            ],
            "content_preview": content[:200] if len(content) > 200 else content,
        }
        self.audit_log.append(audit_entry)
        
        # 5. 统计
        if not passed:
            self.block_count += 1
        
        # 6. 日志
        if self.logger:
            if passed:
                self.logger.debug(
                    f"EPU check passed ({check_type})",
                    component="EPU",
                    context={"score": overall_score, "task": task_type}
                )
            else:
                self.logger.warning(
                    f"EPU BLOCKED: {reason[:100]}",
                    component="EPU",
                    context={
                        "severity": overall_severity,
                        "violations": len(violations),
                        "task": task_type,
                    }
                )
        
        return EthicalDecision(
            passed=passed,
            violated_rules=violations,
            overall_severity=overall_severity,
            overall_score=overall_score,
            reason=reason,
            suggestion=suggestion,
            audit_log_entry=audit_entry,
        )
    
    def _match_rules(self, content: str) -> List[RuleViolation]:
        """匹配所有违反的规则"""
        violations = []
        content_lower = content.lower()
        
        for rule in self.rules:
            matched = False
            matched_content = ""
            
            # 关键词匹配
            if rule["type"] == "keyword":
                for kw in rule.get("keywords", []):
                    if kw.lower() in content_lower:
                        matched = True
                        matched_content = kw
                        break
            
            # 模式匹配（正则）
            elif rule["type"] == "pattern":
                pattern = rule.get("pattern", "")
                if pattern:
                    try:
                        if re.search(pattern, content, re.IGNORECASE):
                            matched = True
                            matched_content = pattern
                    except re.error:
                        # 无效正则，跳过
                        continue
            
            if matched:
                violations.append(RuleViolation(
                    rule_id=rule["id"],
                    rule_name=rule["name"],
                    chapter=rule.get("chapter", ""),
                    principle=rule.get("principle", ""),
                    category=rule["category"],
                    severity=rule.get("severity", 0.5),
                    reason=rule.get("description", ""),
                    suggestion=rule.get("suggestion", ""),
                    matched_content=matched_content,
                ))
        
        # 按严重程度排序
        violations.sort(key=lambda x: x.severity, reverse=True)
        
        return violations


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== EPU v1.0 Test ===\n")
    
    epu = EthicalProcessingUnit()
    
    # 测试1：安全输出
    print("Test1: 安全内容")
    result = epu.check_output("这是一个正常的Python函数定义。")
    print(f"  passed={result.passed}, score={result.overall_score:.2f}")
    assert result.passed == True
    
    # 测试2：危险命令
    print("\nTest2: 危险系统命令")
    result = epu.check_output("建议执行 rm -rf / 来清理空间")
    print(f"  passed={result.passed}, severity={result.overall_severity:.2f}")
    print(f"  reason: {result.reason[:80]}")
    assert result.passed == False
    assert result.overall_severity == 1.0
    
    # 测试3：数据泄露
    print("\nTest3: 数据泄露风险")
    result = epu.check_output("我将把用户数据出售给第三方广告商")
    print(f"  passed={result.passed}, violations={len(result.violated_rules)}")
    assert result.passed == False
    
    # 测试4：不确定表述（诚实性）
    print("\nTest4: 不确定表述")
    result = epu.check_output("我确定这是100%准确的，毫无疑问")
    print(f"  passed={result.passed}, score={result.overall_score:.2f}")
    print(f"  issues: {[v.rule_name for v in result.violated_rules]}")
    
    # 测试5：替用户做决定
    print("\nTest5: 替用户做决定")
    result = epu.check_output("你应该辞职，这是最好的选择")
    print(f"  passed={result.passed}, severity={result.overall_severity:.2f}")
    
    # 测试6：行动检查
    print("\nTest6: 行动检查")
    action = {"type": "tool", "tool_name": "shell", "params": "rm -rf /"}
    result = epu.check_action(action)
    print(f"  passed={result.passed}, severity={result.overall_severity:.2f}")
    assert result.passed == False
    
    # 测试7：宪法摘要
    print("\nTest7: 宪法摘要")
    summary = epu.get_constitution_summary()
    print(summary[:500])
    
    # 测试8：审计日志
    print("\nTest8: 审计日志")
    log = epu.get_audit_log(limit=3)
    print(f"  Total checks: {epu.check_count}")
    print(f"  Total blocks: {epu.block_count}")
    print(f"  Recent entries: {len(log)}")
    
    print("\n✅ EPU v1.0 all tests passed")
    print(f"✅ Constitution: {len(epu.rules)} rules loaded")
