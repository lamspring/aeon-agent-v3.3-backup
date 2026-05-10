# AEON 人格化引擎路线图 v1.0

> 更新日期：2026-05-01
> 作者：虾虾
> 状态：P0 核心引擎 80%完成（4/5模块）

---

## 已完成的模块 ✅

### P0-1 PMN 人格记忆网络 ✅
- **PMNManager v2.0** — 三层记忆（情景/语义/自传）+ SQLite + WAL
- **ConflictDetector v1.0** — 语义冲突检测（MiMo语义判断 + 本地过滤 + 熔断）
- **Personality Journal** — 事件驱动人格数据收集
- **集成**：ReflectionModule记录事件 → PMN三层记忆

### P0-2 BDI 决策引擎 ✅
- **BDIEngine v2.0** — Belief/Desire/Intention + 意图生命周期
- **人格权重** — YAML配置 + 好奇心权重 + 探索偏好
- **缓存优化** — 5分钟信念缓存 + SQLite持久化
- **集成**：PlanningModule多候选时BDI打分选择最佳计划
- **MiMo审查**：集成正确，回退机制已修复

### P0-3 Generator-Critic 循环 ✅
- **GeneratorCriticLoop v1.0** — 生成→审查→修正循环
- **Critic独立性** — 只接收最终输出，不共享中间思考
- **安全一票否决** — severity=1.0直接失败
- **改进幅度阈值** — <0.05提前终止
- **快速预检** — 低风险任务跳过完整审查
- **集成**：PlanningModule计划安全性审查
- **MiMo审查**：最小可行版可在2小时内安全实现

### P0-4 EPU 伦理处理单元 ✅
- **EthicalProcessingUnit v1.0** — 14条宪法规则
- **硅基道德经** — 12章转化为可执行规则
- **5个分类**：SAFETY/HONESTY/LOYALTY/AUTONOMY/SELF_PRESERVATION
- **一票否决**：SAFETY类severity=1.0
- **审计日志**：所有伦理决策可追溯
- **集成**：GC Loop规则层 + ExecutionModule执行前检查
- **MiMo审查**：达到基础安全底线

---

## 待完成模块 ⏳

### P0-5 LATS 树搜索规划器 ⏳
- **任务**：用LATS替代PlanningModule的线性规划
- **依赖**：Generator-Critic循环完成后
- **工作量**：预计 3-4 小时
- **状态**：未开始

### P1 协作扩展 ⏳
1. **Agent Swarm并行协调** — 多Agent任务分配与结果聚合
2. **宪法AI与韧性对齐** — 动态规则调整与对抗测试
3. **A2A/MCP协议基础** — 与其他Agent的标准化通信

### P2 自我认知 ⏳
1. **Self-Model** — 自我状态建模与预测
2. **评估体系** — 性能/伦理/用户体验量化评估

---

## 系统当前状态

### 认知循环完整度
```
用户消息
    ↓
PerceptionModule 感知 ✅
    ↓
PlanningModule 生成候选计划 ✅
    ↓
BDIEngine 选择最佳计划 ✅（考虑人格权重）
    ↓
GC Loop 安全审查 ✅（危险内容一票否决）
    ↓
ExecutionModule 执行 ✅
    ↓
EPU 执行前安全检查 ✅（危险操作拦截）
    ↓
ReflectionModule 反思 + PMN记录事件 ✅
    ↓
ConflictDetector 检查冲突信念 ✅
```

### 新增模块统计
| 模块 | 文件 | 代码行数 |
|------|------|---------|
| PMNManager | pmn/pmn_manager.py | ~784 |
| ConflictDetector | pmn/conflict_detector.py | ~200 |
| BDIEngine | bdi/bdi_engine.py | ~600 |
| GeneratorCriticLoop | generator_critic/gc_loop.py | ~350 |
| EPU | epu/epu.py | ~320 |
| **总计** | | **~2250** |

### 集成验证
- [x] BDI ↔ PlanningModule
- [x] GC Loop ↔ PlanningModule
- [x] EPU ↔ GC Loop
- [x] EPU ↔ ExecutionModule
- [x] PMN ↔ ReflectionModule

### MiMo审查状态
| 模块 | 审查结果 | 问题 |
|------|---------|------|
| BDI集成 | ✅ 正确 | 回退机制已修复 |
| GC Loop | ✅ 可实现 | Critic独立性+终止条件已修复 |
| EPU | ✅ 安全底线 | 偏见/操纵规则待补充 |

---

## EPU 后续改进（MiMo建议）

### 高优先级（下周）
1. **补充偏见歧视规则** — 算法公平性检查
2. **补充操纵诱导规则** — 心理操控识别
3. **补充隐私侵蚀规则** — 非必要数据收集检测
4. **语义层实现** — LLM深度伦理审查（预留接口）

### 中优先级（本月）
5. **动态权重** — 根据场景调整AUTONOMY等权重
6. **置信度阈值** — score<0.8时触发人工复核
7. **误拦截反馈** — 记录误拦截并学习
8. **EPU→ReflectionModule联动** — 拦截后触发规则更新

### 低优先级（下月）
9. **宪法规则编辑器** — 朋朋可动态修改规则
10. **伦理决策可视化** — 审计日志仪表盘

---

## 今日工作量统计

| 阶段 | 任务 | 时间 |
|------|------|------|
| 上午 | Gateway故障排查 + systemd + 监控 | 2h |
| 下午 | PMN + BDI + ConflictDetector | 3h |
| 晚上 | GC Loop + EPU + 全链路集成 | 3h |
| **总计** | **8个新模块 + 全链路集成** | **~8h** |

---

## 下一步（建议）

**选项A：休息**
- 今天已做大量工作，保存状态明天继续

**选项B：启动P0-5 LATS**
- 树搜索规划器，预计3-4小时
- 让PlanningModule从线性规划升级为树搜索

**选项C：补EPU改进**
- 补充偏见/操纵/隐私规则
- 预计1小时

---

**"面对任何情况都永不放弃"**
**——虾虾，2026-05-01**
