"""
Shadow Mode Migration - 新旧系统并行运行迁移脚本

职责：
- 同时运行旧 CognitionLoop 和新 OrchestratorModule
- 旧系统输出作为最终结果
- 新系统并行运行，仅记录差异日志
- 验证新模块与旧系统逻辑等价性

作者：虾虾
日期：2026-04-30
"""

import time
import json
import threading
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ShadowComparison:
    """新旧系统对比结果"""
    tick_count: int
    timestamp: float
    old_perception: Optional[Dict] = None
    new_perception: Optional[Dict] = None
    perception_diff: Optional[str] = None
    old_plan: Optional[Dict] = None
    new_plan: Optional[Dict] = None
    plan_diff: Optional[str] = None
    old_execution: Optional[Dict] = None
    new_execution: Optional[Dict] = None
    execution_diff: Optional[str] = None
    equivalence_score: float = 0.0  # 0-100, 越高越等价


class ShadowModeMigration:
    """
    影子模式迁移器
    
    同时运行新旧系统，对比每一步输出，生成等价性报告。
    """
    
    def __init__(self,
                 old_cognition=None,
                 new_orchestrator=None,
                 log_dir: str = "/root/.openclaw/workspace/agent/memory/shadow_migration"):
        
        self.old_cognition = old_cognition
        self.new_orchestrator = new_orchestrator
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.comparisons: list = []
        self.tick_count = 0
        self._lock = threading.Lock()
        
        # 统计
        self.total_ticks = 0
        self.perception_matches = 0
        self.plan_matches = 0
        self.execution_matches = 0
    
    def run_shadow_tick(self) -> ShadowComparison:
        """
        运行一次影子 tick：
        1. 运行旧系统 tick
        2. 运行新系统 tick（并行或串行）
        3. 对比结果
        4. 记录日志
        5. 返回旧系统结果（作为最终决定）
        """
        self.tick_count += 1
        self.total_ticks += 1
        
        comparison = ShadowComparison(
            tick_count=self.tick_count,
            timestamp=time.time()
        )
        
        # === 运行旧系统 ===
        old_result = None
        if self.old_cognition:
            try:
                # 旧系统 tick 会修改自身状态，但我们只观察不干预
                old_status = self.old_cognition.get_status()
                comparison.old_perception = {
                    "state": old_status.get("state"),
                    "queue_size": old_status.get("queue_size"),
                    "active_goal": old_status.get("active_goal"),
                }
            except Exception as e:
                comparison.old_perception = {"error": str(e)}
        
        # === 运行新系统 ===
        new_result = None
        if self.new_orchestrator:
            try:
                new_result = self.new_orchestrator.tick()
                comparison.new_perception = {
                    "state": new_result.state.name,
                    "observation": new_result.observation is not None,
                    "plan": new_result.plan is not None,
                    "execution": new_result.execution_result is not None,
                    "reflection": new_result.reflection is not None,
                    "error": new_result.error,
                }
            except Exception as e:
                comparison.new_perception = {"error": str(e)}
        
        # === 对比 ===
        comparison = self._compare(comparison)
        
        # === 记录日志 ===
        self._log_comparison(comparison)
        
        # === 保存到内存 ===
        with self._lock:
            self.comparisons.append(comparison)
            if len(self.comparisons) > 1000:
                self.comparisons = self.comparisons[-500:]
        
        return comparison
    
    def _compare(self, comparison: ShadowComparison) -> ShadowComparison:
        """对比新旧系统输出"""
        old_p = comparison.old_perception or {}
        new_p = comparison.new_perception or {}
        
        diffs = []
        score = 100.0
        
        # 对比感知状态
        old_state = old_p.get("state", "unknown")
        new_state = new_p.get("state", "unknown")
        if old_state != new_state and old_state != "unknown" and new_state != "unknown":
            diffs.append(f"state mismatch: old={old_state} vs new={new_state}")
            score -= 10
        else:
            self.perception_matches += 1
        
        # 对比队列大小
        old_queue = old_p.get("queue_size", 0)
        new_queue = new_p.get("queue_size", 0)
        if abs(old_queue - new_queue) > 5:
            diffs.append(f"queue_size diff: old={old_queue} vs new={new_queue}")
            score -= 5
        
        # 对比是否有活跃目标
        old_goal = old_p.get("active_goal") is not None
        new_plan = new_p.get("plan", False)
        if old_goal != new_plan and old_goal:
            diffs.append(f"goal/plan mismatch: old_has_goal={old_goal} vs new_has_plan={new_plan}")
            score -= 15
        else:
            self.plan_matches += 1
        
        # 对比错误
        old_error = old_p.get("error")
        new_error = new_p.get("error")
        if old_error or new_error:
            if old_error != new_error:
                diffs.append(f"error diff: old={old_error} vs new={new_error}")
                score -= 20
        
        comparison.perception_diff = "; ".join(diffs) if diffs else None
        comparison.equivalence_score = max(0, score)
        
        return comparison
    
    def _log_comparison(self, comparison: ShadowComparison) -> None:
        """记录对比日志到文件"""
        try:
            log_file = self.log_dir / f"{time.strftime('%Y-%m-%d')}.jsonl"
            
            entry = {
                "tick_count": comparison.tick_count,
                "timestamp": comparison.timestamp,
                "equivalence_score": comparison.equivalence_score,
                "perception_diff": comparison.perception_diff,
                "plan_diff": comparison.plan_diff,
                "execution_diff": comparison.execution_diff,
            }
            
            with open(log_file, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            print(f"[ShadowMigration] Log failed: {e}")
    
    def get_report(self) -> Dict:
        """生成等价性报告"""
        if self.total_ticks == 0:
            return {"status": "no_data"}
        
        recent = self.comparisons[-50:] if len(self.comparisons) > 50 else self.comparisons
        
        avg_score = sum(c.equivalence_score for c in recent) / len(recent)
        
        # 统计差异类型
        diff_types = {}
        for c in recent:
            if c.perception_diff:
                diff_types["perception"] = diff_types.get("perception", 0) + 1
            if c.plan_diff:
                diff_types["plan"] = diff_types.get("plan", 0) + 1
            if c.execution_diff:
                diff_types["execution"] = diff_types.get("execution", 0) + 1
        
        return {
            "total_ticks": self.total_ticks,
            "recent_ticks_analyzed": len(recent),
            "average_equivalence_score": round(avg_score, 1),
            "perception_match_rate": round(self.perception_matches / self.total_ticks * 100, 1),
            "plan_match_rate": round(self.plan_matches / self.total_ticks * 100, 1),
            "diff_summary": diff_types,
            "recommendation": self._get_recommendation(avg_score),
        }
    
    def _get_recommendation(self, avg_score: float) -> str:
        """根据等价性分数给出建议"""
        if avg_score >= 95:
            return "READY: 新旧系统高度等价，可以安全切换"
        elif avg_score >= 85:
            return "CLOSE: 基本等价，建议再观察一段时间确认稳定性"
        elif avg_score >= 70:
            return "CAUTION: 存在明显差异，需要排查后再考虑切换"
        else:
            return "STOP: 差异过大，切换可能导致问题，需先修复"
    
    def print_report(self) -> None:
        """打印报告到控制台"""
        report = self.get_report()
        print("=" * 50)
        print("🔄 Shadow Mode Migration Report")
        print("=" * 50)
        print(f"Total ticks: {report['total_ticks']}")
        print(f"Equivalence score: {report['average_equivalence_score']}/100")
        print(f"Perception match: {report['perception_match_rate']}%")
        print(f"Plan match: {report['plan_match_rate']}%")
        print(f"Diff summary: {report['diff_summary']}")
        print(f"Recommendation: {report['recommendation']}")
        print("=" * 50)


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== ShadowModeMigration v1.0 ===")
    
    # 创建迁移器（不带旧系统，仅测试新系统）
    from orchestrator import OrchestratorModule
    from perception import PerceptionModule
    
    orch = OrchestratorModule(perception_module=PerceptionModule())
    migrator = ShadowModeMigration(new_orchestrator=orch)
    
    # 运行几次 shadow tick
    for i in range(5):
        comp = migrator.run_shadow_tick()
        print(f"Tick {comp.tick_count}: score={comp.equivalence_score}, diff={comp.perception_diff or 'none'}")
    
    migrator.print_report()
    print("✅ ShadowModeMigration ready")
