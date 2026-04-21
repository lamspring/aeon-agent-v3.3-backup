"""
Experience Logger v1.0 - 经验记录器（客观+主观+身体）

功能:
- 记录每次任务的客观结果（成功/失败/超时）
- 记录虾虾的主观体验（信心/挫败感/满足感）
- 记录执行时的身体状态（token消耗/响应时间/错误数）
- 提供历史查询，供LATS评分使用
- 触发潜意识信号（强烈情绪时）

设计原则:
- 最简版本：先能用，再完善
- 主观字段可选：不强制填写，但鼓励记录
- 自动采集身体数据：不需要手动输入
- 触发潜意识：frustration_peak > 0.7 时广播

与CognitionLoop的集成:
- 在 _act() 执行后调用 log_experience()
- 在 _reflect() 中调用 log_subjective()
- 在 LATS _score_candidate() 中查询历史成功率
"""

import json
import os
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

logger = get_logger()


class ExperienceRecord:
    """单条经验记录"""
    
    def __init__(
        self,
        task_id: str,
        task_desc: str,
        action: str,
        success: bool,
        duration_ms: int = 0,
        attempts: int = 1,
        subjective: Optional[Dict] = None,
        body: Optional[Dict] = None,
        context: Optional[Dict] = None,
    ):
        self.task_id = task_id
        self.task_desc = task_desc
        self.action = action
        self.success = success
        self.duration_ms = duration_ms
        self.attempts = attempts
        self.subjective = subjective or {}
        self.body = body or {}
        self.context = context or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "task_desc": self.task_desc,
            "action": self.action,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "subjective": self.subjective,
            "body": self.body,
            "context": self.context,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ExperienceRecord":
        record = cls(
            task_id=data["task_id"],
            task_desc=data["task_desc"],
            action=data["action"],
            success=data["success"],
            duration_ms=data.get("duration_ms", 0),
            attempts=data.get("attempts", 1),
            subjective=data.get("subjective"),
            body=data.get("body"),
            context=data.get("context"),
        )
        record.timestamp = data.get("timestamp", record.timestamp)
        return record


class ExperienceLogger:
    """
    经验记录器
    
    存储路径: /root/.openclaw/workspace/agent/memory/experiences/
    文件名: YYYY-MM-DD.jsonl（每天一个文件，JSON Lines格式）
    
    查询接口:
    - get_success_rate(action): 某动作的历史成功率
    - get_recent_experiences(limit): 最近N条记录
    - get_experiences_by_action(action): 某动作的所有记录
    - get_emotional_summary(): 情绪统计
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            storage_dir = "/root/.openclaw/workspace/agent/memory/experiences"
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存（最近100条）
        self._cache: List[ExperienceRecord] = []
        self._cache_limit = 100
        
        # 统计缓存
        self._stats_cache: Optional[Dict] = None
        self._stats_cache_time: float = 0
        
        logger.info(f"ExperienceLogger initialized: {self.storage_dir}", component="ExperienceLogger")
    
    def _get_today_file(self) -> Path:
        """获取今天的存储文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.storage_dir / f"{today}.jsonl"
    
    def log(
        self,
        task_id: str,
        task_desc: str,
        action: str,
        success: bool,
        duration_ms: int = 0,
        attempts: int = 1,
        subjective: Optional[Dict] = None,
        body: Optional[Dict] = None,
        context: Optional[Dict] = None,
    ) -> ExperienceRecord:
        """
        记录一次经验
        
        使用示例:
        ```python
        logger.log(
            task_id="fix_001",
            task_desc="修复ShadowOperation",
            action="shell_exec",
            success=True,
            duration_ms=300000,
            attempts=2,
            subjective={
                "confidence_at_start": 0.3,
                "frustration_peak": 0.8,
                "satisfaction_at_end": 0.9,
                "what_i_learned": "sed要加-i",
            },
            body={
                "token_cost": 1500,
                "response_time_ms": 8000,
                "error_count": 3,
            }
        )
        ```
        """
        record = ExperienceRecord(
            task_id=task_id,
            task_desc=task_desc,
            action=action,
            success=success,
            duration_ms=duration_ms,
            attempts=attempts,
            subjective=subjective,
            body=body,
            context=context,
        )
        
        # 写入文件
        self._append_to_file(record)
        
        # 更新缓存
        self._cache.append(record)
        if len(self._cache) > self._cache_limit:
            self._cache = self._cache[-self._cache_limit:]
        
        # 触发潜意识信号（强烈情绪）
        self._maybe_broadcast_to_shadow(record)
        
        # 清除统计缓存
        self._stats_cache = None
        
        logger.debug(
            f"Experience logged: {action} → {'success' if success else 'fail'}",
            component="ExperienceLogger",
            context={"task_id": task_id, "duration_ms": duration_ms}
        )
        
        return record
    
    def _append_to_file(self, record: ExperienceRecord):
        """追加到文件"""
        file_path = self._get_today_file()
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to write experience: {e}", component="ExperienceLogger")
    
    def _maybe_broadcast_to_shadow(self, record: ExperienceRecord):
        """
        如果挫败感过高，向潜意识广播信号
        
        触发条件:
        - frustration_peak > 0.7
        - 或 attempts > 3（反复失败）
        """
        subjective = record.subjective or {}
        frustration = subjective.get("frustration_peak", 0)
        attempts = record.attempts
        
        if frustration > 0.7 or attempts > 3:
            # 广播到潜意识（如果有的话）
            try:
                self._broadcast_shadow(record, frustration, attempts)
            except Exception as e:
                logger.debug(f"Shadow broadcast failed: {e}", component="ExperienceLogger")
    
    def _broadcast_shadow(self, record: ExperienceRecord, frustration: float, attempts: int):
        """向潜意识广播"""
        # TODO: 接入真正的潜意识系统
        # 现在先记录到日志
        logger.warning(
            f"Shadow signal: high frustration({frustration}) or repeated failures({attempts})",
            component="ExperienceLogger",
            context={
                "task_id": record.task_id,
                "action": record.action,
                "frustration": frustration,
                "attempts": attempts,
            }
        )
    
    # === 查询接口 ===
    
    def get_success_rate(self, action: Optional[str] = None, min_samples: int = 5) -> Optional[float]:
        """
        获取某动作的历史成功率
        
        Args:
            action: 动作类型，None表示全部
            min_samples: 最少样本数，不足返回None
        
        Returns:
            成功率 (0-1)，或 None（样本不足）
        """
        records = self._load_all_records()
        
        if action:
            records = [r for r in records if r.action == action]
        
        if len(records) < min_samples:
            return None
        
        successes = sum(1 for r in records if r.success)
        return round(successes / len(records), 3)
    
    def get_recent_experiences(self, limit: int = 10, action: Optional[str] = None) -> List[ExperienceRecord]:
        """获取最近N条记录"""
        records = self._load_all_records()
        
        if action:
            records = [r for r in records if r.action == action]
        
        # 按时间倒序
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records[:limit]
    
    def get_experiences_by_action(self, action: str) -> List[ExperienceRecord]:
        """获取某动作的所有记录"""
        records = self._load_all_records()
        return [r for r in records if r.action == action]
    
    def get_emotional_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        情绪统计摘要
        
        Returns:
            {
                "avg_confidence": 0.6,
                "avg_frustration": 0.3,
                "avg_satisfaction": 0.8,
                "strong_emotion_count": 2,
                "recent_mood": "positive"  # positive / neutral / negative
            }
        """
        records = self._load_all_records()
        
        # 过滤最近N天
        # 简化处理：取最近50条
        recent = records[-50:] if len(records) > 50 else records
        
        confidences = []
        frustrations = []
        satisfactions = []
        strong_emotions = 0
        
        for r in recent:
            sub = r.subjective or {}
            if "confidence_at_start" in sub:
                confidences.append(sub["confidence_at_start"])
            if "frustration_peak" in sub:
                frustrations.append(sub["frustration_peak"])
                if sub["frustration_peak"] > 0.7:
                    strong_emotions += 1
            if "satisfaction_at_end" in sub:
                satisfactions.append(sub["satisfaction_at_end"])
        
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
        avg_frus = sum(frustrations) / len(frustrations) if frustrations else 0.0
        avg_sat = sum(satisfactions) / len(satisfactions) if satisfactions else 0.5
        
        # 判断最近情绪
        if avg_sat > 0.6 and avg_frus < 0.3:
            mood = "positive"
        elif avg_frus > 0.5 or strong_emotions >= 2:
            mood = "negative"
        else:
            mood = "neutral"
        
        return {
            "avg_confidence": round(avg_conf, 2),
            "avg_frustration": round(avg_frus, 2),
            "avg_satisfaction": round(avg_sat, 2),
            "strong_emotion_count": strong_emotions,
            "recent_mood": mood,
            "sample_count": len(recent),
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        # 检查缓存
        if self._stats_cache and time.time() - self._stats_cache_time < 60:
            return self._stats_cache
        
        records = self._load_all_records()
        
        if not records:
            return {"total": 0, "success_rate": 0.0}
        
        total = len(records)
        successes = sum(1 for r in records if r.success)
        
        # 按动作分组统计
        action_stats = {}
        for r in records:
            act = r.action
            if act not in action_stats:
                action_stats[act] = {"total": 0, "successes": 0}
            action_stats[act]["total"] += 1
            if r.success:
                action_stats[act]["successes"] += 1
        
        # 计算每个动作的成功率
        for act, stat in action_stats.items():
            stat["success_rate"] = round(stat["successes"] / stat["total"], 3)
        
        stats = {
            "total": total,
            "success_rate": round(successes / total, 3),
            "action_breakdown": action_stats,
            "has_subjective_data": any(r.subjective for r in records),
            "has_body_data": any(r.body for r in records),
        }
        
        self._stats_cache = stats
        self._stats_cache_time = time.time()
        
        return stats
    
    def _load_all_records(self) -> List[ExperienceRecord]:
        """加载所有记录（从文件+缓存合并）"""
        records = []
        
        # 从文件加载
        for file_path in sorted(self.storage_dir.glob("*.jsonl")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            records.append(ExperienceRecord.from_dict(data))
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}", component="ExperienceLogger")
        
        # 合并缓存（缓存可能包含未写入文件的最新记录）
        if self._cache:
            # 去重：基于task_id
            existing_ids = {r.task_id for r in records}
            for cached in self._cache:
                if cached.task_id not in existing_ids:
                    records.append(cached)
        
        # 按时间排序
        records.sort(key=lambda r: r.timestamp)
        return records
    
    # === CognitionLoop 集成辅助 ===
    
    def log_from_cognition(
        self,
        plan: Dict,
        result: Dict,
        subjective: Optional[Dict] = None,
    ) -> ExperienceRecord:
        """
        从CognitionLoop的plan和result记录经验
        
        自动提取客观数据，主观数据需传入
        """
        decision = plan.get("decision_context", {})
        
        # 自动采集身体数据
        body = {
            "token_cost": result.get("token_cost", 0),
            "response_time_ms": result.get("response_time_ms", 0),
            "error_count": result.get("error_count", 0),
        }
        
        return self.log(
            task_id=plan.get("plan_id", f"task_{int(time.time())}"),
            task_desc=plan.get("goal", "unknown"),
            action=decision.get("action", "unknown"),
            success=result.get("success", False),
            duration_ms=result.get("duration_ms", 0),
            attempts=result.get("attempts", 1),
            subjective=subjective,
            body=body,
            context={
                "plan_type": plan.get("type"),
                "priority": decision.get("priority"),
            }
        )


# 全局实例
_experience_logger: Optional[ExperienceLogger] = None


def get_experience_logger() -> ExperienceLogger:
    """获取全局经验记录器"""
    global _experience_logger
    if _experience_logger is None:
        _experience_logger = ExperienceLogger()
    return _experience_logger


# === 测试 ===
if __name__ == "__main__":
    print("=== ExperienceLogger 测试 ===")
    
    # 使用临时目录测试
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    el = ExperienceLogger(tmp_dir)
    
    # 测试1: 基础记录
    print("\n[测试1] 基础记录")
    r1 = el.log(
        task_id="fix_001",
        task_desc="修复ShadowOperation",
        action="shell_exec",
        success=True,
        duration_ms=300000,
        attempts=2,
    )
    print(f"  记录: {r1.action} → {'success' if r1.success else 'fail'}")
    
    # 测试2: 带主观体验
    print("\n[测试2] 带主观体验")
    r2 = el.log(
        task_id="explore_001",
        task_desc="探索OpenAkita",
        action="web_fetch",
        success=False,
        duration_ms=5000,
        attempts=1,
        subjective={
            "confidence_at_start": 0.8,
            "frustration_peak": 0.2,
            "satisfaction_at_end": 0.3,
            "what_i_learned": "API额度不够，需要等重置",
        },
        body={
            "token_cost": 800,
            "response_time_ms": 3000,
            "error_count": 1,
        }
    )
    print(f"  记录: {r2.action} → {'success' if r2.success else 'fail'}")
    print(f"  主观: confidence={r2.subjective.get('confidence_at_start')}")
    
    # 测试3: 高挫败感（触发潜意识信号）
    print("\n[测试3] 高挫败感")
    r3 = el.log(
        task_id="debug_001",
        task_desc="调试循环检测bug",
        action="code_debug",
        success=False,
        duration_ms=600000,
        attempts=5,
        subjective={
            "confidence_at_start": 0.4,
            "frustration_peak": 0.85,  # > 0.7，触发shadow
            "satisfaction_at_end": 0.1,
            "what_i_learned": "逻辑比想象中复杂",
        },
    )
    print(f"  记录: {r3.action} → {'success' if r3.success else 'fail'}")
    print(f"  frustration={r3.subjective.get('frustration_peak')} (应该触发shadow)")
    
    # 测试4: 统计查询
    print("\n[测试4] 统计查询")
    stats = el.get_stats()
    print(f"  总记录: {stats['total']}")
    print(f"  成功率: {stats['success_rate']}")
    print(f"  动作分布: {list(stats['action_breakdown'].keys())}")
    
    # 测试5: 情绪摘要
    print("\n[测试5] 情绪摘要")
    emotion = el.get_emotional_summary()
    print(f"  平均信心: {emotion['avg_confidence']}")
    print(f"  平均挫败: {emotion['avg_frustration']}")
    print(f"  平均满足: {emotion['avg_satisfaction']}")
    print(f"  最近情绪: {emotion['recent_mood']}")
    print(f"  强烈情绪次数: {emotion['strong_emotion_count']}")
    
    # 测试6: 成功率查询
    print("\n[测试6] 成功率查询")
    sr = el.get_success_rate("shell_exec", min_samples=1)
    print(f"  shell_exec成功率: {sr}")
    sr_all = el.get_success_rate(min_samples=1)
    print(f"  总体成功率: {sr_all}")
    
    # 测试7: CognitionLoop集成
    print("\n[测试7] CognitionLoop集成")
    plan = {
        "plan_id": "plan_123",
        "goal": "检查系统健康",
        "type": "maintenance",
        "decision_context": {
            "action": "check_health",
            "priority": "high",
        }
    }
    result = {
        "success": True,
        "token_cost": 500,
        "response_time_ms": 2000,
        "error_count": 0,
        "duration_ms": 30000,
    }
    r7 = el.log_from_cognition(plan, result, subjective={
        "confidence_at_start": 0.9,
        "satisfaction_at_end": 0.95,
    })
    print(f"  自动记录: {r7.action} → {'success' if r7.success else 'fail'}")
    print(f"  身体数据: tokens={r7.body.get('token_cost')}")
    
    # 清理
    import shutil
    shutil.rmtree(tmp_dir)
    
    print("\n✅ 所有测试通过")
