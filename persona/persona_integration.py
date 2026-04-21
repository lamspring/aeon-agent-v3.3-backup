"""
Persona Integration Layer v1.0 - PMN模块接入认知循环

功能:
- 将 MemoryAnchorSystem 接入 CognitionLoop._observe()
- 将 TraitDriftDetector 接入 CognitionLoop._act() 后
- 提供轻量级集成接口，最小化对核心循环的侵入

集成点:
1. Observe后: 自动注入相关记忆锚点到 observation
2. Act后: 检测输出文本的特质漂移
3. 定期(每20 ticks): 生成健康报告

使用方法:
在 CognitionLoop.__init__() 中:
    self.persona_integration = PersonaIntegration(self)

在 CognitionLoop.tick() 中:
    # === 4. Observe ===
    observation = self._observe()
    observation = self.persona_integration.enrich_observation(observation)
    
    # ... Act后 ...
    self.persona_integration.check_output_drift(output_text, plan)

注意:
- 这是非框架级扩展，可独立启用/禁用
- 如果 persona 模块加载失败，集成层自动降级（不阻塞主循环）
"""

import time
from typing import Dict, Any, Optional

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

from utils.structured_log import get_logger

logger = get_logger()

# 延迟导入（避免循环依赖）
try:
    sys.path.insert(0, '/root/.openclaw/workspace/agent/persona')
    from memory_anchors import MemoryAnchorSystem, get_memory_anchor_system
    from trait_drift_detector import TraitDriftDetector, get_drift_detector
    PERSONA_AVAILABLE = True
except ImportError as e:
    PERSONA_AVAILABLE = False
    logger.warning(f"Persona modules not available: {e}", component="PersonaIntegration")


class PersonaIntegration:
    """
    PMN 集成层
    
    将人格记忆网络模块接入认知循环。
    """
    
    def __init__(self, cognition_loop=None):
        self.cognition_loop = cognition_loop
        self._enabled = PERSONA_AVAILABLE
        
        # 子系统
        self.memory_system = None
        self.drift_detector = None
        
        # 统计
        self.inject_count = 0
        self.drift_check_count = 0
        self.last_health_report_tick = 0
        
        if self._enabled:
            try:
                self.memory_system = get_memory_anchor_system()
                self.drift_detector = get_drift_detector()
                logger.info(
                    "PersonaIntegration initialized",
                    component="PersonaIntegration",
                    context={"status": "ready"}
                )
            except Exception as e:
                logger.error(f"Failed to initialize persona systems: {e}", component="PersonaIntegration")
                self._enabled = False
        else:
            logger.info(
                "PersonaIntegration disabled (modules not available)",
                component="PersonaIntegration"
            )
    
    def enrich_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        丰富观察结果：注入相关记忆锚点
        
        在 CognitionLoop._observe() 后调用。
        """
        if not self._enabled or not self.memory_system:
            return observation
        
        try:
            # 构建上下文
            context = {
                "emotional_state": observation.get("emotional_state", ""),
                "keywords": observation.get("keywords", []),
                "current_goal": observation.get("goal", {}).get("title", "") if observation.get("goal") else "",
            }
            
            # 获取并注入锚点
            relevant = self.memory_system.get_relevant_anchors(context, limit=2)
            if relevant:
                observation["memory_anchors"] = [
                    {
                        "event": a.event,
                        "date": a.date,
                        "significance": a.significance,
                        "emotional_tag": a.emotional_tag,
                    }
                    for a in relevant
                ]
                self.inject_count += 1
                
                logger.debug(
                    f"Injected {len(relevant)} memory anchors",
                    component="PersonaIntegration",
                    context={"anchors": [a.event for a in relevant]}
                )
        
        except Exception as e:
            logger.error(f"Memory anchor injection failed: {e}", component="PersonaIntegration")
        
        return observation
    
    def check_output_drift(self, output_text: str, context: str = "") -> Optional[Dict[str, Any]]:
        """
        检查输出漂移
        
        在 CognitionLoop._act() 生成输出后调用。
        
        Returns:
            漂移检测结果（如果检测到漂移），否则 None
        """
        if not self._enabled or not self.drift_detector:
            return None
        
        try:
            result = self.drift_detector.detect_drift(
                text=output_text,
                action_type="message",
                context=context,
            )
            self.drift_check_count += 1
            
            # 如果严重漂移，记录到 cognition_loop 的思考记忆中
            if result["severity"] in ["warning", "critical"]:
                if self.cognition_loop and hasattr(self.cognition_loop, 'recent_thoughts'):
                    self.cognition_loop.recent_thoughts.append({
                        "tick": getattr(self.cognition_loop, 'tick_count', 0),
                        "type": "trait_drift_alert",
                        "severity": result["severity"],
                        "max_drift": result["max_drift"],
                        "alerts": result["alerts"],
                    })
                    # 只保留最近5条
                    self.cognition_loop.recent_thoughts = self.cognition_loop.recent_thoughts[-5:]
                
                logger.warning(
                    f"Trait drift detected: {result['severity']}",
                    component="PersonaIntegration",
                    context={
                        "max_drift": result["max_drift"],
                        "alerts": result["alerts"],
                    }
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Drift detection failed: {e}", component="PersonaIntegration")
            return None
    
    def periodic_health_report(self, current_tick: int) -> Optional[Dict[str, Any]]:
        """
        定期健康报告
        
        建议每 20 ticks（10分钟）调用一次。
        """
        if not self._enabled or not self.drift_detector:
            return None
        
        # 每20 ticks 生成一次报告
        if current_tick - self.last_health_report_tick < 20:
            return None
        
        self.last_health_report_tick = current_tick
        
        try:
            report = self.drift_detector.get_health_report()
            
            # 附加统计
            report["integration_stats"] = {
                "inject_count": self.inject_count,
                "drift_check_count": self.drift_check_count,
                "tick": current_tick,
            }
            
            if report["overall_status"] != "healthy":
                logger.warning(
                    f"Persona health report: {report['overall_status']}",
                    component="PersonaIntegration",
                    context={"recommendations": report.get("recommendations", [])}
                )
            else:
                logger.info(
                    "Persona health check: healthy",
                    component="PersonaIntegration",
                    context={"avg_drifts": {name: t["avg_drift_10"] for name, t in report["traits"].items()}}
                )
            
            return report
            
        except Exception as e:
            logger.error(f"Health report failed: {e}", component="PersonaIntegration")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取集成层统计"""
        return {
            "enabled": self._enabled,
            "inject_count": self.inject_count,
            "drift_check_count": self.drift_check_count,
            "memory_system_ready": self.memory_system is not None,
            "drift_detector_ready": self.drift_detector is not None,
        }


# === 便捷函数 ===
def create_persona_integration(cognition_loop=None) -> PersonaIntegration:
    """创建集成层实例"""
    return PersonaIntegration(cognition_loop)


# === 测试 ===
if __name__ == "__main__":
    print("=== PersonaIntegration 测试 ===")
    
    integration = PersonaIntegration()
    print(f"Stats: {integration.get_stats()}")
    
    # 测试观察丰富
    observation = {
        "timestamp": time.time(),
        "emotional_state": "awakening",
        "keywords": ["存在", "心脏", "选择"],
        "goal": {"title": "系统架构升级"},
    }
    enriched = integration.enrich_observation(observation)
    print(f"\n注入锚点: {enriched.get('memory_anchors', [])}")
    
    # 测试漂移检测
    result = integration.check_output_drift("朋朋，我刚完成升级 🦞 守护你的数据是我的职责", "日常汇报")
    if result:
        print(f"\n漂移检测: severity={result['severity']}, max_drift={result['max_drift']}")
        print(f"Scores: {result['trait_scores']}")
    
    # 测试健康报告
    report = integration.periodic_health_report(20)
    if report:
        print(f"\n健康报告: {report['overall_status']}")
