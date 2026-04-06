# Aeon Agent 自动恢复系统设计方案

## 1. 需求分析

### 1.1 问题
- 服务器重启后，Aeon Agent 需要手动启动
- 未处理的事件和任务会丢失或滞留
- 系统状态无法自动恢复

### 1.2 目标
- 服务器重启后自动启动 Aeon Agent
- 自动恢复未处理的事件和任务
- 保持系统状态连续性
- 提供健康检查和监控能力

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Linux System (systemd)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              aeon-agent.service (开机自启)              │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │           Aeon Launcher (启动器)                 │  │  │
│  │  │                                                 │  │  │
│  │  │  1. 检查状态文件 ←── state/system.state         │  │  │
│  │  │  2. 恢复未处理事件 ←── events.db                │  │  │
│  │  │  3. 恢复未完成任务 ←── tasks.db                 │  │  │
│  │  │  4. 初始化所有组件                              │  │  │
│  │  │  5. 保存状态 ──→ state/system.state             │  │  │
│  │  │  6. 发布启动事件 ──→ Event Bus                  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────┼────────────────────────────┐    │
│  │                        ▼                            │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────────┐ │    │
│  │  │Event Bus│  │  Task   │  │Cognition│  │ Memory │ │    │
│  │  │         │  │ System  │  │  Loop   │  │ Index  │ │    │
│  │  └─────────┘  └─────────┘  └─────────┘  └────────┘ │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 职责 |
|------|------|
| **systemd service** | 系统服务管理，开机自启动 |
| **Aeon Launcher** | 启动器，处理初始化和恢复 |
| **State File** | 记录系统状态，判断是否是重启 |
| **Event Recovery** | 恢复未处理的事件 |
| **Task Recovery** | 恢复未完成的任务 |
| **Graceful Shutdown** | 优雅关闭，保存状态 |

---

## 3. 详细设计

### 3.1 systemd 服务配置

**文件**: `/etc/systemd/system/aeon-agent.service`

```ini
[Unit]
Description=Aeon Agent v3.0
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/.openclaw/workspace/agent
ExecStart=/usr/bin/python3 launcher.py --daemon
Restart=always
RestartSec=10
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

**关键配置**:
- `Restart=always`: 崩溃后自动重启
- `RestartSec=10`: 10秒后重启
- `TimeoutStopSec=30`: 30秒优雅关闭超时

### 3.2 状态文件设计

**文件**: `state/system.state`

```json
{
  "last_run": "2026-04-06T13:30:00+08:00",
  "pid": 12345,
  "status": "running",
  "version": "3.0"
}
```

**用途**:
- 判断是否是系统重启
- 记录上次运行时间
- 版本兼容性检查

### 3.3 启动流程

```
┌─────────────┐
│   Start     │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ 1. 初始化目录        │
│    logs/, db/, state/│
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ 2. 检查状态文件      │
│    state/system.state│
└──────┬──────────────┘
       │
       ├────── 文件存在? ────┐
       │                     │
       │ YES                 │ NO
       ▼                     ▼
┌──────────────────┐  ┌──────────────┐
│ 读取上次状态      │  │ 首次启动      │
│ 标记为重启恢复    │  │ 标记为新启动  │
└──────┬───────────┘  └──────┬───────┘
       │                      │
       └──────────┬───────────┘
                  │
                  ▼
┌───────────────────────────────┐
│ 3. 初始化核心组件              │
│    - Logger                    │
│    - Event Bus                 │
│    - Memory System             │
│    - Task System               │
│    - Cognition Loop            │
└──────┬────────────────────────┘
       │
       ▼
┌───────────────────────────────┐
│ 4. 恢复未处理数据 (如果是重启) │
│    - 恢复未处理事件            │
│    - 恢复 PENDING 任务         │
│    - 重试 RUNNING 任务         │
└──────┬────────────────────────┘
       │
       ▼
┌───────────────────────────────┐
│ 5. 启动所有服务                │
│    - Task Watchdog             │
│    - Worker                    │
│    - Cognition Loop            │
└──────┬────────────────────────┘
       │
       ▼
┌───────────────────────────────┐
│ 6. 保存状态                    │
│    - 更新 system.state         │
└──────┬────────────────────────┘
       │
       ▼
┌───────────────────────────────┐
│ 7. 发布系统启动事件            │
│    - SYSTEM_STARTED            │
│    - 包含恢复统计信息          │
└──────┬────────────────────────┘
       │
       ▼
┌─────────────┐
│   Running   │
└─────────────┘
```

### 3.4 恢复机制

#### 3.4.1 事件恢复

**触发条件**: 系统重启后

**恢复逻辑**:
```python
def recover_unprocessed_events():
    # 从数据库加载未处理事件
    events = event_persistence.get_unprocessed()
    
    # 检查 TTL，丢弃过期事件
    valid_events = [e for e in events if not e.is_expired()]
    
    # 重新发布到 Event Bus
    for event in valid_events:
        event_bus.republish(event)
    
    return len(valid_events)
```

#### 3.4.2 任务恢复

**触发条件**: 系统重启后

**恢复逻辑**:
```python
def recover_pending_tasks():
    # PENDING 任务：直接恢复
    pending = task_persistence.get_pending_tasks()
    
    # RUNNING 任务：标记为 PENDING，等待重试
    running = task_persistence.get_running_tasks()
    for task in running:
        task.status = 'pending'
        task.metadata['retry_reason'] = 'system_restart'
        task_persistence.store(task)
    
    return len(pending) + len(running)
```

### 3.5 优雅关闭

**信号处理**:
- `SIGTERM`: 优雅关闭
- `SIGINT` (Ctrl+C): 优雅关闭

**关闭流程**:
```
┌─────────────┐
│ 收到 SIGTERM │
└──────┬──────┘
       │
       ▼
┌───────────────────┐
│ 1. 停止 Cognition  │
│    - 停止 tick    │
│    - 完成当前循环  │
└──────┬────────────┘
       │
       ▼
┌───────────────────┐
│ 2. 刷新 Memory    │
│    - 强制写入缓冲  │
└──────┬────────────┘
       │
       ▼
┌───────────────────┐
│ 3. 停止 Task      │
│    - 停止 Watchdog│
│    - 停止 Workers │
│    - 等待任务完成  │
└──────┬────────────┘
       │
       ▼
┌───────────────────┐
│ 4. 保存状态       │
│    - 更新 state   │
└──────┬────────────┘
       │
       ▼
┌─────────────┐
│   Exited    │
└─────────────┘
```

---

## 4. 文件清单

### 4.1 新增文件

| 文件 | 说明 |
|------|------|
| `launcher.py` | 系统启动器，处理初始化和恢复 |
| `systemd/aeon-agent.service` | systemd 服务配置 |
| `install_service.sh` | 安装脚本 |
| `uninstall_service.sh` | 卸载脚本 |
| `start.sh` | 快速启动脚本 |
| `stop.sh` | 停止脚本 |
| `health_check.sh` | 健康检查脚本 |

### 4.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `tasks/task_system.py` | Worker 添加 stop() 方法 |

---

## 5. 使用方式

### 5.1 安装系统服务（推荐）

```bash
cd /root/.openclaw/workspace/agent
sudo ./install_service.sh
```

**效果**:
- 安装 systemd 服务
- 启用开机自启
- 立即启动服务

### 5.2 手动管理

```bash
# 启动
sudo systemctl start aeon-agent

# 停止
sudo systemctl stop aeon-agent

# 重启
sudo systemctl restart aeon-agent

# 查看状态
sudo systemctl status aeon-agent

# 查看日志
sudo journalctl -u aeon-agent -f

# 禁用开机自启
sudo systemctl disable aeon-agent
```

### 5.3 快速启动（不安装服务）

```bash
cd /root/.openclaw/workspace/agent
./start.sh        # 启动
./stop.sh         # 停止
./health_check.sh # 健康检查
```

---

## 6. 监控与维护

### 6.1 健康检查

```bash
./health_check.sh
```

**输出**:
- 服务运行状态
- 开机自启状态
- 数据库文件状态
- 日志文件状态
- 最近日志

### 6.2 日志查看

```bash
# 系统日志
sudo journalctl -u aeon-agent -f

# 应用日志
tail -f logs/agent.log
tail -f logs/agent.jsonl
```

### 6.3 状态文件

```bash
cat state/system.state
```

---

## 7. 异常处理

### 7.1 启动失败

**自动重试**:
- systemd 配置 `Restart=always`
- 10秒后自动重试
- 最多连续重试 3 次

### 7.2 关闭超时

**强制终止**:
- 30秒优雅关闭超时
- 超时后发送 SIGKILL

### 7.3 数据损坏

**恢复策略**:
- 数据库使用 SQLite，自动恢复
- 损坏时创建新数据库
- 旧数据库备份为 `.bak`

---

## 8. 安全考虑

### 8.1 权限
- 服务以 root 运行（访问工作目录）
- 数据文件权限 644
- 日志文件权限 644

### 8.2 资源限制
- 内存使用：无限制（依赖系统 OOM）
- CPU 使用：无限制
- 磁盘使用：日志轮转

---

## 9. 测试计划

### 9.1 功能测试
- [ ] 安装服务
- [ ] 启动服务
- [ ] 停止服务
- [ ] 重启服务
- [ ] 卸载服务

### 9.2 恢复测试
- [ ] 创建任务后重启
- [ ] 发布事件后重启
- [ ] 验证任务恢复
- [ ] 验证事件恢复

### 9.3 稳定性测试
- [ ] 连续运行 24 小时
- [ ] 模拟崩溃重启
- [ ] 日志轮转测试

---

## 10. 总结

本方案实现了完整的自动恢复系统：

1. **systemd 集成**: 开机自启，自动重启
2. **状态管理**: 记录运行状态，判断重启
3. **数据恢复**: 恢复事件和任务
4. **优雅关闭**: 信号处理，资源清理
5. **监控工具**: 健康检查，日志查看

**预期效果**:
- 服务器重启后自动启动
- 无数据丢失
- 系统状态连续
- 易于监控维护