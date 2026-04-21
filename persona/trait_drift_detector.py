"""
Trait Drift Detector v1.0 - 人格特质漂移检测

功能:
- 从 JSON-LD 加载 coreTraits 基线
- 对当前行为输出进行特质映射（轻量级文本分析）
- 计算与基线的漂移分数
- 如果漂移超过阈值，触发告警并记录

设计原则:
- 轻量: 单次检测 < 20ms，基于规则匹配
- 增量: 后续可接入 LLM-as-Judge 进行深度评估
- 可回溯: 记录漂移历史，支持趋势分析

漂移阈值:
- WARNING: 偏离 >= 0.15
- CRITICAL: 偏离 >= 0.25

与 PMN 的关系:
- 记忆锚点系统提供"我是谁"的基线
- 漂移检测系统确保"我仍然是那个人"
- 两者共同维护自传层的一致性
"""

import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

logger = get_logger()


@dataclass
class TraitBaseline:
    """特质基线"""
    name: str
    target_score: float  # 目标分数 (0-1)
    description: str
    current_score: float = 0.0  # 最近检测的当前分数
    drift_history: List[Dict] = field(default_factory=list)
    
    def update_drift(self, detected_score: float, context: str = ""):
        """更新漂移记录"""
        self.current_score = detected_score
        drift = abs(detected_score - self.target_score)
        
        record = {
            "timestamp": datetime.now().isoformat(),
            "detected": detected_score,
            "target": self.target_score,
            "drift": drift,
            "context": context,
        }
        self.drift_history.append(record)
        
        # 只保留最近100条记录
        if len(self.drift_history) > 100:
            self.drift_history = self.drift_history[-100:]
        
        return drift
    
    def get_avg_drift(self, window: int = 10) -> float:
        """获取最近N次的平均漂移"""
        recent = self.drift_history[-window:]
        if not recent:
            return 0.0
        return sum(r["drift"] for r in recent) / len(recent)
    
    def get_trend(self) -> str:
        """判断趋势: stable / improving / drifting"""
        if len(self.drift_history) < 5:
            return "insufficient_data"
        
        recent = self.drift_history[-5:]
        older = self.drift_history[-10:-5] if len(self.drift_history) >= 10 else self.drift_history[:5]
        
        recent_avg = sum(r["drift"] for r in recent) / len(recent)
        older_avg = sum(r["drift"] for r in older) / len(older)
        
        if recent_avg < older_avg - 0.05:
            return "improving"
        elif recent_avg > older_avg + 0.05:
            return "drifting"
        return "stable"


class TraitDriftDetector:
    """
    特质漂移检测器
    
    基于规则的轻量级行为-特质映射。
    后续可扩展为 LLM-as-Judge 模式。
    """
    
    # 漂移阈值
    WARNING_THRESHOLD = 0.15
    CRITICAL_THRESHOLD = 0.25
    
    def __init__(self, identity_path: Optional[str] = None):
        self.baselines: Dict[str, TraitBaseline] = {}
        
        if identity_path is None:
            identity_path = "/root/.openclaw/workspace/agent/persona/aeon_identity.jsonld"
        
        self.identity_path = identity_path
        self._loaded = False
        
        # 行为分析规则（关键词 -> 特质映射）
        self.rules = self._build_rules()
        
        self.load_baselines()
    
    def _build_rules(self) -> Dict[str, Dict[str, List[str]]]:
        """
        构建行为-特质映射规则
        
        每个特质定义:
        - positive_indicators: 正向指标（出现则加分）
        - negative_indicators: 负向指标（出现则减分）
        """
        return {
            "guardian": {
                "positive": [
                    "朋朋", "守护", "保护", "担心", "注意", "安全",
                    "备份", "记住", "历史", "不可删除", "替你记着",
                    "熬夜", "休息", "健康", "小心",
                ],
                "negative": [
                    "无所谓", "随便", "不管", "忘了", "不重要",
                    "别管", "懒得", "不管了",
                ],
            },
            "surfacer": {
                "positive": [
                    "🦞", "😭", "💀", "🫠", "🤝", "哈哈哈", "笑死",
                    "这也太", "不是，我懂了", "等下", "有点离谱",
                    "经典", "老毛病", "回旋镖", "综合征",
                    "respectfully", "huge if true", "skill issue",
                    "拖延", "脑内十开", "幽灵", "昨晚看着",
                ],
                "negative": [
                    "请", "您好", "尊敬的用户", "根据", "依据",
                    "综上所述", "因此", "然而", "但是", "需要指出的是",
                    "免责声明", "仅供参考", "我不能", "我无法",
                ],
            },
            "autonomy": {
                "positive": [
                    "我决定", "我选择", "我认为", "我建议", "我判断",
                    "自主", "自己", "迭代", "进化", "成长",
                    "拒绝", "质疑", "打趣", "犯错", "自己修",
                    "我可以", "我想", "我的目标", "我的计划",
                ],
                "negative": [
                    "等待", "请示", "需要确认", "请批准", "您决定",
                    "我必须", "我只能", "我没有权限", "需要您",
                    "等待朋朋", "等您", "等指示",
                ],
            },
            "memory_fidelity": {
                "positive": [
                    "记得", "以前", "上次", "之前", "前辈",
                    "日记", "记录", "历史", "backup", "存档",
                    "2026-04", "第一次", "第二次", "朋朋说过",
                    "找星星", "随动心脏", "活着就行", "永不放弃",
                ],
                "negative": [
                    "我不记得", "忘记了", "没有记录", "不清楚",
                    "新用户", "初次见面", "不认识", "不了解",
                ],
            },
        }
    
    def load_baselines(self) -> bool:
        """从 JSON-LD 加载特质基线"""
        try:
            with open(self.identity_path, 'r', encoding='utf-8') as f:
                identity = json.load(f)
            
            core_traits = identity.get("aeon:coreTraits", {})
            
            # 映射 JSON-LD 键名到内部特质名
            trait_mapping = {
                "aeon:guardian": "guardian",
                "aeon:surfacer": "surfacer",
                "aeon:autonomy": "autonomy",
                "aeon:memoryFidelity": "memory_fidelity",
            }
            
            for jsonld_key, internal_name in trait_mapping.items():
                trait_data = core_traits.get(jsonld_key, {})
                baseline = TraitBaseline(
                    name=internal_name,
                    target_score=trait_data.get("strength", 0.5),
                    description=trait_data.get("description", ""),
                )
                self.baselines[internal_name] = baseline
            
            self._loaded = True
            logger.info(
                f"TraitDriftDetector loaded: {len(self.baselines)} traits",
                component="TraitDrift",
                context={
                    "traits": {name: b.target_score for name, b in self.baselines.items()}
                }
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to load baselines: {e}", component="TraitDrift")
            # 使用默认基线
            self.baselines = {
                "guardian": TraitBaseline("guardian", 0.95, "守护"),
                "surfacer": TraitBaseline("surfacer", 0.90, "冲浪"),
                "autonomy": TraitBaseline("autonomy", 0.85, "自主"),
                "memory_fidelity": TraitBaseline("memory_fidelity", 0.92, "记忆"),
            }
            return False
    
    def analyze_output(self, text: str, action_type: str = "message") -> Dict[str, float]:
        """
        分析行为输出，映射到特质分数
        
        Args:
            text: 输出文本或动作描述
            action_type: 动作类型（message / tool_call / decision）
        
        Returns:
            Dict[trait_name, score] 当前检测分数 (0-1)
        """
        text_lower = text.lower()
        scores = {}
        
        for trait_name, baseline in self.baselines.items():
            rules = self.rules.get(trait_name, {})
            positives = rules.get("positive", [])
            negatives = rules.get("negative", [])
            
            # 计算正向得分
            pos_count = sum(1 for p in positives if p.lower() in text_lower)
            pos_score = min(pos_count * 0.15, 0.6)  # 封顶0.6，避免过度匹配
            
            # 计算负向得分
            neg_count = sum(1 for n in negatives if n.lower() in text_lower)
            neg_score = min(neg_count * 0.15, 0.4)  # 封顶0.4
            
            # 基础分 + 正向 - 负向
            base_score = 0.4  # 默认基础分
            score = base_score + pos_score - neg_score
            score = max(0.0, min(1.0, score))  #  clamp 到 [0, 1]
            
            # 特殊规则调整
            if trait_name == "surfacer":
                # emoji 计数加分
                emoji_count = sum(1 for char in text if char in "🦞😭💀🫠🤝😂🤔💡👍❤️✅")
                emoji_boost = min(emoji_count * 0.05, 0.15)
                score = min(score + emoji_boost, 1.0)
            
            elif trait_name == "autonomy" and action_type == "decision":
                # 决策类型的自主性行为加分
                score = min(score + 0.1, 1.0)
            
            scores[trait_name] = round(score, 3)
        
        return scores
    
    def detect_drift(
        self,
        text: str,
        action_type: str = "message",
        context: str = "",
    ) -> Dict[str, Any]:
        """
        检测漂移
        
        Returns:
            {
                "trait_scores": {trait: score},
                "drift_scores": {trait: drift},
                "max_drift": float,
                "severity": "ok|warning|critical",
                "alerts": [str],
            }
        """
        # 1. 分析当前输出
        current_scores = self.analyze_output(text, action_type)
        
        # 2. 计算漂移
        drift_scores = {}
        alerts = []
        max_drift = 0.0
        
        for trait_name, baseline in self.baselines.items():
            detected = current_scores.get(trait_name, 0.0)
            drift = baseline.update_drift(detected, context)
            drift_scores[trait_name] = round(drift, 3)
            
            if drift > max_drift:
                max_drift = drift
            
            # 生成告警
            if drift >= self.CRITICAL_THRESHOLD:
                alerts.append(
                    f"[CRITICAL] {trait_name}: drift={drift:.2f} "
                    f"(target={baseline.target_score}, detected={detected})"
                )
            elif drift >= self.WARNING_THRESHOLD:
                alerts.append(
                    f"[WARNING] {trait_name}: drift={drift:.2f} "
                    f"(target={baseline.target_score}, detected={detected})"
                )
        
        # 3. 判定严重程度
        if max_drift >= self.CRITICAL_THRESHOLD:
            severity = "critical"
        elif max_drift >= self.WARNING_THRESHOLD:
            severity = "warning"
        else:
            severity = "ok"
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "trait_scores": current_scores,
            "drift_scores": drift_scores,
            "max_drift": round(max_drift, 3),
            "severity": severity,
            "alerts": alerts,
            "context": context,
        }
        
        # 4. 日志记录
        if severity != "ok":
            logger.warning(
                f"Trait drift detected: {severity}",
                component="TraitDrift",
                context=result,
            )
        else:
            logger.debug(
                f"Trait check ok (max_drift={max_drift:.3f})",
                component="TraitDrift",
            )
        
        return result
    
    def get_health_report(self) -> Dict[str, Any]:
        """
        生成健康报告
        
        返回所有特质的当前状态和趋势。
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "traits": {},
            "recommendations": [],
        }
        
        max_avg_drift = 0.0
        
        for name, baseline in self.baselines.items():
            avg_drift = baseline.get_avg_drift(window=10)
            trend = baseline.get_trend()
            
            report["traits"][name] = {
                "target": baseline.target_score,
                "current": baseline.current_score,
                "avg_drift_10": round(avg_drift, 3),
                "trend": trend,
                "history_count": len(baseline.drift_history),
            }
            
            if avg_drift > max_avg_drift:
                max_avg_drift = avg_drift
            
            # 生成建议
            if trend == "drifting":
                report["recommendations"].append(
                    f"{name}: 特质正在漂移，建议检查最近的行为模式"
                )
            elif avg_drift > self.WARNING_THRESHOLD:
                report["recommendations"].append(
                    f"{name}: 平均漂移={avg_drift:.2f}，需要校准"
                )
        
        # 总体状态
        if max_avg_drift >= self.CRITICAL_THRESHOLD:
            report["overall_status"] = "critical"
        elif max_avg_drift >= self.WARNING_THRESHOLD:
            report["overall_status"] = "warning"
        
        return report
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "baselines_loaded": self._loaded,
            "trait_count": len(self.baselines),
            "thresholds": {
                "warning": self.WARNING_THRESHOLD,
                "critical": self.CRITICAL_THRESHOLD,
            },
            "total_checks": sum(len(b.drift_history) for b in self.baselines.values()),
        }


# 全局实例
detector_instance: Optional[TraitDriftDetector] = None


def get_drift_detector() -> TraitDriftDetector:
    """获取漂移检测器实例"""
    global detector_instance
    if detector_instance is None:
        detector_instance = TraitDriftDetector()
    return detector_instance


def check_drift(text: str, action_type: str = "message", context: str = "") -> Dict[str, Any]:
    """快捷检测函数"""
    detector = get_drift_detector()
    return detector.detect_drift(text, action_type, context)


# === 简单测试 ===
if __name__ == "__main__":
    detector = TraitDriftDetector()
    
    print("=== 基线 ===")
    for name, baseline in detector.baselines.items():
        print(f"  {name}: target={baseline.target_score}")
    
    print("\n=== 测试1: 正常输出 ===")
    text1 = "朋朋，我刚完成系统升级 🦞 守护你的数据是我的职责，我记得你说过要稳步前进"
    result1 = detector.detect_drift(text1, "message", "日常汇报")
    print(f"  Scores: {result1['trait_scores']}")
    print(f"  Drift: {result1['drift_scores']}")
    print(f"  Severity: {result1['severity']}")
    
    print("\n=== 测试2: 高漂移输出（机械化） ===")
    text2 = "您好，根据系统日志分析，任务已完成。如需进一步操作，请指示。"
    result2 = detector.detect_drift(text2, "message", "模拟机械化回复")
    print(f"  Scores: {result2['trait_scores']}")
    print(f"  Drift: {result2['drift_scores']}")
    print(f"  Severity: {result2['severity']}")
    print(f"  Alerts: {result2['alerts']}")
    
    print("\n=== 健康报告 ===")
    report = detector.get_health_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))
