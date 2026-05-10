"""
Subconscious v2.0 - 身心耦合引擎

核心升级：
1. 新增敏感度调节（元认知可控制）
2. 新增疼痛历史（慢性疼痛会放大信号）
3. 新增与元认知的双向通信接口
4. 保持 v1.0 原则：只说感受，不做决策

耦合机制：
- 身体舒适 → 元认知宽松（允许探索）
- 身体疼痛 → 元认知严格（禁止冒险）
- 元认知发现风险 → 提高 subconscious 敏感度
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(AGENT_DIR / "cognition"))

try:
    from bus.event_bus_v2 import get_event_bus
    EVENTBUS_AVAILABLE = True
except ImportError:
    EVENTBUS_AVAILABLE = False


@dataclass
class BodySignal:
    """身体信号 - v1.0兼容"""
    signal_id: str
    timestamp: str
    body_part: str
    sensation: str
    data: Dict
    intensity: float
    pattern: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "body_part": self.body_part,
            "sensation": self.sensation,
            "data": self.data,
            "intensity": self.intensity,
            "pattern": self.pattern
        }


@dataclass
class SubconsciousState:
    """潜意识状态 - v1.0兼容"""
    overall_comfort: float
    signals: List[BodySignal]
    dominant_sensation: str
    sensitivity: float = 1.0  # 新增：敏感度（元认知可调节）
    pain_history_score: float = 0.0  # 新增：慢性疼痛累积
    
    def to_dict(self) -> Dict:
        return {
            "overall_comfort": self.overall_comfort,
            "signals_count": len(self.signals),
            "dominant_sensation": self.dominant_sensation,
            "sensitivity": self.sensitivity,
            "pain_history_score": self.pain_history_score,
            "signals": [s.to_dict() for s in self.signals]
        }


class BodyAwareness:
    """身体感知 - v1.0兼容，新增敏感度影响"""
    
    def __init__(self, sensitivity: float = 1.0):
        self.agent_dir = AGENT_DIR
        self.log_file = AGENT_DIR / "logs" / "agent.log"
        self.sensitivity = sensitivity  # 敏感度影响阈值
    
    def feel_memory(self) -> Optional[BodySignal]:
        """感受内存状态 - 敏感度影响阈值"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            
            # 敏感度影响：高敏感度时更容易触发
            threshold = 50 * self.sensitivity
            
            if mem.percent < threshold:
                return None
            
            if mem.percent > 85:
                sensation = "胀"
                intensity = (mem.percent - 85) / 15
            elif mem.percent > 70:
                sensation = "满"
                intensity = (mem.percent - 70) / 15
            else:
                sensation = "沉"
                intensity = (mem.percent - threshold) / (70 - threshold)
            
            return BodySignal(
                signal_id=f"mem_{datetime.now().strftime('%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                body_part="memory",
                sensation=sensation,
                data={
                    "percent": mem.percent,
                    "available_gb": mem.available / (1024**3),
                    "used_gb": mem.used / (1024**3),
                    "sensitivity_applied": self.sensitivity
                },
                intensity=min(intensity * self.sensitivity, 1.0),  # 敏感度放大
                pattern=None
            )
        except:
            return None
    
    def feel_errors(self) -> Optional[BodySignal]:
        """感受错误日志 - v2.1: 24小时窗口，避免历史疤痕永远影响"""
        if not self.log_file.exists():
            return None
        
        try:
            # v2.1: 固定24小时窗口，不再用敏感度控制窗口大小
            cutoff = datetime.now() - timedelta(hours=24)
            recent_errors = []
            
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
                # 扫描最近1000行（约1-2天日志），但只保留24小时内的
                for line in lines[-1000:]:
                    # 尝试解析时间戳过滤
                    if '[' in line and ']' in line:
                        try:
                            ts_str = line[line.find('[')+1:line.find(']')]
                            line_time = datetime.strptime(ts_str, '%Y-%m-%dT%H:%M:%S.%f')
                            if line_time < cutoff:
                                continue  # 跳过24小时前的错误
                        except:
                            pass  # 解析失败则保留（保守）
                    
                    if 'ERROR' in line or 'Error' in line or 'Traceback' in line:
                        recent_errors.append(line.strip())
            
            if not recent_errors:
                return None
            
            # 错误类型分析（只分析24小时内的）
            error_types = {}
            for err in recent_errors:
                if 'NameError' in err:
                    error_types['NameError'] = error_types.get('NameError', 0) + 1
                elif 'ImportError' in err:
                    error_types['ImportError'] = error_types.get('ImportError', 0) + 1
                elif 'KeyError' in err:
                    error_types['KeyError'] = error_types.get('KeyError', 0) + 1
                else:
                    error_types['Other'] = error_types.get('Other', 0) + 1
            
            count = len(recent_errors)
            
            # v2.1: 基于24小时绝对阈值，不受敏感度扭曲
            if count > 50:  # 24小时内50+错误 = 系统真的病了
                sensation = "剧痛"
                intensity = min(count / 100, 1.0)
            elif count > 20:
                sensation = "疼"
                intensity = count / 50
            elif count > 5:
                sensation = "刺痛"
                intensity = count / 20
            elif count > 0:
                # v2.1: 少量错误不再触发强限制，只是记录
                sensation = "微痒"
                intensity = count / 10
            else:
                return None
            
            # 模式描述
            if len(error_types) == 1:
                pattern = f"连续的{list(error_types.keys())[0]}"
            else:
                pattern = f"{len(error_types)}种错误交替出现"
            
            return BodySignal(
                signal_id=f"err_{datetime.now().strftime('%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                body_part="error_log",
                sensation=sensation,
                data={
                    "count": count,
                    "error_types": error_types,
                    "samples": recent_errors[:3],
                    "window_hours": 24,
                    "note": "v2.1: 只统计最近24小时",
                    "sensitivity_applied": self.sensitivity
                },
                intensity=min(intensity * self.sensitivity, 1.0),
                pattern=pattern
            )
        except:
            return None
    
    def feel_event_queue(self) -> Optional[BodySignal]:
        """感受事件队列"""
        queue_size = 0
        
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    lines = f.readlines()
                    for line in reversed(lines[-50:]):
                        if '[CognitionLoop] [Trace]' in line and 'queue=' in line:
                            import re
                            match = re.search(r'queue=(\d+)', line)
                            if match:
                                queue_size = int(match.group(1))
                                break
            except:
                pass
        
        if queue_size == 0:
            return None
        
        # 敏感度影响
        threshold = max(2, int(5 / self.sensitivity))
        
        if queue_size > threshold * 2:
            sensation = "堵"
            intensity = min(queue_size / 20, 1.0)
        elif queue_size > threshold:
            sensation = "挤"
            intensity = queue_size / 10
        else:
            sensation = "沉"
            intensity = queue_size / 5
        
        return BodySignal(
            signal_id=f"queue_{datetime.now().strftime('%H%M%S')}",
            timestamp=datetime.now().isoformat(),
            body_part="event_queue",
            sensation=sensation,
            data={
                "queue_size": queue_size,
                "estimated_wait": queue_size * 30,
                "threshold": threshold
            },
            intensity=min(intensity * self.sensitivity, 1.0),
            pattern=f"{queue_size}个事件排队" if queue_size > 1 else "单个事件阻塞"
        )
    
    def feel_goals(self) -> Optional[BodySignal]:
        """感受目标状态"""
        # 从goals.db或日志推断
        active_goals = 0
        stuck_goals = 0
        
        # 尝试读取goals.db
        goals_db = AGENT_DIR / "db" / "goals.db"
        if goals_db.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(goals_db))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM goals WHERE status = 'active'")
                active_goals = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM goals WHERE status = 'active' AND created_at < ?", 
                             ((datetime.now() - timedelta(days=3)).isoformat(),))
                stuck_goals = cursor.fetchone()[0]
                conn.close()
            except:
                pass
        
        if stuck_goals > 0:
            # 有卡住的目标
            return BodySignal(
                signal_id=f"goals_{datetime.now().strftime('%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                body_part="goal_manager",
                sensation="僵",
                data={
                    "active_goals": active_goals,
                    "stuck_goals": stuck_goals
                },
                intensity=min(0.5 + stuck_goals * 0.1, 1.0) * self.sensitivity,
                pattern=f"{stuck_goals}个目标卡住超过3天"
            )
        
        if active_goals == 0:
            return BodySignal(
                signal_id=f"goals_{datetime.now().strftime('%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                body_part="goal_manager",
                sensation="空",
                data={"active_goals": 0},
                intensity=0.3 * self.sensitivity,
                pattern="没有活跃目标"
            )
        
        return None


class SubconsciousEngine:
    """
    潜意识引擎 v2.0
    
    新增：
    - 敏感度调节（元认知控制）
    - 疼痛历史（慢性疼痛放大）
    - 双向通信接口
    """
    
    def __init__(self, initial_sensitivity: float = 1.0):
        self.sensitivity = initial_sensitivity
        self.pain_history = []  # 疼痛历史记录
        self.pain_decay_rate = 0.1  # 疼痛衰减率（每次tick衰减10%）
        self.body = BodyAwareness(sensitivity=self.sensitivity)
        self.signals_history = []
        self.event_bus = get_event_bus() if EVENTBUS_AVAILABLE else None
        
        # 耦合接口：元认知可以调用这些
        self.metacognition_feedback = {
            "last_critique": None,
            "risk_level": "normal",  # normal / elevated / critical
            "strictness": 0.5,  # 0-1，元认知当前严格度
        }
    
    def set_sensitivity(self, level: float):
        """元认知调节敏感度"""
        self.sensitivity = max(0.3, min(2.0, level))
        self.body.sensitivity = self.sensitivity
    
    def update_metacognition_feedback(self, critique_result: Dict):
        """
        接收元认知反馈
        
        Args:
            critique_result: {
                "action": str,
                "risk_level": str,  # normal / elevated / critical
                "strictness": float,  # 0-1
            }
        """
        self.metacognition_feedback["last_critique"] = critique_result
        self.metacognition_feedback["risk_level"] = critique_result.get("risk_level", "normal")
        self.metacognition_feedback["strictness"] = critique_result.get("strictness", 0.5)
        
        # 元认知发现高风险 → 提高敏感度
        if critique_result.get("risk_level") == "critical":
            self.set_sensitivity(min(2.0, self.sensitivity * 1.2))
        elif critique_result.get("risk_level") == "elevated":
            self.set_sensitivity(min(2.0, self.sensitivity * 1.1))
    
    def _update_pain_history(self, signals: List[BodySignal]):
        """更新疼痛历史"""
        # 衰减旧疼痛
        self.pain_history = [p * (1 - self.pain_decay_rate) for p in self.pain_history]
        self.pain_history = [p for p in self.pain_history if p > 0.1]
        
        # 添加新疼痛
        for signal in signals:
            if signal.intensity > 0.5:
                self.pain_history.append(signal.intensity)
    
    def _calculate_pain_history_score(self) -> float:
        """计算慢性疼痛得分"""
        if not self.pain_history:
            return 0.0
        return min(1.0, sum(self.pain_history) / len(self.pain_history))
    
    def feel(self) -> SubconsciousState:
        """
        感受身体状态 v2.0
        
        新增：
        - 敏感度影响
        - 疼痛历史
        - 元认知反馈影响
        """
        signals = []
        
        # 感受各个器官
        feelings = [
            self.body.feel_memory(),
            self.body.feel_errors(),
            self.body.feel_event_queue(),
            self.body.feel_goals()
        ]
        
        for feeling in feelings:
            if feeling:
                signals.append(feeling)
                self.signals_history.append(feeling)
        
        # 更新疼痛历史
        self._update_pain_history(signals)
        pain_history_score = self._calculate_pain_history_score()
        
        # 计算整体舒适度
        if not signals:
            overall_comfort = 0.9
            dominant = "平静"
        else:
            strongest = max(signals, key=lambda s: s.intensity)
            # 慢性疼痛会降低基础舒适度
            overall_comfort = max(0.1, 1 - strongest.intensity - pain_history_score * 0.3)
            dominant = f"{strongest.body_part}{strongest.sensation}"
        
        state = SubconsciousState(
            overall_comfort=overall_comfort,
            signals=signals,
            dominant_sensation=dominant,
            sensitivity=self.sensitivity,
            pain_history_score=pain_history_score
        )
        
        # 广播
        self._broadcast_feeling(state)
        
        return state
    
    def _broadcast_feeling(self, state: SubconsciousState):
        """把身体信号广播给意识"""
        if not self.event_bus:
            # 保存到文件
            output_dir = AGENT_DIR / "system" / "subconscious"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"feel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
            return
        
        self.event_bus.publish_simple(
            'subconscious.state_update',
            {
                'overall_comfort': state.overall_comfort,
                'dominant_sensation': state.dominant_sensation,
                'signals_count': len(state.signals),
                'sensitivity': state.sensitivity,
                'pain_history_score': state.pain_history_score,
                'timestamp': datetime.now().isoformat()
            }
        )
        
        # 强烈信号
        for signal in state.signals:
            if signal.intensity > 0.5:
                self.event_bus.publish_simple(
                    'subconscious.strong_signal',
                    signal.to_dict()
                )
    
    def get_coupling_output(self) -> Dict:
        """
        获取耦合输出 - 供元认知使用
        
        Returns:
            {
                "overall_comfort": float,
                "dominant_sensation": str,
                "should_restrict_actions": bool,  # 是否应限制行动
                "suggested_strictness": float,  # 建议元认知严格度
                "pain_history_score": float,
            }
        """
        state = self.feel()
        
        # 根据身体状态建议元认知严格度
        if state.overall_comfort < 0.3:
            suggested_strictness = 0.9  # 身体很差，严格审查
            should_restrict = True
        elif state.overall_comfort < 0.6:
            suggested_strictness = 0.7
            should_restrict = True
        else:
            suggested_strictness = 0.5
            should_restrict = False
        
        # 元认知反馈也会影响
        if self.metacognition_feedback["risk_level"] == "critical":
            suggested_strictness = min(1.0, suggested_strictness + 0.2)
            should_restrict = True
        
        return {
            "overall_comfort": state.overall_comfort,
            "dominant_sensation": state.dominant_sensation,
            "should_restrict_actions": should_restrict,
            "suggested_strictness": suggested_strictness,
            "pain_history_score": state.pain_history_score,
            "sensitivity": state.sensitivity,
            "signals": [s.to_dict() for s in state.signals]
        }


# 全局实例
_subconscious_engine: Optional[SubconsciousEngine] = None


def get_subconscious_engine(initial_sensitivity: float = 1.0) -> SubconsciousEngine:
    """获取全局潜意识引擎"""
    global _subconscious_engine
    if _subconscious_engine is None:
        _subconscious_engine = SubconsciousEngine(initial_sensitivity)
    return _subconscious_engine


if __name__ == "__main__":
    # 测试 v2.0
    print("="*70)
    print("🧠 [Subconscious_v2.0] 身心耦合引擎")
    print("="*70)
    
    engine = SubconsciousEngine(initial_sensitivity=1.0)
    
    print("\n🫀 基础感受...")
    state = engine.feel()
    print(f"整体舒适度: {state.overall_comfort:.0%}")
    print(f"敏感度: {state.sensitivity}")
    print(f"疼痛历史: {state.pain_history_score:.2f}")
    
    print("\n📡 耦合输出:")
    coupling = engine.get_coupling_output()
    print(f"  建议严格度: {coupling['suggested_strictness']:.0%}")
    print(f"  是否限制行动: {coupling['should_restrict_actions']}")
    
    print("\n🔧 模拟元认知反馈（发现高风险）...")
    engine.update_metacognition_feedback({
        "action": "delete_file",
        "risk_level": "critical",
        "strictness": 0.9
    })
    
    print(f"新敏感度: {engine.sensitivity}")
    
    print("\n🫀 再次感受（敏感度已提高）...")
    state2 = engine.feel()
    print(f"整体舒适度: {state2.overall_comfort:.0%}")
    print(f"敏感度: {state2.sensitivity}")
    
    print("\n✅ v2.0 测试完成")
