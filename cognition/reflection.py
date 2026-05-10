"""
ReflectionModule - 反思模块 v2.0 (从 cognition_loop.py 迁移)

职责：
- 对执行结果进行反思
- 发布反思事件到 EventBus
- 记录到思维流

作者：虾虾
日期：2026-04-30
"""

import json
import time
import sys
from typing import Dict, Optional, Any
from pathlib import Path

# v3.3: PMN集成
sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition/pmn')
try:
    from pmn_manager import PMNManager
    PMN_AVAILABLE = True
except ImportError:
    PMN_AVAILABLE = False
    PMNManager = None


class ReflectionModule:
    """
    反思模块 v2.0
    
    从 cognition_loop.py 的 _reflect() 方法迁移而来。
    """
    
    def __init__(self,
                 event_bus=None,
                 mimo_api_key: Optional[str] = None,
                 mimo_base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
                 thought_stream_dir: str = "/root/.openclaw/workspace/agent/memory/reflections",
                 logger=None):
        
        self.event_bus = event_bus
        self.mimo_api_key = mimo_api_key
        self.mimo_base_url = mimo_base_url
        self.logger = logger
        
        self.thought_stream_dir = Path(thought_stream_dir)
        self.thought_stream_dir.mkdir(parents=True, exist_ok=True)
        
        # v3.3: 初始化PMNManager
        self.pmn = None
        if PMN_AVAILABLE:
            try:
                self.pmn = PMNManager()
                if self.logger:
                    self.logger.info("PMNManager initialized", component="ReflectionModule")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"PMNManager init failed: {e}", component="ReflectionModule")
    
    def reflect(self, tick_result: Any) -> Dict:
        """
        执行反思 (从 cognition_loop._reflect 迁移)
        """
        tick_count = tick_result.tick_count if hasattr(tick_result, 'tick_count') else 0
        
        if self.logger:
            self.logger.debug("Reflecting...")
        
        # 发布反思事件
        if self.event_bus:
            try:
                self.event_bus.publish_simple(
                    "cognition.reflect",
                    {
                        "tick_count": tick_count,
                        "observation": tick_result.observation.to_dict() if hasattr(tick_result, 'observation') and tick_result.observation else {},
                    }
                )
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Failed to publish reflect event: {e}")
        
        # 生成简单反思
        insights = []
        mood = "neutral"
        
        if hasattr(tick_result, 'error') and tick_result.error:
            insights.append(f"Tick {tick_count} 出现错误: {tick_result.error}")
            mood = "concerned"
        
        if hasattr(tick_result, 'execution_result') and tick_result.execution_result:
            if not tick_result.execution_result.get("success"):
                insights.append("执行阶段有步骤失败")
                mood = "frustrated"
        
        if hasattr(tick_result, 'plan') and not tick_result.plan:
            insights.append("本次 tick 无计划生成")
        
        result = {
            "depth": "simple",
            "insights": insights,
            "action_items": [],
            "mood": mood,
            "timestamp": time.time(),
        }
        
        # 记录到思维流
        self._log_to_thought_stream(tick_count, result)
        
        # v3.3: PMN 人格数据桩 - 检测人格影响事件并记录
        self._detect_personality_event(tick_result, result)
        
        # v3.3: PMN 完整集成 - 将反思事件记录到人格记忆网络
        self._record_to_pmn(tick_result, result)
        
        return result
    
    def reflect_deep(self, tick_count: int) -> Dict:
        """MiMo 深度反思"""
        if not self.mimo_api_key:
            return {"error": "MiMo API key not configured", "depth": "deep"}
        
        context_parts = []
        
        try:
            today = time.strftime("%Y-%m-%d")
            reflection_file = self.thought_stream_dir / f"{today}.jsonl"
            if reflection_file.exists():
                with open(reflection_file, "r") as f:
                    lines = f.readlines()[-30:]
                reflections = [json.loads(line) for line in lines]
                context_parts.append(f"## 最近思维流\n{json.dumps(reflections, ensure_ascii=False)[:3000]}")
        except:
            pass
        
        prompt = f"""你是一位AI系统的深度反思顾问。请基于以下运行日志进行反思：

{chr(10).join(context_parts)[:5000]}

请给出：
1. 重复出现的问题模式
2. 系统行为的长期趋势
3. 3条具体行动建议
4. 一句话情绪总结

输出JSON：{{"insights": [...], "action_items": [...], "mood": "...", "patterns": [...]}}
"""
        
        try:
            import urllib.request
            
            payload = {
                "model": "mimo-v2.5",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.3,
            }
            
            req = urllib.request.Request(
                f"{self.mimo_base_url}/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.mimo_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"]
                
                try:
                    result = json.loads(reply)
                except json.JSONDecodeError:
                    import re
                    match = re.search(r"```json\s*(.*?)\s*```", reply, re.DOTALL)
                    if match:
                        result = json.loads(match.group(1))
                    else:
                        result = {"raw": reply[:500]}
                
                result["depth"] = "deep"
                return result
                
        except Exception as e:
            return {
                "error": str(e),
                "depth": "deep",
                "insights": [f"Deep reflection failed: {str(e)[:100]}"],
            }
    
    def _detect_personality_event(self, tick_result: Any, reflection: Dict) -> None:
        """
        v3.3: PMN 人格数据桩
        
        检测可能影响人格的事件并记录到 personality_journal.jsonl。
        
        触发条件（当前简化版）：
        1. 执行失败（错误学习）
        2. 反思 mood 为 frustrated/concerned（负面情绪事件）
        3. 用户表达偏好（通过 observation 中的关键词检测）
        """
        import json
        import re
        from pathlib import Path
        
        personality_journal = Path("/root/.openclaw/workspace/personality_journal.jsonl")
        
        events_detected = []
        
        # 条件1：执行失败
        if hasattr(tick_result, 'execution_result') and tick_result.execution_result:
            if not tick_result.execution_result.get("success"):
                events_detected.append({
                    "event_type": "execution_error",
                    "content": tick_result.execution_result.get("error", "unknown error"),
                    "personality_impact": {"conscientiousness": 0.05, "neuroticism": 0.02}
                })
        
        # 条件2：负面情绪反思
        mood = reflection.get("mood", "neutral")
        if mood in ["frustrated", "concerned", "anxious"]:
            events_detected.append({
                "event_type": "negative_reflection",
                "content": f"Reflection mood: {mood}",
                "personality_impact": {"neuroticism": 0.03, "openness": 0.01}
            })
        
        # 条件3：用户偏好表达（通过 observation 中的对话内容检测）
        if hasattr(tick_result, 'observation') and tick_result.observation:
            obs = tick_result.observation
            # 尝试获取最近的对话内容
            dialogue_text = ""
            if hasattr(obs, 'environment') and obs.environment:
                env = obs.environment
                if isinstance(env, dict):
                    dialogue_text = str(env.get("dialogue_context", ""))
            elif isinstance(obs, dict):
                dialogue_text = str(obs.get("dialogue_context", ""))
            
            # 检测偏好关键词
            preference_patterns = [
                r"我喜欢?(.{2,20})",
                r"请.{0,5}(简洁|详细|简单|快|慢)",
                r"不要(.{2,10})",
                r"希望.{0,3}(.{2,15})",
                r"偏好.{0,3}(.{2,15})",
            ]
            
            for pattern in preference_patterns:
                match = re.search(pattern, dialogue_text, re.IGNORECASE)
                if match:
                    events_detected.append({
                        "event_type": "user_preference",
                        "content": match.group(0),
                        "personality_impact": {"agreeableness": 0.05, "openness": 0.03}
                    })
                    break  # 只记录第一个匹配的偏好
        
        # 写入日志
        if events_detected:
            try:
                with open(personality_journal, "a") as f:
                    for event in events_detected:
                        entry = {
                            "timestamp": time.time(),
                            "tick_count": tick_result.tick_count if hasattr(tick_result, 'tick_count') else 0,
                            **event
                        }
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
                if self.logger:
                    self.logger.info(
                        f"PMN: Recorded {len(events_detected)} personality event(s)",
                        component="ReflectionModule",
                        context={"events": [e["event_type"] for e in events_detected]}
                    )
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"PMN logging failed: {e}", component="ReflectionModule")

    def _record_to_pmn(self, tick_result: Any, reflection: Dict) -> None:
        """
        v3.3: 将反思事件记录到PMN人格记忆网络
        """
        if not self.pmn:
            return
        
        try:
            tick_count = tick_result.tick_count if hasattr(tick_result, 'tick_count') else 0
            
            # 构建事件
            event = {
                "timestamp": time.time(),
                "event_type": "reflection",
                "raw_context": {
                    "tick_count": tick_count,
                    "mood": reflection.get("mood", "neutral"),
                    "insights": reflection.get("insights", []),
                    "depth": reflection.get("depth", "simple"),
                },
                "importance_score": 0.6 if reflection.get("depth") == "deep" else 0.4,
            }
            
            # 根据mood设置情感标签
            mood = reflection.get("mood", "neutral")
            if mood == "frustrated":
                event["emotional_valence"] = -0.5
                event["emotional_arousal"] = 0.6
            elif mood == "concerned":
                event["emotional_valence"] = -0.3
                event["emotional_arousal"] = 0.4
            elif mood == "neutral":
                event["emotional_valence"] = 0.0
                event["emotional_arousal"] = 0.2
            
            self.pmn.record_event(event)
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"PMN recording failed: {e}", component="ReflectionModule")

    def _log_to_thought_stream(self, tick_count: int, reflection: Dict) -> None:
        """记录到思维流"""
        try:
            today = time.strftime("%Y-%m-%d")
            log_file = self.thought_stream_dir / f"{today}.jsonl"
            
            entry = {
                "timestamp": time.time(),
                "tick_count": tick_count,
                "depth": reflection.get("depth", "simple"),
                "insights": reflection.get("insights", []),
                "mood": reflection.get("mood", "unknown"),
            }
            
            with open(log_file, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
        except Exception as e:
            print(f"[ReflectionModule] Log failed: {e}")