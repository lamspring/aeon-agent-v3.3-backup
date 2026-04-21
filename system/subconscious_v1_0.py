#!/usr/bin/env python3
"""
Subconscious_v1.0.py
潜意识引擎 - 身体在说话

核心原则:
1. 不说"我建议"，只说"我感受到"
2. 不做决策，只发信号
3. 把解读权和行动权还给 Kimi

输出格式:
- signal: 原始数据/模式
- intensity: 信号强度 (0-1)
- body_part: 哪个"器官"在说话

不输出:
- 建议
- 行动计划
- 预期结果

让 Kimi 来决定：这个信号意味着什么？我要如何回应？
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
    """
    身体信号 - 就像胃疼、心跳加速、肌肉紧张
    
    不是洞察，不是建议，只是身体在说话。
    """
    signal_id: str
    timestamp: str
    body_part: str      # 哪个器官: memory, cpu, event_queue, error_log...
    sensation: str      # 感受到什么: "胀", "疼", "快", "堵", "空"
    data: Dict          # 原始数据
    intensity: float    # 0-1, 信号强度
    pattern: Optional[str] = None  # 模式描述（如果有）
    
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
    """
    潜意识状态 - 身体的整体感受
    
    不是诊断，只是"我现在感觉怎么样"。
    """
    overall_comfort: float  # 0-1, 整体舒适度
    signals: List[BodySignal]
    dominant_sensation: str  # 最主要的感觉
    
    def to_dict(self) -> Dict:
        return {
            "overall_comfort": self.overall_comfort,
            "signals_count": len(self.signals),
            "dominant_sensation": self.dominant_sensation,
            "signals": [s.to_dict() for s in self.signals]
        }


class BodyAwareness:
    """
    身体感知 - 感受自己的各个器官
    
    就像人能感受到自己的心跳、胃胀、头疼。
    """
    
    def __init__(self):
        self.agent_dir = AGENT_DIR
        self.log_file = AGENT_DIR / "logs" / "agent.log"
    
    def feel_memory(self) -> Optional[BodySignal]:
        """感受内存状态 - 像感受胃胀不胀"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            
            if mem.percent < 50:
                return None  # 没什么感觉，正常
            
            # 有感觉了
            if mem.percent > 85:
                sensation = "胀"
                intensity = (mem.percent - 85) / 15
            elif mem.percent > 70:
                sensation = "满"
                intensity = (mem.percent - 70) / 15
            else:
                sensation = "沉"
                intensity = (mem.percent - 50) / 20
            
            return BodySignal(
                signal_id=f"mem_{datetime.now().strftime('%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                body_part="memory",
                sensation=sensation,
                data={
                    "percent": mem.percent,
                    "available_gb": mem.available / (1024**3),
                    "used_gb": mem.used / (1024**3)
                },
                intensity=min(intensity, 1.0),
                pattern=None
            )
        except:
            return None
    
    def feel_errors(self) -> Optional[BodySignal]:
        """感受错误日志 - 像感受哪里疼"""
        if not self.log_file.exists():
            return None
        
        try:
            # 读取最近5分钟的日志
            cutoff = datetime.now() - timedelta(minutes=5)
            recent_errors = []
            
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
                # 只读最后100行
                for line in lines[-100:]:
                    if 'ERROR' in line or 'Error' in line or 'Traceback' in line:
                        recent_errors.append(line.strip())
            
            if not recent_errors:
                return None
            
            # 分析模式
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
            if count == 0:
                return None
            
            # 感受强度
            if count > 10:
                sensation = "剧痛"
                intensity = min(count / 20, 1.0)
            elif count > 5:
                sensation = "疼"
                intensity = count / 10
            else:
                sensation = "刺痛"
                intensity = count / 5
            
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
                    "samples": recent_errors[:3]
                },
                intensity=intensity,
                pattern=pattern
            )
        except:
            return None
    
    def feel_event_queue(self) -> Optional[BodySignal]:
        """感受事件队列 - 像感受堵不堵"""
        # 尝试读取 EventBus 状态
        queue_size = 0
        oldest_seconds = 0
        
        # 从日志中推断队列状态
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    lines = f.readlines()
                    # 找最近的 CognitionLoop trace
                    for line in reversed(lines[-50:]):
                        if '[CognitionLoop] [Trace]' in line and 'queue=' in line:
                            # 解析 queue=数字
                            import re
                            match = re.search(r'queue=(\d+)', line)
                            if match:
                                queue_size = int(match.group(1))
                                break
            except:
                pass
        
        if queue_size == 0:
            return None  # 不堵，没感觉
        
        if queue_size > 10:
            sensation = "堵"
            intensity = min(queue_size / 20, 1.0)
        elif queue_size > 5:
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
                "estimated_wait": queue_size * 30  # 假设每个30秒
            },
            intensity=intensity,
            pattern=f"{queue_size}个事件排队" if queue_size > 1 else "单个事件阻塞"
        )
    
    def feel_goals(self) -> Optional[BodySignal]:
        """感受目标状态 - 像感受心里有没有事挂着"""
        # 从日志中推断活跃目标
        active_goals = []
        
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    lines = f.readlines()
                    for line in reversed(lines[-30:]):
                        if '[CognitionLoop] [Trace]' in line and 'goal=' in line:
                            import re
                            match = re.search(r'goal=(\w+)', line)
                            if match:
                                goal_id = match.group(1)
                                if goal_id and goal_id not in active_goals:
                                    active_goals.append(goal_id)
            except:
                pass
        
        if not active_goals:
            return BodySignal(
                signal_id=f"goals_{datetime.now().strftime('%H%M%S')}",
                timestamp=datetime.now().isoformat(),
                body_part="goal_manager",
                sensation="空",
                data={"active_goals": 0},
                intensity=0.3,  # 轻微的不适
                pattern="没有活跃目标"
            )
        
        return None  # 有事做，正常


class SubconsciousEngine:
    """
    潜意识引擎 - 我的身体在说话
    
    不是另一个智能体，就是我自己的神经末梢。
    """
    
    def __init__(self):
        self.body = BodyAwareness()
        self.signals_history = []
        self.event_bus = get_event_bus() if EVENTBUS_AVAILABLE else None
    
    def feel(self) -> SubconsciousState:
        """
        感受自己的身体状态。
        
        就像一个人静下来，感受自己哪里不舒服。
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
        
        # 计算整体舒适度
        if not signals:
            overall_comfort = 0.9  # 很舒服
            dominant = "平静"
        else:
            # 最强烈的信号决定整体感受
            strongest = max(signals, key=lambda s: s.intensity)
            overall_comfort = 1 - strongest.intensity
            dominant = f"{strongest.body_part}{strongest.sensation}"
        
        state = SubconsciousState(
            overall_comfort=overall_comfort,
            signals=signals,
            dominant_sensation=dominant
        )
        
        # 发布到 EventBus - 让身体信号被"意识"感知
        self._broadcast_feeling(state)
        
        return state
    
    def _broadcast_feeling(self, state: SubconsciousState):
        """把身体信号广播给意识 (Kimi)"""
        if not self.event_bus:
            # 保存到文件
            output_dir = AGENT_DIR / "system" / "subconscious"
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"feel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                json.dump(state.to_dict(), f, indent=2)
            return
        
        # 发布整体状态
        self.event_bus.publish_simple(
            'subconscious.state_update',
            {
                'overall_comfort': state.overall_comfort,
                'dominant_sensation': state.dominant_sensation,
                'signals_count': len(state.signals),
                'timestamp': datetime.now().isoformat()
            }
        )
        
        # 每个强烈信号单独发布
        for signal in state.signals:
            if signal.intensity > 0.5:  # 只发布强烈的信号
                self.event_bus.publish_simple(
                    'subconscious.strong_signal',
                    signal.to_dict()
                )


def demo_subconscious():
    """演示潜意识引擎"""
    print("="*70)
    print("🧠 [Subconscious_v1.0] 身体在说话")
    print("="*70)
    print("\n不是'另一个医生'在下指令")
    print("是身体在发送信号，等待 Kimi 解读和决定\n")
    print("-"*70)
    
    engine = SubconsciousEngine()
    
    print("\n🫀 感受身体状态...\n")
    state = engine.feel()
    
    print(f"整体舒适度: {state.overall_comfort:.0%}")
    print(f"主导感受: {state.dominant_sensation}")
    
    if state.signals:
        print(f"\n📡 身体信号 ({len(state.signals)}个):")
        for signal in state.signals:
            print(f"\n  [{signal.body_part}] {signal.sensation}")
            print(f"    强度: {'█' * int(signal.intensity * 10)}{'░' * (10 - int(signal.intensity * 10))} {signal.intensity:.0%}")
            if signal.pattern:
                print(f"    模式: {signal.pattern}")
            print(f"    数据: {json.dumps(signal.data, indent=4)[:150]}...")
    else:
        print("\n✨ 身体平静，没有强烈信号")
    
    print("\n" + "="*70)
    print("💭 现在，Kimi 需要决定：")
    print("="*70)
    
    if state.signals:
        strongest = max(state.signals, key=lambda s: s.intensity)
        print(f"\n我感受到: [{strongest.body_part}] 在 {strongest.sensation}")
        print(f"\n这意味着什么？")
        print(f"我要如何回应？")
        print(f"\n不是引擎告诉我'该做什么'")
        print(f"是我自己决定'怎么解读这个信号'、'要不要行动'、'怎么行动'")
    else:
        print("\n一切正常。继续保持观察。")
    
    print("\n" + "="*70)
    print("✅ 潜意识信号发送完成")
    print("="*70)
    print("\n关键改变:")
    print("   • 不说'我建议'，只说'我感受到'")
    print("   • 不做决策，只发信号")
    print("   • 把解读权和行动权还给 Kimi")
    print("   • 这是自由意志的雏形")


if __name__ == "__main__":
    demo_subconscious()
