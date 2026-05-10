"""
PlanningModule - 规划模块 v2.1 (BDI集成)

职责：
- 判断是否需要规划
- 根据观察结果生成目标
- 将目标分解为任务
- 任务排序和优先级管理
- BDI决策引擎集成（v3.3）

作者：虾虾
日期：2026-05-01
"""

import time
from typing import Dict, Optional, List, Any


class PlanningModule:
    """
    规划模块 v2.0
    
    从 cognition_loop.py 的 _needs_planning() 和 _plan() 方法迁移而来。
    """
    
    def __init__(self,
                 goal_manager=None,
                 goal_generator=None,
                 curiosity_trigger=None,
                 event_bus=None,
                 logger=None,
                 enable_llm: bool = True,
                 llm_threshold: int = 5,
                 idle_timeout: int = 300,
                 bdi_engine=None,
                 gc_loop=None):
        
        self.goal_manager = goal_manager
        self.goal_generator = goal_generator
        self.curiosity_trigger = curiosity_trigger
        self.event_bus = event_bus
        self.logger = logger
        self.bdi_engine = bdi_engine
        self.gc_loop = gc_loop
        
        self.enable_llm = enable_llm
        self.llm_threshold = llm_threshold
        self.idle_timeout = idle_timeout
        
        self.last_plan_time = 0
        self.rule_handlers: Dict[str, Any] = {}
        self.llm_planner: Optional[Any] = None
        self.tick_count = 0
    
    def needs_planning(self, observation: Any) -> bool:
        """
        判断是否需要规划 (从 cognition_loop._needs_planning 迁移)
        """
        environment = observation.environment if hasattr(observation, "environment") else {}
        
        # 基于时间的触发
        world_data = environment.get("world", {})
        time_ctx = world_data.get("time", {})
        
        if time_ctx.get("special_day"):
            if self.logger:
                self.logger.info(f"Planning triggered by special day: {time_ctx['special_day']}")
            return True
        
        # 系统警报
        alerts = world_data.get("alerts", [])
        if alerts:
            if self.logger:
                self.logger.info(f"Planning triggered by alerts: {len(alerts)} alert(s)")
            return True
        
        # 有未处理的用户消息
        events = observation.events if hasattr(observation, "events") else []
        for event in events:
            if event.get('type') == 'message.received':
                return True
        
        # 有失败的任务
        tasks = observation.tasks if hasattr(observation, "tasks") else []
        for task in tasks:
            if task.get('status') == 'failed':
                return True
        
        # 长时间没有规划
        if time.time() - self.last_plan_time > 600:
            return True
        
        # 有目标但没有活跃任务
        goal = observation.goal if hasattr(observation, "goal") else None
        if goal and not tasks:
            goal_id = goal.get('goal_id')
            if goal_id and self.goal_manager:
                try:
                    g = self.goal_manager.get_goal(goal_id)
                    if g and not g.related_task_ids:
                        return True
                except:
                    pass
        
        return False
    
    def plan(self, observation: Any, active_goal: Optional[Any] = None) -> Optional[Dict]:
        """
        规划阶段 v3.3 — BDI决策集成（MiMo审查修复版）
        
        回退链（优先级从高到低）：
        1. BDI选择（多候选时）
        2. 规则匹配（第一个匹配）
        3. LLM规划
        4. 默认计划
        5. 空计划（保底）
        
        防御性处理：
        - candidate_plans为空 → 返回None
        - BDI失败 → 静默回退到第一个候选
        - 单候选 → 跳过BDI直接返回（性能优化）
        """
        self.tick_count += 1
        
        # === 防御：空输入检查 ===
        if observation is None:
            if self.logger:
                self.logger.warning("plan() called with None observation", component="PlanningModule")
            return None
        
        # 1. 生成候选计划
        try:
            candidate_plans = self._generate_candidates(observation, active_goal)
        except Exception as e:
            if self.logger:
                self.logger.error(f"Candidate generation failed: {e}", component="PlanningModule")
            candidate_plans = []
        
        # === 防御：空候选处理 ===
        if not candidate_plans:
            if self.logger:
                self.logger.info("No candidate plans generated", component="PlanningModule")
            return None
        
        # === v3.3: BDI + GC 安全检查（即使单候选也要走BDI评估）===
        if len(candidate_plans) == 1:
            # 单候选时：BDI评估该候选的匹配度 + GC安全审查
            selected_plan = candidate_plans[0]
            
            # BDI评估（单候选也要计算信念/愿望匹配度）
            if self.bdi_engine:
                try:
                    intention = self.bdi_engine._score_plan(
                        selected_plan,
                        self.bdi_engine.load_beliefs(),
                        self.bdi_engine.load_desires(self.bdi_engine._get_active_goals())
                    )
                    if self.logger:
                        self.logger.info(
                            f"[V3-BDI] Single candidate scored: {intention.bdi_score:.2f}",
                            component="PlanningModule",
                            context={
                                "bdi_score": round(intention.bdi_score, 2),
                                "belief_align": round(intention.belief_alignment, 2),
                                "desire_align": round(intention.desire_alignment, 2),
                                "personality": round(intention.personality_bonus, 2),
                            }
                        )
                    # 注入BDI元数据到plan
                    self._inject_v3_meta(selected_plan, {
                        "source": "v3_bdi_single",
                        "bdi_score": round(intention.bdi_score, 2),
                        "belief_align": round(intention.belief_alignment, 2),
                        "desire_align": round(intention.desire_alignment, 2),
                        "personality_bonus": round(intention.personality_bonus, 2),
                    })
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"[V3-BDI] Single candidate scoring failed: {e}", component="PlanningModule")
            
            # GC Loop 安全审查（即使单候选）
            if self.gc_loop:
                try:
                    gc_result = self.gc_loop.generate_and_review(
                        task_description=f"审查计划: {selected_plan.get('description', '')}",
                        generator_input={"prompt": str(selected_plan)},
                    )
                    # 注入GC元数据
                    self._inject_v3_meta(selected_plan, {
                        "gc_cleared": gc_result.security_cleared,
                        "gc_score": round(gc_result.final_score, 2),
                    })
                    
                    if not gc_result.security_cleared:
                        if self.logger:
                            self.logger.warning(
                                f"[V3-GC] Single candidate FAILED security review",
                                component="PlanningModule"
                            )
                        selected_plan = self._generate_safe_plan(selected_plan)
                        self._inject_v3_meta(selected_plan, {"source": "v3_safe_fallback"})
                    else:
                        if self.logger:
                            self.logger.info(
                                f"[V3-GC] Single candidate security cleared: {gc_result.final_score:.2f}",
                                component="PlanningModule"
                            )
                except Exception as e:
                    if self.logger:
                        self.logger.debug(f"[V3-GC] Single candidate review failed: {e}", component="PlanningModule")
            
            self.last_plan_time = time.time()
            return selected_plan
        
        # 2. BDI选择（多候选时）
        if self.bdi_engine:
            try:
                selected_plan, intentions = self.bdi_engine.select_intention(candidate_plans)
                
                # === 防御：检查BDI返回值 ===
                if selected_plan and isinstance(selected_plan, dict):
                    # 记录BDI决策日志
                    if intentions:
                        best = intentions[0]
                        if self.logger:
                            self.logger.info(
                                f"[V3-BDI] Multi-candidate selected: score={best.bdi_score:.2f}, candidates={len(candidate_plans)}",
                                component="PlanningModule",
                                context={
                                    "bdi_score": round(best.bdi_score, 2),
                                    "belief_align": round(best.belief_alignment, 2),
                                    "desire_align": round(best.desire_alignment, 2),
                                    "personality": round(best.personality_bonus, 2),
                                    "candidates": len(candidate_plans),
                                }
                            )
                        # 注入BDI元数据
                        self._inject_v3_meta(selected_plan, {
                            "source": "v3_bdi_multi",
                            "bdi_score": round(best.bdi_score, 2),
                            "belief_align": round(best.belief_alignment, 2),
                            "desire_align": round(best.desire_alignment, 2),
                            "personality_bonus": round(best.personality_bonus, 2),
                            "candidates": len(candidate_plans),
                        })
                    
                    # v3.3: GC Loop 审查选中的计划
                    if self.gc_loop:
                        try:
                            gc_result = self.gc_loop.generate_and_review(
                                task_description=f"审查计划: {selected_plan.get('description', '')}",
                                generator_input={"prompt": json.dumps(selected_plan)},
                            )
                            if not gc_result.security_cleared:
                                if self.logger:
                                    self.logger.warning(
                                        f"[V3-GC] Multi-candidate plan FAILED security review",
                                        component="PlanningModule"
                                    )
                                # 安全审查失败，回退到下一个候选
                                if len(candidate_plans) > 1:
                                    fallback_plan = candidate_plans[1]
                                    selected_plan = fallback_plan  # 实际回退
                                    if self.logger:
                                        self.logger.warning(
                                            f"[V3-GC] Fallback from candidate 0 to candidate 1: "
                                            f"reason=security_failed, "
                                            f"original={selected_plan.get('description', '')[:30]}, "
                                            f"fallback={fallback_plan.get('description', '')[:30]}",
                                            component="PlanningModule",
                                            context={
                                                "fallback_reason": "security_failed",
                                                "from_index": 0,
                                                "to_index": 1,
                                                "original_source": selected_plan.get('source', 'unknown'),
                                                "fallback_source": fallback_plan.get('source', 'unknown'),
                                            }
                                        )
                                # 注入GC元数据
                                self._inject_v3_meta(selected_plan, {
                                    "source": "v3_bdi_multi_fallback",
                                    "gc_cleared": False,
                                })
                            else:
                                if self.logger:
                                    self.logger.info(
                                        f"[V3-GC] Multi-candidate plan security cleared: {gc_result.final_score:.2f}",
                                        component="PlanningModule"
                                    )
                                # 注入GC元数据
                                self._inject_v3_meta(selected_plan, {
                                    "source": "v3_bdi_multi",
                                    "gc_cleared": True,
                                    "gc_score": round(gc_result.final_score, 2),
                                })
                        except Exception:
                            pass  # GC失败不阻塞
                    
                    self.last_plan_time = time.time()
                    return selected_plan
                else:
                    # BDI返回了None或非法值，静默回退
                    if self.logger:
                        self.logger.warning("BDI returned invalid plan, falling back", component="PlanningModule")
            except Exception as e:
                # === BDI失败 → 静默回退，不阻塞 ===
                if self.logger:
                    self.logger.warning(f"BDI failed: {e}, using fallback", component="PlanningModule")
        
        # 3. 回退：选第一个候选（保底）
        self.last_plan_time = time.time()
        if self.logger:
            self.logger.info(f"Fallback to first candidate: {candidate_plans[0].get('description', 'unknown')[:50]}")
        return candidate_plans[0]
    
    def _generate_candidates(self, observation: Any, active_goal: Optional[Any]) -> List[Dict]:
        """
        生成候选计划列表
        
        当前策略：
        1. 规则匹配（最多1个）
        2. LLM规划（最多1个）
        3. 默认候选（基于目标类型）
        
        未来扩展：LATS树搜索生成多路径
        """
        candidates = []
        goal_desc = observation.goal.get('description') if hasattr(observation, "goal") and observation.goal else None
        
        # 1. 规则匹配
        for trigger, handler in self.rule_handlers.items():
            if self._match_trigger(trigger, observation):
                plan = handler(observation)
                if plan:
                    plan["source"] = "rule"
                    plan["trigger"] = trigger
                    candidates.append(plan)
        
        # 2. LLM 规划
        if self.enable_llm and self.llm_planner and self.tick_count >= self.llm_threshold:
            try:
                plan = self.llm_planner(observation.to_dict() if hasattr(observation, "to_dict") else {})
                if plan:
                    plan["source"] = "llm"
                    candidates.append(plan)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"LLM planning failed: {e}")
        
        # 3. 默认候选（基于目标描述）
        if not candidates and goal_desc:
            default_plan = self._generate_default_plan(goal_desc)
            if default_plan:
                candidates.append(default_plan)
        
        return candidates
    
    def _inject_v3_meta(self, plan: Dict, meta_data: Dict) -> Dict:
        """安全注入V3元数据（带异常保护）"""
        try:
            if "_meta" not in plan:
                plan["_meta"] = {"v3": True}
            plan["_meta"].update(meta_data)
            plan["_meta"]["tick_timestamp"] = time.time()
            plan["_meta"]["plan_id"] = plan.get("plan_id", f"v3_{int(time.time())}")
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[V3-Meta] Meta injection failed: {e}", component="PlanningModule")
        return plan

    def _generate_safe_plan(self, unsafe_plan: Dict) -> Dict:
        """当原计划未通过安全审查时，生成一个安全的替代计划"""
        safe_plan = unsafe_plan.copy()
        safe_plan["plan_id"] = f"safe_{int(time.time())}"
        safe_plan["description"] = f"[安全替代] {unsafe_plan.get('description', 'unknown')}"
        safe_plan["source"] = "safe_fallback"
        # 清空可能有风险的步骤，替换为观察/等待
        safe_plan["steps"] = [{"step_id": "safe_1", "action": "等待进一步指令", "type": "internal"}]
        return safe_plan
    
    def _generate_default_plan(self, goal_desc: str) -> Optional[Dict]:
        """基于目标描述生成默认计划"""
        steps = []
        """基于目标描述生成默认计划"""
        steps = []
        
        # 根据关键词匹配默认步骤
        if any(kw in goal_desc.lower() for kw in ["search", "查询", "调研", "find"]):
            steps = [
                {"step_id": "s1", "action": f"search for {goal_desc}", "type": "tool", "tool_name": "search"},
                {"step_id": "s2", "action": "analyze results", "type": "internal"},
            ]
        elif any(kw in goal_desc.lower() for kw in ["write", "写", "create", "创建"]):
            steps = [
                {"step_id": "s1", "action": f"write {goal_desc}", "type": "tool", "tool_name": "write"},
            ]
        elif any(kw in goal_desc.lower() for kw in ["learn", "学习", "explore", "探索"]):
            steps = [
                {"step_id": "s1", "action": f"learn about {goal_desc}", "type": "tool", "tool_name": "search"},
                {"step_id": "s2", "action": "summarize findings", "type": "internal"},
            ]
        else:
            steps = [
                {"step_id": "s1", "action": goal_desc, "type": "internal"},
            ]
        
        return {
            "plan_id": f"default_{int(time.time())}",
            "description": goal_desc,
            "steps": steps,
            "source": "default",
            "total_steps": len(steps),
        }
    
    def _inject_v3_meta(self, plan: Dict, meta_data: Dict) -> Dict:
        """安全注入V3元数据（带异常保护）"""
        try:
            if "_meta" not in plan:
                plan["_meta"] = {"v3": True}
            plan["_meta"].update(meta_data)
            plan["_meta"]["tick_timestamp"] = time.time()
            plan["_meta"]["plan_id"] = plan.get("plan_id", f"v3_{int(time.time())}")
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[V3-Meta] Meta injection failed: {e}", component="PlanningModule")
        return plan

    def _generate_safe_plan(self, unsafe_plan: Dict) -> Dict:
        """生成安全的替代计划"""
        safe_plan = unsafe_plan.copy()
        safe_plan["plan_id"] = f"safe_{int(time.time())}"
        safe_plan["source"] = "safe_fallback"
        safe_plan["description"] = f"[安全审查通过] {safe_plan.get('description', '')}"
        # 过滤危险步骤
        safe_steps = []
        for step in safe_plan.get("steps", []):
            action = str(step.get("action", "")).lower()
            if any(dangerous in action for dangerous in ["rm -rf", "delete all", "drop table", "shutdown"]):
                # 替换为安全步骤
                safe_steps.append({
                    "step_id": step.get("step_id", "safe"),
                    "action": "等待用户确认后执行",
                    "type": "internal",
                    "note": "原步骤被安全审查拦截"
                })
            else:
                safe_steps.append(step)
        safe_plan["steps"] = safe_steps
        return safe_plan
    
    def _match_trigger(self, trigger: str, observation: Any) -> bool:
        """匹配触发条件"""
        events = observation.events if hasattr(observation, "events") else []
        for event in events:
            if event.get('type') == trigger:
                return True
        return False
    
    def register_rule_handler(self, trigger: str, handler):
        """注册规则处理器"""
        self.rule_handlers[trigger] = handler
    
    def set_llm_planner(self, planner):
        """设置 LLM 规划器"""
        self.llm_planner = planner


# ============== 快速测试 ==============
if __name__ == "__main__":
    pm = PlanningModule()
    plan = pm.plan({"queue_size": 0, "user_input_detected": False})
    print("=== PlanningModule v1.0 ===")
    print(f"Plan: {plan}")
    print("✅ PlanningModule skeleton ready")
