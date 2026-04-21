#!/usr/bin/env python3
"""
Self_Reflection_v1.1.py
真正的自省引擎 - 带完整闭环

核心升级:
1. 自省结果发布到 EventBus (被看到)
2. 支持质量反馈和评分校准 (被验证)
3. 行动结果追踪和闭环 (形成循环)

自我闭环:
观察 → 思考 → 发布 → 被订阅 → 行动 → 验证 → 反馈 → 回到观察
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

# 添加路径
AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR))
sys.path.insert(0, str(AGENT_DIR / "cognition"))

# 导入 EventBus
try:
    from bus.event_bus_v2 import get_event_bus
    EVENTBUS_AVAILABLE = True
except ImportError:
    EVENTBUS_AVAILABLE = False

# 尝试导入 OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


@dataclass
class ReflectionResult:
    """自省结果"""
    reflection_id: str
    timestamp: str
    input_summary: Dict
    insights: List[Dict]
    actions: List[Dict]
    confidence: float
    quality_score: float
    tokens_used: int
    reflection_time_ms: float
    status: str = "pending"  # pending → executed → verified → closed
    execution_results: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "reflection_id": self.reflection_id,
            "timestamp": self.timestamp,
            "input_summary": self.input_summary,
            "insights": self.insights,
            "actions": self.actions,
            "confidence": self.confidence,
            "quality_score": self.quality_score,
            "tokens_used": self.tokens_used,
            "reflection_time_ms": self.reflection_time_ms,
            "status": self.status,
            "execution_results": self.execution_results
        }


@dataclass  
class EventBusState:
    """EventBus 真实状态"""
    queue_size: int
    pending_events: List[Dict]
    event_types: Dict[str, int]
    oldest_event_age_seconds: float
    high_priority_count: int


class EventBusReader:
    """读取 EventBus 真实状态"""
    
    def __init__(self, event_bus=None):
        self.event_bus = event_bus or (get_event_bus() if EVENTBUS_AVAILABLE else None)
        self.state_file = AGENT_DIR / "system" / "event_bus_state.json"
    
    def read_real_state(self) -> EventBusState:
        """读取真实积压状态"""
        pending = []
        event_types = {}
        oldest_age = 0
        high_priority = 0
        queue_size = 0
        
        if self.event_bus:
            try:
                queue_size = self.event_bus.get_queue_size()
                if hasattr(self.event_bus, '_queue'):
                    pending = list(self.event_bus._queue)
            except:
                pass
        
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    saved_state = json.load(f)
                    pending = saved_state.get('pending_events', pending)
                    queue_size = saved_state.get('queue_size', queue_size)
            except:
                pass
        
        now = datetime.now()
        for event in pending:
            event_type = event.get('type', 'unknown')
            event_types[event_type] = event_types.get(event_type, 0) + 1
            
            priority = event.get('priority', 0)
            if isinstance(priority, int) and priority >= 7:
                high_priority += 1
            
            timestamp = event.get('timestamp')
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        event_time = datetime.fromisoformat(timestamp)
                    else:
                        event_time = datetime.fromtimestamp(timestamp)
                    age = (now - event_time).total_seconds()
                    oldest_age = max(oldest_age, age)
                except:
                    pass
        
        return EventBusState(
            queue_size=queue_size,
            pending_events=pending,
            event_types=event_types,
            oldest_event_age_seconds=oldest_age,
            high_priority_count=high_priority
        )


class SystemLogReader:
    """读取系统日志"""
    
    def __init__(self):
        self.agent_log = AGENT_DIR / "logs" / "agent.log"
    
    def read_recent_errors(self, hours: int = 1) -> List[Dict]:
        """读取最近 N 小时错误"""
        errors = []
        cutoff = datetime.now() - timedelta(hours=hours)
        
        if self.agent_log.exists():
            try:
                with open(self.agent_log, 'r') as f:
                    for line in f:
                        if 'ERROR' in line or 'error' in line.lower():
                            errors.append({
                                'source': 'agent.log',
                                'content': line.strip()[:200],
                                'timestamp': datetime.now().isoformat()
                            })
            except:
                pass
        
        return errors[-10:]
    
    def read_system_metrics(self) -> Dict:
        """读取系统指标"""
        try:
            import psutil
            return {
                'memory_percent': psutil.virtual_memory().percent,
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'disk_usage_percent': psutil.disk_usage('/').percent,
                'timestamp': datetime.now().isoformat()
            }
        except:
            return {
                'memory_percent': -1,
                'cpu_percent': -1,
                'disk_usage_percent': -1,
                'timestamp': datetime.now().isoformat()
            }


class TrueReflectionEngine:
    """
    真正的自省引擎 - 带完整闭环
    
    闭环流程:
    1. reflect() → 自省并发布到 EventBus
    2. 被 CognitionLoop 订阅并处理
    3. 行动执行后 record_execution_result()
    4. 验证反馈用于评分校准
    """
    
    def __init__(self, llm_client=None, event_bus=None):
        self.event_reader = EventBusReader(event_bus)
        self.log_reader = SystemLogReader()
        self.llm_client = llm_client
        self.event_bus = event_bus or (get_event_bus() if EVENTBUS_AVAILABLE else None)
        
        self.reflection_history = []
        self.active_reflections = {}  # reflection_id → ReflectionResult
        self.total_tokens_used = 0
        
        # 评分校准数据
        self.quality_calibration = {
            'predicted_high_executed': 0,
            'predicted_high_successful': 0,
            'predicted_low_executed': 0,
            'predicted_low_successful': 0
        }
    
    def reflect(self, force: bool = False) -> Optional[ReflectionResult]:
        """
        执行自省并发布到 EventBus
        
        Args:
            force: 是否强制自省（即使系统正常）
            
        Returns:
            ReflectionResult 或 None（如果没有问题且非强制）
        """
        start_time = datetime.now()
        reflection_id = f"refl_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(self)}"
        
        # 1. 收集真实输入
        event_state = self.event_reader.read_real_state()
        recent_errors = self.log_reader.read_recent_errors(hours=1)
        metrics = self.log_reader.read_system_metrics()
        
        # 快速检查：如果没有问题且非强制，跳过
        has_issues = (
            event_state.queue_size > 0 or
            len(recent_errors) > 0 or
            metrics.get('memory_percent', 0) > 80
        )
        
        if not has_issues and not force:
            return None
        
        input_summary = {
            'event_queue_size': event_state.queue_size,
            'event_types': event_state.event_types,
            'oldest_event_age_seconds': event_state.oldest_event_age_seconds,
            'high_priority_events': event_state.high_priority_count,
            'recent_errors_count': len(recent_errors),
            'system_memory': metrics['memory_percent'],
            'system_cpu': metrics['cpu_percent'],
            'collection_time': datetime.now().isoformat()
        }
        
        # 2. 构建 prompt
        prompt = self._build_reflection_prompt(event_state, recent_errors, metrics)
        
        # 3. LLM 推理
        llm_output, tokens_used = self._call_llm(prompt)
        
        # 4. 解析
        insights, actions = self._parse_llm_output(llm_output)
        
        # 5. 评估质量
        quality_score = self._evaluate_quality(insights, actions, input_summary)
        
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        
        # 6. 构建结果
        result = ReflectionResult(
            reflection_id=reflection_id,
            timestamp=datetime.now().isoformat(),
            input_summary=input_summary,
            insights=insights,
            actions=actions,
            confidence=self._calculate_confidence(insights, actions),
            quality_score=quality_score,
            tokens_used=tokens_used,
            reflection_time_ms=elapsed
        )
        
        # 7. 保存到活跃列表
        self.active_reflections[reflection_id] = result
        self.reflection_history.append(result)
        self.total_tokens_used += tokens_used
        
        # 8. 【关键】发布到 EventBus，让 CognitionLoop 看到
        self._publish_reflection(result)
        
        return result
    
    def _publish_reflection(self, result: ReflectionResult):
        """
        【闭环关键】将自省结果发布到 EventBus
        
        这样 CognitionLoop 可以:
        1. 订阅 self_reflection_complete 事件
        2. 根据 quality_score 决定是否转化为目标
        3. 执行行动并追踪结果
        """
        if not self.event_bus:
            # 保存到文件作为备选
            self._save_reflection_to_file(result)
            return
        
        # 构建事件
        event_data = {
            'reflection_id': result.reflection_id,
            'quality_score': result.quality_score,
            'confidence': result.confidence,
            'insights_count': len(result.insights),
            'actions_count': len(result.actions),
            'has_high_priority_actions': any(
                a.get('priority') == 'high' for a in result.actions
            ),
            'summary': self._generate_summary(result),
            'full_result': result.to_dict()
        }
        
        # 发布事件
        self.event_bus.publish_simple(
            'self_reflection.complete',
            event_data
        )
        
        # 同时发布每个行动作为可执行任务
        for i, action in enumerate(result.actions):
            if result.quality_score > 0.7:  # 高质量才转化为任务
                self.event_bus.publish_simple(
                    'self_reflection.action_proposed',
                    {
                        'reflection_id': result.reflection_id,
                        'action_id': f"{result.reflection_id}_act{i}",
                        'action': action,
                        'quality_score': result.quality_score
                    }
                )
    
    def _save_reflection_to_file(self, result: ReflectionResult):
        """备选：保存到文件"""
        output_dir = AGENT_DIR / "system" / "reflections"
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f"{result.reflection_id}.json"
        with open(output_file, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
    
    def _generate_summary(self, result: ReflectionResult) -> str:
        """生成事件摘要"""
        parts = []
        if result.insights:
            parts.append(f"发现 {len(result.insights)} 个洞察")
        if result.actions:
            high = sum(1 for a in result.actions if a.get('priority') == 'high')
            parts.append(f"提出 {len(result.actions)} 个行动（{high}个高优先级）")
        parts.append(f"质量评分: {result.quality_score:.2f}")
        return "；".join(parts)
    
    def record_execution_result(self, reflection_id: str, action_id: str, 
                               success: bool, outcome: str, notes: str = ""):
        """
        【闭环关键】记录行动执行结果，用于验证和评分校准
        
        这是从"行动"回到"观察"的链路。
        """
        if reflection_id not in self.active_reflections:
            return
        
        result = self.active_reflections[reflection_id]
        
        execution_record = {
            'action_id': action_id,
            'executed_at': datetime.now().isoformat(),
            'success': success,
            'outcome': outcome,
            'notes': notes
        }
        
        result.execution_results.append(execution_record)
        
        # 更新评分校准数据
        was_predicted_high = result.quality_score > 0.7
        if was_predicted_high:
            self.quality_calibration['predicted_high_executed'] += 1
            if success:
                self.quality_calibration['predicted_high_successful'] += 1
        else:
            self.quality_calibration['predicted_low_executed'] += 1
            if success:
                self.quality_calibration['predicted_low_successful'] += 1
        
        # 如果所有行动都执行完毕，更新状态
        if len(result.execution_results) >= len(result.actions):
            all_success = all(r['success'] for r in result.execution_results)
            result.status = 'verified_success' if all_success else 'verified_partial'
        
        # 发布执行结果事件
        if self.event_bus:
            self.event_bus.publish_simple(
                'self_reflection.action_executed',
                {
                    'reflection_id': reflection_id,
                    'action_id': action_id,
                    'success': success,
                    'outcome': outcome,
                    'reflection_status': result.status
                }
            )
    
    def get_calibration_stats(self) -> Dict:
        """获取评分校准统计"""
        high = self.quality_calibration['predicted_high_executed']
        high_success = self.quality_calibration['predicted_high_successful']
        low = self.quality_calibration['predicted_low_executed']
        low_success = self.quality_calibration['predicted_low_successful']
        
        return {
            'high_quality_predictions': high,
            'high_quality_success_rate': high_success / high if high > 0 else 0,
            'low_quality_predictions': low,
            'low_quality_success_rate': low_success / low if low > 0 else 0,
            'calibration_accuracy': 'accurate' if (high_success/high if high else 0) > 0.7 else 'needs_adjustment'
        }
    
    def _build_reflection_prompt(self, event_state: EventBusState,
                                  errors: List[Dict], metrics: Dict) -> str:
        """构建 prompt"""
        event_summary = []
        if event_state.queue_size > 0:
            event_summary.append(f"队列中有 {event_state.queue_size} 个未处理事件")
            if event_state.event_types:
                event_summary.append(f"事件类型: {json.dumps(event_state.event_types)}")
            if event_state.oldest_event_age_seconds > 300:
                event_summary.append(f"⚠️ 最老事件已积压 {event_state.oldest_event_age_seconds/60:.1f} 分钟")
        else:
            event_summary.append("队列为空")
        
        error_summary = []
        if errors:
            error_summary.append(f"最近1小时有 {len(errors)} 个错误")
            for i, err in enumerate(errors[:3], 1):
                error_summary.append(f"  {i}. {err['content'][:80]}")
        else:
            error_summary.append("最近1小时无错误")
        
        metrics_summary = []
        if metrics.get('memory_percent', 0) > 80:
            metrics_summary.append(f"🚨 内存: {metrics['memory_percent']}% (高)")
        elif metrics.get('memory_percent', 0) > 0:
            metrics_summary.append(f"内存: {metrics['memory_percent']}%")
        
        return f"""你是一个系统自省引擎。基于以下真实状态生成洞察和行动计划。

## 系统状态

### EventBus
{chr(10).join(event_summary)}

### 错误日志
{chr(10).join(error_summary)}

### 指标
{chr(10).join(metrics_summary) if metrics_summary else "正常"}

## 任务

1. 分析模式，找出根因
2. 生成 1-3 个可执行行动
3. 每个行动必须有验证方法

## 输出 (JSON)

```json
{{
  "insights": [{{"observation": "...", "root_cause": "...", "confidence": 0.8}}],
  "actions": [{{"action": "...", "priority": "high", "verification_method": "..."}}],
  "meta": {{"overall_confidence": 0.75}}
}}
```
"""
    
    def _call_llm(self, prompt: str) -> Tuple[str, int]:
        """调用 LLM"""
        if not OPENAI_AVAILABLE or not self.llm_client:
            return self._mock_llm_response(prompt), 0
        
        try:
            response = self.llm_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "系统自省引擎。结构化输出。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            return content, tokens
        except Exception as e:
            return f"错误: {e}", 0
    
    def _mock_llm_response(self, prompt: str) -> str:
        """模拟响应"""
        has_events = "队列中有" in prompt and "队列为空" not in prompt
        has_errors = "最近1小时有" in prompt and "无错误" not in prompt
        
        insights = []
        actions = []
        
        if has_events:
            insights.append({
                "observation": "EventBus 中有积压事件",
                "root_cause": "消费者处理速度不足",
                "confidence": 0.85
            })
            actions.append({
                "action": "检查 EventBus 消费者状态",
                "priority": "high",
                "expected_outcome": "找出瓶颈",
                "verification_method": "查看消费者日志，确认处理速率"
            })
        
        if has_errors:
            insights.append({
                "observation": "最近有错误",
                "root_cause": "待分析",
                "confidence": 0.6
            })
            actions.append({
                "action": "分析错误日志模式",
                "priority": "high",
                "expected_outcome": "识别根因",
                "verification_method": "统计错误类型频率"
            })
        
        if not insights:
            insights.append({
                "observation": "系统正常",
                "root_cause": "无",
                "confidence": 0.95
            })
        
        import json
        return json.dumps({
            "insights": insights,
            "actions": actions,
            "meta": {"overall_confidence": 0.8 if actions else 0.95}
        }, ensure_ascii=False, indent=2)
    
    def _parse_llm_output(self, output: str) -> Tuple[List[Dict], List[Dict]]:
        """解析输出"""
        insights = []
        actions = []
        
        try:
            if "```json" in output:
                json_str = output.split("```json")[1].split("```")[0]
            elif "```" in output:
                json_str = output.split("```")[1].split("```")[0]
            else:
                json_str = output
            
            data = json.loads(json_str.strip())
            insights = data.get("insights", [])
            actions = data.get("actions", [])
        except:
            pass
        
        return insights, actions
    
    def _evaluate_quality(self, insights, actions, input_summary) -> float:
        """评估质量"""
        scores = []
        
        # 基于真实输入
        has_input = any([
            input_summary.get('event_queue_size', 0) > 0,
            input_summary.get('recent_errors_count', 0) > 0,
            input_summary.get('system_memory', 0) > 80
        ])
        if has_input and len(insights) > 0:
            scores.append(0.3)
        elif not has_input and len(insights) == 0:
            scores.append(0.3)
        else:
            scores.append(0.1)
        
        # 可执行性
        if actions:
            executable = sum(1 for a in actions if any(v in a.get('action', '').lower() 
                        for v in ['检查', '分析', '优化', '清理', '重启', '查看']))
            scores.append(0.3 * (executable / len(actions)))
        else:
            scores.append(0)
        
        # 验证方法
        if actions:
            with_verify = sum(1 for a in actions if len(a.get('verification_method', '')) > 10)
            scores.append(0.2 * (with_verify / len(actions)))
        else:
            scores.append(0)
        
        # 置信度合理
        if insights and not any("解析失败" in str(i) for i in insights):
            scores.append(0.2)
        else:
            scores.append(0)
        
        return sum(scores)
    
    def _calculate_confidence(self, insights, actions) -> float:
        """计算置信度"""
        if not insights:
            return 0.95 if not actions else 0.5
        
        confidences = []
        for ins in insights:
            if isinstance(ins, dict):
                confidences.append(ins.get('confidence', 0.5))
        
        return sum(confidences) / len(confidences) if confidences else 0.5
    
    def get_stats(self) -> Dict:
        """获取统计"""
        if not self.reflection_history:
            return {
                'total_reflections': 0,
                'pending_reflections': 0,
                'verified_reflections': 0,
                'avg_quality': 0,
                'total_tokens': 0
            }
        
        qualities = [r.quality_score for r in self.reflection_history]
        pending = sum(1 for r in self.active_reflections.values() if r.status == 'pending')
        verified = sum(1 for r in self.reflection_history if 'verified' in r.status)
        
        return {
            'total_reflections': len(self.reflection_history),
            'pending_reflections': pending,
            'verified_reflections': verified,
            'avg_quality': sum(qualities) / len(qualities),
            'total_tokens': self.total_tokens_used,
            'calibration': self.get_calibration_stats()
        }


# CognitionLoop 订阅示例 (需要添加到 cognition_loop_v2.py)
"""
# 在 CognitionLoop.__init__ 中添加:
self.event_bus.subscribe('self_reflection.complete', self._on_reflection_complete)
self.event_bus.subscribe('self_reflection.action_proposed', self._on_action_proposed)
self.event_bus.subscribe('self_reflection.action_executed', self._on_action_executed)

# 处理方法:
def _on_reflection_complete(self, event):
    data = event.get('data', {})
    quality_score = data.get('quality_score', 0)
    
    if quality_score > 0.7:
        # 高质量洞察，转化为新目标
        summary = data.get('summary', '')
        full_result = data.get('full_result', {})
        
        self.logger.info(f"High quality reflection: {summary}")
        
        # 可以在这里创建新目标或调整优先级
        for action in full_result.get('actions', []):
            if action.get('priority') == 'high':
                # 创建高优先级任务
                pass

def _on_action_proposed(self, event):
    data = event.get('data', {})
    action = data.get('action', {})
    quality_score = data.get('quality_score', 0)
    
    # 根据质量评分决定是否自动执行
    if quality_score > 0.8:
        # 高质量，可以自动执行
        pass
    else:
        # 低质量，需要人工确认
        pass

def _on_action_executed(self, event):
    data = event.get('data', {})
    success = data.get('success', False)
    reflection_id = data.get('reflection_id')
    
    # 反馈给自省引擎
    if self.integrations and hasattr(self.integrations, 'true_reflection'):
        self.integrations.true_reflection.record_execution_result(
            reflection_id=reflection_id,
            action_id=data.get('action_id'),
            success=success,
            outcome=data.get('outcome', ''),
            notes='Executed by CognitionLoop'
        )
"""


def demo_closed_loop():
    """演示完整闭环"""
    print("="*70)
    print("🧠 [Self_Reflection_v1.1] 完整闭环演示")
    print("="*70)
    
    engine = TrueReflectionEngine()
    
    print("\n🔄 第1步：执行自省...")
    result = engine.reflect(force=True)
    
    if not result:
        print("   无问题，跳过自省")
        return
    
    print(f"\n✅ 自省完成")
    print(f"   ID: {result.reflection_id}")
    print(f"   质量: {result.quality_score:.2f}")
    print(f"   洞察: {len(result.insights)}条")
    print(f"   行动: {len(result.actions)}个")
    
    print(f"\n📤 第2步：发布到 EventBus（已自动完成）")
    print(f"   事件: self_reflection.complete")
    print(f"   CognitionLoop 可以订阅并处理")
    
    print(f"\n🎯 第3步：模拟行动执行...")
    for i, action in enumerate(result.actions):
        action_id = f"{result.reflection_id}_act{i}"
        # 模拟执行结果
        success = True  # 假设成功
        outcome = f"执行了: {action.get('action', '')[:40]}"
        
        engine.record_execution_result(
            reflection_id=result.reflection_id,
            action_id=action_id,
            success=success,
            outcome=outcome,
            notes="模拟执行"
        )
        print(f"   行动{i+1}: {'✅' if success else '❌'} {outcome[:50]}")
    
    print(f"\n🔄 第4步：闭环完成")
    print(f"   自省状态: {result.status}")
    print(f"   执行记录: {len(result.execution_results)}条")
    
    print(f"\n📊 校准统计")
    stats = engine.get_calibration_stats()
    print(f"   高质量预测成功率: {stats['high_quality_success_rate']:.1%}")
    print(f"   校准准确度: {stats['calibration_accuracy']}")
    
    print("\n" + "="*70)
    print("✅ 闭环演示完成")
    print("="*70)
    print("\n闭环流程:")
    print("   观察 → 思考 → 发布 → 被订阅 → 行动 → 验证 → 反馈 → 观察")
    print("\n关键改进:")
    print("   • 自省结果发布到 EventBus（被看到）")
    print("   • 行动结果记录并反馈（形成循环）")
    print("   • 评分校准数据积累（自我改进）")


if __name__ == "__main__":
    demo_closed_loop()
