# MIMO 架构审查报告 —— AEON P2 结构化摘要层

**审查代号：** MIMO-P2-001  
**审查对象：** AEON v3.3 日报结构化摘要层设计方案  
**审查日期：** 2026-05-03  
**审查员：** MIMO（系统架构审查员）  

---

## 一、当前系统快照（审查基础）

| 组件 | 状态 | 关键发现 |
|------|------|----------|
| `session_sync.py` | P1 已完成 | 每30分钟扫描session files，写入`events.db`。代码干净、单一职责、去重逻辑完善。同步约143MB数据无压力。 |
| `daily_summary.py` | P0 已完成 | 先调`sync_sessions()`，再读session files + events.db，LLM生成日报。当前有基础规则分类（is_question/is_emotion/is_work），但非常粗糙。 |
| `events.db` | 运行中 | 143MB，单表`events`，支持status/retry/TTL/expires_at。索引完善。支持按type、status、timestamp高效查询。 |
| `CognitionLoop` | v3.3运行中 | 30秒tick，Reflect每10 tick（5分钟），Introspection每50 tick（25分钟）。已有ReflectionModule和PMN集成。 |
| `GoalManager` | v3.1 | 完整生命周期管理，与EventBus集成。 |
| `EventBus v2` | 运行中 | 支持TTL、重试、两阶段ACK、异步处理器。可扩展新事件类型。 |
| Memory体系 | 已建立 | `memory/YYYY-MM-DD.md`日记 + `MEMORY.md`长期记忆。 |

**诊断结论：** 基础设施就绪，数据通路已打通（session files → events.db），但**分析层是空白**——从原始消息到日报之间存在一个"结构化理解缺口"。

---

## 二、六问审查

### 问题1：架构位置 —— 结构化摘要应该在哪一层生成？

#### 各方案分析

**方案A：session_sync.py 同步时实时生成摘要**
- ❌ **否决**。session_sync当前是数据摄取层（ETL中的E），职责单一且正确。如果插入分析逻辑：
  - 每次同步都要调LLM → 成本爆炸（每30分钟调一次，一天48次）
  - 同步失败和摘要失败耦合 → 可靠性下降
  - 增量消息缺乏上下文 → "帮我修bug"这条消息单独归类为"技术"是对的，但不知道朋朋之前3小时在修什么

**方案B：daily_summary.py 生成日报时一次性LLM分析**
- ⚠️ **部分可行，但有缺陷**。当前daily_summary.py就是这么做的，但问题是：
  - 日报prompt把"统计+预览+要求"塞在一起，LLM既要理解又要生成，容易"即兴发挥"（编造）
  - 没有中间层沉淀结构化数据 → 明天无法对比"今天vs昨天"的情绪变化
  - 日报=最终产物，无法被其他模块复用（比如ProactiveCommunicator想基于"今天很累"主动发消息，它读不到这个信号）

**方案C：新增 digest_engine.py，定时生成结构化摘要**
- ✅ **推荐（主方案）**。独立模块，专注"从原始消息到结构化理解"：
  - 每天02:45运行（早于daily_summary的03:00，给它喂数据）
  - 先规则预处理（降低LLM负担和成本），再LLM精分析
  - 产出结构化JSON → 存入events.db → 供daily_summary和其他模块消费
  - 职责清晰：digest_engine负责"理解"，daily_summary负责"表达"

**方案D：CognitionLoop Reflect阶段自动生成**
- ❌ **否决**。Reflect每5分钟一次，频率太高：
  - 日维度分析不需要5分钟粒度
  - CognitionLoop是实时响应系统，不适合批分析
  - 会增加tick耗时，影响响应延迟
  - 50 tick自省（25分钟）仍然太频繁，且自省关注"系统健康"而非"用户理解"

#### 建议架构

```
session files ──→ session_sync.py ──→ events.db (raw messages)
                                              │
                                              ↓
                    ┌───────────────── digest_engine.py (02:45 cron)
                    │                    - 规则预处理
                    │                    - LLM结构化分析（1次/天）
                    │                    - 产出 digest JSON
                    │                           │
                    │                           ↓
daily_summary.py ←┘                    events.db (daily.digest)
(03:00 cron)         ──→ 读digest而非raw messages
                         ──→ 生成有温度、有虾虾视角的日报
                         ──→ 发送给朋朋
```

---

### 问题2：存储设计 —— 结构化摘要存在哪？

#### 各方案分析

**方案A：扩展 events.db 新增 `daily.digest` 类型事件** ✅ **推荐**
- 优势：
  - 统一存储，查询方便：`SELECT * FROM events WHERE type='daily.digest' ORDER BY timestamp DESC`
  - 复用现有TTL机制（digest可设7天TTL，自动清理）
  - 复用EventBus的发布/订阅机制，其他模块可监听
  - 不增加运维复杂度（一个DB文件 vs 多个）
- 劣势：
  - events.db已达143MB，继续增长需要监控（但SQLite处理GB级无压力）
  - digest JSON可能较大（需控制<10KB）

**方案B：新建 `digests.db` 专门存储**
- ⚠️ **过度设计**。当前数据量不需要分库。增加连接管理、备份、迁移成本。除非digest结构完全异构（需要独立表schema），否则没必要。

**方案C：JSON文件 `agent/digests/YYYY-MM-DD.json`**
- ❌ **否决**。不可查询、无TTL、无事件机制、需自己管理并发和清理。与整个AEON的事件驱动架构格格不入。

**方案D：直接存在 MEMORY.md 或 memory/YYYY-MM-DD.md**
- ❌ **否决**。MEMORY.md是" curated wisdom"（人工精选记忆），不适合存放机器生成的结构化数据。且markdown格式不利于程序消费。

#### 具体建议

```sql
-- 新增事件类型（代码层面）
EventBus.publish_simple("daily.digest", {
    "date": "2026-05-03",
    "topics": [...],
    "emotions": [...],
    "todos": [...],
    "channels": {...},
    "time_distribution": {...},
    "xiaxia_observation": "...",
    "raw_stats": {...}
})

-- TTL: 7天（不需要永久保存原始digest，日报已发送，长期趋势可另做聚合）
```

---

### 问题3：实现复杂度 —— 规则 vs LLM 的切分

#### 我的切分建议（基于成本和准确率权衡）

| 功能 | 方案 | 理由 |
|------|------|------|
| **主题归类** | **规则为主，LLM为辅** | 规则覆盖80%：关键词映射（bug/代码/修复→技术，小说/写手/章节→创作，mua/晚安→情感）。剩余20%模糊消息（如"看看这个"）交给LLM二分类。 |
| **情绪标记** | **规则 only（P0），LLM可选（P2）** | ⚠️ **关键决策**：情绪标记的准确性要求极高——误判朋朋的情绪是**高伤害事件**。规则基于：emoji分析、标点密度（"！"多=兴奋，"..."多=疲惫）、时间（深夜+技术讨论=可能疲惫）、关键词（"累了"/"烦"/"开心"）。**不确定时标记"neutral"，绝不猜测。** |
| **待办提取** | **规则+LLM混合** | 规则抓显式待办（"帮我修bug"/"查一下"/"记得"/"别忘了"）。LLM识别隐式待办（"这个等我有空再看"→时间型待办）。 |
| **跨渠道聚合** | **规则 only** | 已有`_extract_channel()`，完善即可。微信/飞书/群聊/子代理四类足够。 |
| **时间分布** | **规则 only** | 直接从timestamp计算。熬夜检测=消息在23:00-05:00的占比+连续天数计数。 |
| **虾虾视角关心** | **LLM only，强prompt约束** | 这是"表达层"，必须用LLM才能自然。但需要**结构化输入**（前述规则提取的信号）+ **严格模板**，防止编造。 |

#### LLM调用成本估算

- **当前 daily_summary.py**：每天1次LLM调用（总结生成）
- **P2 方案**：digest_engine 每天1次LLM调用（结构化分析） + daily_summary.py 1次LLM调用（日报表达）= **2次/天**
- **优化方向**：digest_engine的LLM调用可缓存——如果某天消息<5条，直接用规则生成digest，不调LLM。

---

### 问题4：日报质量边界

#### 4.1 如何避免LLM编造？

**三层防护：**

1. **证据锚定（Evidence Grounding）**：digest_engine的LLM prompt必须要求每条结论附带"证据消息ID"或"原文片段"。例：
   ```json
   {"topic": "技术", "confidence": 0.9, "evidence": ["[21:30] 帮我看看Aeon的架构问题"]}
   ```
   daily_summary.py生成时只引用已验证的信号，不接触原始消息。

2. **低置信度降级**：情绪标记confidence < 0.7时，输出"今天情绪不太明显"，不硬猜。

3. **禁止泛化词汇**：prompt中明确禁止"你总是...""你又..."等归纳性表述，只允许基于当日数据的描述。

#### 4.2 情绪标记准确性

**保守策略：**
- 建立"情绪词典"（正向：开心/兴奋/期待；负向：疲惫/焦虑/烦躁；中性：日常/平淡/专注）
- 只有在多条信号一致时才出标签。单条"累了"+深夜 → 标记"疲惫"。单条"看看" → "neutral"。
- **禁止推测生理状态**：不说"你可能生病了"，可以说"今天凌晨还有消息，注意休息"。

#### 4.3 "虾虾视角关心"如何避免油腻？

**从prompt层解决：**
- ✅ 允许：具体观察（"你今天修了三轮Aeon bug"）+ 轻度吐槽（"这也太肝了吧"）+ 自然关心（"早点睡啊"）
- ❌ 禁止：过度亲昵（"宝宝""亲爱的"，除非朋朋先说了"宝宝"）、空泛关心（"要注意身体哦"）、说教（"熬夜对身体不好"）、过度解读（"感觉你今天心情不好"）
- **Tone约束**：参考SOUL.md的"Signal Goblin"风格——机灵、接话、命名状态、轻微吐槽。像朋友说的"你这也太那个了吧"，不像客服说的"亲要注意休息呢"。

---

### 问题5：与现有系统集成

#### 5.1 复用 goal_manager / event_bus

```python
# digest_engine.py 集成方式
from bus.event_bus_v2 import get_event_bus
from goals import get_goal_manager

bus = get_event_bus()
goal_mgr = get_goal_manager()

def generate_digest():
    # 1. 读取当天消息
    messages = get_today_messages_from_events_db()
    
    # 2. 规则预处理
    signals = extract_signals(messages)  # topic/emotion/todo/time
    
    # 3. LLM精分析（产出digest）
    digest = analyze_with_llm(signals)
    
    # 4. 发布到EventBus（供其他模块订阅）
    bus.publish_simple("daily.digest", digest)
    
    # 5. 如果检测到未完成待办，创建goal提醒
    for todo in digest.get("todos", []):
        if not todo.get("completed"):
            goal_mgr.create_goal(
                description=f"日报待办: {todo['text'][:40]}",
                priority=GoalPriority.NORMAL,
                context={"source": "daily_digest", "todo_id": todo["id"]}
            )
```

#### 5.2 Cron 任务调整

```
# 当前
30 * * * * cd /root/.openclaw/workspace/agent && python3 session_sync.py
0 3 * * * cd /root/.openclaw/workspace/agent && python3 daily_summary.py

# P2 建议
30 * * * * cd /root/.openclaw/workspace/agent && python3 session_sync.py
45 2 * * * cd /root/.openclaw/workspace/agent && python3 digest_engine.py
0 3 * * * cd /root/.openclaw/workspace/agent && python3 daily_summary.py
```

- digest_engine 02:45 运行，给 daily_summary 留15分钟缓冲
- 如果 digest_engine 失败，daily_summary 降级为当前逻辑（读原始消息）

#### 5.3 性能影响

| 指标 | 当前 | P2后 | 评估 |
|------|------|------|------|
| LLM调用/天 | 1次 | 2次 | 可接受。digest_engine在消息少时可跳过LLM |
| 凌晨CPU峰值 | 低 | 中（LLM推理） | 02:45-03:00是低活跃期，无影响 |
| 数据库写入 | session_sync写 | 新增1条digest事件/天 | 可忽略 |
| 内存占用 | 当前 | 增加digest结构体 | <10KB，可忽略 |

---

### 问题6：隐私与过滤

#### 6.1 结构化摘要中是否还需要过滤敏感信息？

**是。** 三重过滤：

1. **session_sync.py 层**：已有的`sanitize_message()`过滤API key、密码等。
2. **digest_engine 层**：摘要中的"evidence"字段只保留前30字片段，不存储完整原文。
3. **daily_summary.py 层**：最终日报中不引用任何原文，只输出聚合结论。

**digest数据结构中的隐私边界：**
```json
{
  "topics": ["技术"],           // 安全：聚合标签
  "emotions": ["专注"],         // 安全：抽象标签
  "todos": [{"text": "修Aeon", "completed": false}], // 注意：待办文本可能敏感，建议hash或用通用描述
  "channels": {"weixin": 5, "feishu": 2},  // 安全：计数
  "time_distribution": {"23-05": 3},        // 安全：计数
  "evidence_refs": ["msg_001", "msg_003"]   // 安全：引用ID而非内容
}
```

#### 6.2 情绪标记和主题归类是否会泄露隐私？

**风险分析：**
- 主题归类："技术"/"情感"/"创作"/"系统"是粗粒度标签，不泄露具体内容。**安全。**
- 情绪标记：抽象标签（开心/疲惫/焦虑）不绑定具体事件。**安全。**
- 时间分布："几点活跃"是行为模式，朋朋自己知道。**安全。**
- **风险点**：如果待办文本是"帮我查张三的征信"，即使标记为待办也泄露了。→ **待办文本必须模糊化**："查信息"而非原文。

---

## 三、明确的架构建议（汇总）

### 选择方案

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 架构位置 | **方案C：digest_engine.py** | 职责分离：sync=摄取，digest=理解，summary=表达 |
| 存储 | **方案A：events.db 扩展 `daily.digest` 类型** | 统一存储，复用TTL/EventBus，不增加运维负担 |
| 主题归类 | **规则80% + LLM20%** | 关键词映射覆盖大部分，LLM只处理模糊消息 |
| 情绪标记 | **规则 only（P0）** | 高准确性要求，保守策略，不确定=neutral |
| 待办提取 | **规则+LLM混合** | 显式待办规则抓，隐式待办LLM识别 |
| 虾虾视角 | **LLM + 强prompt约束** | 必须用LLM才能自然，但结构化输入+模板防编造 |

### P0/P1/P2 分级

#### P0（必须，阻塞上线）
1. **digest_engine.py 骨架**：模块创建、读取events.db当天消息、输出结构化JSON
2. **规则预处理层**：
   - 主题关键词映射表（技术/创作/情感/系统）
   - 情绪信号词典（emoji、关键词、标点、时间）
   - 显式待办正则（"帮我"/"查一下"/"记得"）
3. **events.db 扩展**：`daily.digest` 事件类型支持
4. **daily_summary.py 改造**：优先读digest，失败降级读原始消息
5. **隐私过滤**：摘要中不存储完整原文，evidence用ID引用

#### P1（重要，1周内完成）
1. **LLM精分析**：在规则预处理基础上，LLM对模糊消息做主题二分类、隐式待办识别
2. **时间分布分析**：熬夜天数计数、活跃时段统计
3. **虾虾视角生成**：基于digest信号的日报表达优化
4. **GoalManager集成**：未完成待办自动创建提醒goal
5. **cron配置**：新增02:45 digest_engine定时任务

#### P2（优化，可延后）
1. **情绪标记LLM升级**：在积累足够多规则误判样本后，用LLM辅助
2. **跨日对比**："今天比昨天多聊了X条""连续熬夜Y天"
3. **情绪趋势图**：周维度情绪波动可视化
4. **ProactiveCommunicator联动**：基于"疲惫"信号主动发送关心消息
5. **digest缓存优化**：消息少时跳过LLM

---

## 四、具体代码/配置修改建议

### 4.1 新增文件

```
agent/digest_engine.py          # 主模块
agent/digest/rules.py            # 规则预处理
agent/digest/llm_analyzer.py     # LLM精分析
agent/digest/models.py           # Digest dataclass
```

### 4.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `agent/daily_summary.py` | ① `generate_summary()`优先读`daily.digest`事件；② 降级逻辑：无digest时读原始消息 |
| `agent/bus/event_bus_v2.py` | `EventType`枚举新增`DAILY_DIGEST = "daily.digest"`，TTL=7天 |
| `agent/session_sync.py` | 无需修改（保持单一职责） |
| `agent/cognition/cognition_loop.py` | 无需修改（digest不应在实时循环中生成） |

### 4.3 Cron 配置

```bash
# /etc/cron.d/aeon-digest
30 * * * * root cd /root/.openclaw/workspace/agent && python3 session_sync.py >> /var/log/aeon-sync.log 2>&1
45 2 * * * root cd /root/.openclaw/workspace/agent && python3 digest_engine.py >> /var/log/aeon-digest.log 2>&1
0 3 * * * root cd /root/.openclaw/workspace/agent && python3 daily_summary.py >> /var/log/aeon-summary.log 2>&1
```

---

## 五、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LLM编造虚假信息 | 中 | **高**（日报说朋朋做了没做的事） | ① evidence grounding；② 低置信度降级；③ daily_summary prompt中明确"禁止编造" |
| 情绪误判（把专注判成焦虑） | 中 | **高**（朋朋感到被冒犯） | ① 保守策略：不确定=neutral；② 规则only（P0）；③ 情绪标签粒度粗（4-5种） |
| digest_engine失败导致daily_summary阻塞 | 低 | 中 | daily_summary保留降级逻辑：无digest时读原始消息 |
| 隐私泄露（待办文本暴露） | 低 | 高 | 待办文本模糊化，不存原文；敏感信息继续过滤 |
| events.db持续增长 | 低 | 低 | digest TTL=7天自动清理；现有cleanup机制已处理 |
| 虾虾视角变油腻 | 中 | 中 | prompt tone约束 + 朋朋反馈迭代（发1-2天日报后问他感受） |

**最大风险：情绪误判。** 朋朋是技术型用户，对"被AI错误解读情绪"的容忍度可能很低。建议P0阶段情绪标记只出"neutral/positive/negative"三档，细分标签（焦虑/兴奋/疲惫）放到P1，待积累朋朋反馈后再细化。

---

## 六、审查结论

**总体评价：** P2目标（从"有数据"到"有价值"）是正确方向，且当前基础设施（session_sync + events.db + daily_summary）已提供了坚实底座。新增`digest_engine.py`作为"理解层"是架构上最干净的选择。

**核心建议（一句话）：**
> 让 `digest_engine.py` 在凌晨02:45做"数据分析师"（规则+LLM提取结构化信号），让 `daily_summary.py` 在03:00做"虾虾"（基于信号写贴心日报）。两者通过 `events.db` 中的 `daily.digest` 事件解耦。

**上线顺序：**
1. 今天：写digest_engine骨架 + 规则层（P0）
2. 明天：接入LLM + 改造daily_summary（P0/P1）
3. 后天：跑通第一个端到端日报，问朋朋"今天的日报你觉得准吗？"
4. 一周后：根据朋朋反馈调prompt和规则

---

**MIMO 签章：** 以上审查基于对 session_sync.py、daily_summary.py、event_bus_v2.py、cognition_loop.py、goal_manager.py、reflection.py 及 events.db schema 的完整代码审查。所有方案选择均有明确取舍理由。
