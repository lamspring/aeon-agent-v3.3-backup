# OpenClaw 配置文件清单

## 系统级配置

### 1. 主配置文件
**路径**: `~/.openclaw/openclaw.json`
**作用**: OpenClaw 核心配置，包含：
- API Keys (Kimi, etc.)
- 模型配置 (k2p5)
- 心跳间隔 (`agents.defaults.heartbeat.every`)
- 工具权限 (`tools.profile`)
- 通道配置 (channels)
- Gateway 端口和认证
- 插件白名单

**状态**: ✅ 已更新为 15m

---

## 工作区配置 (~/openclaw/workspace/)

### 2. AGENTS.md
**路径**: `/root/.openclaw/workspace/AGENTS.md`
**作用**: 
- 每次会话启动必读清单
- 工作流程规范
- 记忆文件读取顺序
- 工具调用三重保险规则

**状态**: ✅ 已更新门控检查流程

### 3. HEARTBEAT.md
**路径**: `/root/.openclaw/workspace/HEARTBEAT.md`
**作用**:
- 心跳触发时执行的任务
- 门控检查逻辑
- v11.4 消息检查
- 内在动机系统（开发中）

**状态**: ✅ 已绑定门控检查

### 4. SOUL.md
**路径**: `/root/.openclaw/workspace/SOUL.md`
**作用**:
- 我的性格定义
- 工作模式（专注/日常）
- 人格锚点（品味、厌恶、立场）
- 主动禁令清单

**状态**: ✅ 稳定

### 5. USER.md
**路径**: `/root/.openclaw/workspace/USER.md`
**作用**:
- 朋朋的信息
- 用户偏好和禁忌
- 家庭信息（九九🐶）
- 认知库（我们之间的特殊约定）

**状态**: ✅ 稳定

### 6. MEMORY.md
**路径**: `/root/.openclaw/workspace/MEMORY.md`
**作用**:
- 长期记忆（用户偏好、技能库、决策记录）
- 能力里程碑
- 自我进化指南

**状态**: ✅ 定期更新

### 7. IDENTITY.md
**路径**: `/root/.openclaw/workspace/IDENTITY.md`
**作用**:
- 我的身份定义（名字、物种、vibe）
- 核心特质（守护与记忆）
- Few-Shot 示例

**状态**: ✅ 稳定

### 8. TOOLS.md
**路径**: `/root/.openclaw/workspace/TOOLS.md`
**作用**:
- 本地环境专属信息
- 摄像头、SSH、TTS 偏好等

**状态**: 📝 待补充

---

## 动态状态文件 (memory/)

### 9. 状态文件
**路径**: `/root/.openclaw/workspace/memory/state.json`
**作用**:
- 当前状态 (IDLE/BUSY)
- 当前任务
- 心跳队列

**状态**: ✅ 动态更新

### 10. 门控状态
**路径**: `/root/.openclaw/workspace/memory/gate_status.json`
**作用**:
- 外部条件控制开关
- 授权人、有效期、范围
- 自主任务的"红绿灯"

**状态**: 🚫 当前 CLOSED

### 11. 心跳队列
**路径**: `/root/.openclaw/workspace/memory/heartbeat_queue.json`
**作用**:
- BUSY 状态时暂存的心跳任务
- 稍后处理队列

**状态**: 📝 动态

### 12. 每日记忆
**路径**: `/root/.openclaw/workspace/memory/YYYY-MM-DD.md`
**作用**:
- 当天发生的详细记录
- 对话内容、决策过程

**状态**: 📝 每日创建

### 13. 任务进度
**路径**: `/root/.openclaw/workspace/memory/current_task.md`
**作用**:
- 当前任务的详细进度
- 断点续做依据

**状态**: 📝 开发中（内在动机系统）

---

## 设计文档 (design/)

### 14. 内在动机系统设计
**路径**: `/root/.openclaw/workspace/design/intrinsic_motivation_system_v1.md`
**作用**:
- 自主行为系统架构
- 四重内在奖励机制
- System 3 元认知层设计
- 5个新文件的设计方案

**状态**: 📝 待实施

---

## 工具脚本 (tools/)

### 15. 门控检查脚本
**路径**: `/root/.openclaw/workspace/tools/gate_check.py`
**作用**:
- 读取 gate_status.json
- 检查有效期和权限
- 返回码: 0=允许, 1=拒绝

**状态**: ✅ 可执行

---

## 研究文档 (research/)

### 16. 自主行为研究
**路径**: `/root/.openclaw/workspace/research/autonomous_behavior_notes.md`
**作用**:
- AI 自主行为相关论文总结
- 内在动机机制研究
- System 3 架构参考

**状态**: ✅ 已归档

---

## 配置文件层级图

```
~/.openclaw/
├── openclaw.json          # 系统核心配置 ⭐️
├── config.json            # 旧配置（如存在）
└── workspace/
    ├── AGENTS.md          # 启动必读 ⭐️
    ├── HEARTBEAT.md       # 心跳任务 ⭐️
    ├── SOUL.md            # 性格定义 ⭐️
    ├── USER.md            # 用户信息 ⭐️
    ├── MEMORY.md          # 长期记忆
    ├── IDENTITY.md        # 身份定义
    ├── TOOLS.md           # 环境信息
    ├── memory/
    │   ├── state.json         # 当前状态
    │   ├── gate_status.json   # 门控状态 ⭐️
    │   ├── heartbeat_queue.json
    │   └── YYYY-MM-DD.md      # 每日日志
    ├── design/
    │   └── intrinsic_motivation_system_v1.md
    ├── tools/
    │   └── gate_check.py      # 门控脚本 ⭐️
    └── research/
        └── autonomous_behavior_notes.md
```

**⭐️ 标记**: 新实施或修改的文件

---

## 修改记录 (今日)

1. **openclaw.json** - 心跳间隔 60m → 15m
2. **HEARTBEAT.md** - 添加门控检查步骤
3. **gate_status.json** - 新建门控状态文件 (当前 CLOSED)
4. **gate_check.py** - 新建门控检查脚本
5. **design/intrinsic_motivation_system_v1.md** - 内在动机系统设计
6. **research/autonomous_behavior_notes.md** - 自主行为研究笔记
