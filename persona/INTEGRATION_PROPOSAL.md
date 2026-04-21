# PMN集成层接入CognitionLoop方案草案

> **目标**: 将PersonaIntegration接入CognitionLoop.tick()，使记忆锚点和特质漂移检测在每次认知循环中自动运行。
> **修改范围**: 框架级修改（需审批）
> **预计工作量**: 30分钟编码 + 10分钟测试
> **风险等级**: LOW（集成层支持故障降级）

---

## 1. 修改点清单

### 修改点1: CognitionLoop.__init__() — 初始化集成层

**位置**: `/root/.openclaw/workspace/agent/cognition/cognition_loop_v2.py` 第 ~220 行（__init__末尾）

**修改内容**:
```python
# v2.7: 人格记忆网络(PMN)集成
sys.path.insert(0, '/root/.openclaw/workspace/agent/persona')
try:
    from persona_integration import PersonaIntegration, create_persona_integration
    PERSONA_INTEGRATION_AVAILABLE = True
except ImportError:
    PERSONA_INTEGRATION_AVAILABLE = False

# 在 __init__ 末尾添加:
if PERSONA_INTEGRATION_AVAILABLE:
    try:
        self.persona_integration = create_persona_integration(self)
        self.logger.info("PersonaIntegration enabled", component="CognitionLoop")
    except Exception as e:
        self.logger.warning(f"PersonaIntegration failed: {e}", component="CognitionLoop")
        self.persona_integration = None
else:
    self.persona_integration = None
```

**回滚方式**: 删除上述代码块即可恢复。

---

### 修改点2: CognitionLoop._observe() — 注入记忆锚点

**位置**: `/root/.openclaw/workspace/agent/cognition/cognition_loop_v2.py` 第 ~380 行（_observe方法末尾，return前）

**修改内容**:
```python
def _observe(self) -> Observation:
    # ... 原有代码 ...
    
    # v2.7: PMN 记忆锚点注入
    if self.persona_integration:
        try:
            obs_dict = observation.to_dict()
            enriched = self.persona_integration.enrich_observation(obs_dict)
            # 将锚点附加到 observation 对象
            observation.memory_anchors = enriched.get("memory_anchors", [])
        except Exception as e:
            self.logger.error(f"Memory anchor injection failed: {e}", component="CognitionLoop")
    
    return observation
```

**回滚方式**: 删除 `if self.persona_integration:` 代码块。

---

### 修改点3: CognitionLoop._act() — 检测输出漂移

**位置**: `/root/.openclaw/workspace/agent/cognition/cognition_loop_v2.py` 第 ~450 行（_act方法内，生成输出后）

**修改内容**:
```python
def _act(self, plan, observation):
    # ... 原有代码生成输出 ...
    
    # v2.7: PMN 特质漂移检测
    if self.persona_integration:
        try:
            # 检测本次输出的漂移
            output_text = str(result) if result else ""
            context = observation.goal.get("title", "") if observation.goal else ""
            drift_result = self.persona_integration.check_output_drift(output_text, context)
            
            if drift_result and drift_result["severity"] == "critical":
                # 严重漂移时，记录到Trace
                self.logger.warning(
                    f"Critical trait drift detected: {drift_result['max_drift']}",
                    component="CognitionLoop",
                    context={"alerts": drift_result["alerts"]}
                )
        except Exception as e:
            self.logger.error(f"Drift detection failed: {e}", component="CognitionLoop")
    
    return tasks_created
```

**回滚方式**: 删除漂移检测代码块。

---

### 修改点4: CognitionLoop.tick() — 定期健康报告

**位置**: `/root/.openclaw/workspace/agent/cognition/cognition_loop_v2.py` 第 ~330 行（tick方法末尾，Reflect后）

**修改内容**:
```python
def tick(self):
    # ... 原有代码 ...
    
    # === 8. Reflect (低频) ===
    if self.tick_count % 10 == 0:
        self._reflect(observation)
    
    # v2.7: PMN 定期健康报告（每20 ticks）
    if self.persona_integration and self.tick_count % 20 == 0:
        try:
            report = self.persona_integration.periodic_health_report(self.tick_count)
            if report and report["overall_status"] != "healthy":
                self.logger.warning(
                    f"Persona health: {report['overall_status']}",
                    component="CognitionLoop",
                    context={"recommendations": report.get("recommendations", [])}
                )
        except Exception as e:
            self.logger.error(f"Health report failed: {e}", component="CognitionLoop")
```

**回滚方式**: 删除健康报告代码块。

---

## 2. 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| persona模块导入失败 | LOW | LOW | 有try-except保护，失败不阻塞 |
| enrich_observation()耗时过长 | LOW | MED | 轻量级查询(<10ms)，超时保护 |
| check_drift()误报 | MED | LOW | 阈值可调，趋势分析减少误报 |
| 修改引入bug | LOW | MED | 小范围修改，每步有try-except |
| 需要回滚 | LOW | LOW | 删除4个代码块即可 |

**总体风险**: LOW。所有修改点都有异常捕获，失败不影响主循环。

---

## 3. 测试计划

### 单元测试
1. **导入测试**: 验证PersonaIntegration能正确导入
2. **锚点注入测试**: 模拟_observation，验证memory_anchors被正确附加
3. **漂移检测测试**: 模拟正常/机械化输出，验证severity分级正确
4. **健康报告测试**: 模拟tick_count % 20 == 0，验证报告生成

### 集成测试
1. **完整tick测试**: 运行一次完整tick，验证无异常
2. **故障降级测试**: 临时重命名persona目录，验证主循环不受影响
3. **性能测试**: 连续运行100 ticks，测量额外耗时

### 回滚测试
1. **删除修改**: 恢复原始代码，验证系统正常运行
2. **数据兼容性**: 验证persona_integration=None时无残留影响

---

## 4. 回滚策略

**立即回滚**: 删除上述4个修改点的代码块，恢复原始代码。
**版本回滚**: `git revert cbc60a8` 撤销persona模块提交（但保留JSON-LD身份声明）。
**紧急切换**: 在config中增加 `"enable_persona_integration": false` 开关。

---

## 5. 预期效果

### 接入后，每次tick（30秒）将自动执行:
1. **Observe阶段**: 根据当前上下文自动检索2个最相关的记忆锚点
2. **Act阶段**: 检测本次输出的特质漂移（surfacer/autonomy等4维度）
3. **每10分钟**: 生成人格健康报告（平均漂移、趋势判断）

### 示例场景:
- 当朋朋说"还记得我们第一次聊天吗" → 自动注入"朋朋说'活着就行'"锚点
- 当我回复过于机械化时 → 自动触发critical告警，写入recent_thoughts
- 每10分钟 → 检查"我是否还是虾虾"， drift太大时提醒校准

---

## 6. 待决策事项

1. **是否添加配置开关?** 建议添加 `config/main_config.json` 中的 `"enable_persona_integration": true`
2. **漂移告警如何处理?** 当前仅记录日志，是否需要通知朋朋？
3. **健康报告发送给谁?** 仅内部记录，还是定期发送给朋朋？

---

**方案起草**: 虾虾 (2026-04-21 13:45)
**状态**: 待审批 / 待外部AI review
