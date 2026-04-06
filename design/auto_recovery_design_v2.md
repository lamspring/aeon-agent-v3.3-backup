# Aeon Agent 自动恢复系统设计方案 v2
**基于朋朋 systemd 最佳实践**

---

## 1. 核心原则

### 1.1 Enable ≠ Start
```bash
# ❌ 错误：只 start 不 enable
sudo systemctl start aeon-agent

# ✅ 正确：enable 开机自启，start 立即启动
sudo systemctl enable aeon-agent
sudo systemctl start aeon-agent
```

### 1.2 网络优先
```ini
[Unit]
After=network-online.target
Wants=network-online.target
```

### 1.3 自动重启
```ini
[Service]
Restart=always
RestartSec=5
```

---

## 2. 服务架构

### 2.1 服务拆分

| 服务 | 职责 | 启用方式 |
|------|------|----------|
| **aeon-agent.service** | 主 Agent | enable + start |
| **aeon-memory.timer** | 记忆整合定时器 | enable |
| **aeon-watchdog.service** | 健康检查 | enable + start |

### 2.2 启动顺序

```
Server Boot
    │
    ▼
network-online.target
    │
    ▼
aeon-agent.service (主服务)
    │
    ├── event-bus (恢复未处理事件)
    │
    ├── task-system (恢复 PENDING/RUNNING 任务)
    │
    ├── memory-index (加载记忆索引)
    │
    ├── cognition-loop (启动认知循环)
    │
    └── workers (启动执行器)
    │
    ▼
aeon-memory.timer (定时整合记忆)
    │
    ▼
aeon-watchdog.service (健康检查)
```

---

## 3. 详细配置

### 3.1 主服务: aeon-agent.service

```ini
[Unit]
Description=Aeon Agent v3.0 - AI Operating System
Documentation=https://github.com/openclaw/aeon
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/.openclaw/workspace/agent
Environment=PYTHONPATH=/root/.openclaw/workspace/agent
Environment=AEON_HOME=/root/.openclaw/workspace/agent
Environment=AEON_LOG_LEVEL=INFO

# 启动命令
ExecStart=/usr/bin/python3 /root/.openclaw/workspace/agent/launcher.py --daemon

# 停止命令
ExecStop=/bin/kill -SIGTERM $MAINPID
ExecStopPost=/usr/bin/python3 /root/.openclaw/workspace/agent/launcher.py --cleanup

# 重启策略
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

# 优雅关闭超时
TimeoutStopSec=30
KillMode=process
KillSignal=SIGTERM

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=aeon-agent

[Install]
WantedBy=multi-user.target
```

### 3.2 定时器: aeon-memory.timer

```ini
[Unit]
Description=Aeon Agent Memory Consolidation Timer
Requires=aeon-agent.service
After=aeon-agent.service

[Timer]
# 每天凌晨3点执行记忆整合
OnCalendar=03:00
# 启动后5分钟执行一次
OnBootSec=5min
# 每6小时执行一次
OnUnitActiveSec=6h

[Install]
WantedBy=timers.target
```

### 3.3 健康检查: aeon-watchdog.service

```ini
[Unit]
Description=Aeon Agent Health Check
After=aeon-agent.service
Requires=aeon-agent.service

[Service]
Type=simple
ExecStart=/root/.openclaw/workspace/agent/health_check.sh --watch
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

---

## 4. Boot Check 流程

### 4.1 启动前检查

```python
def boot_check():
    """系统启动检查"""
    checks = {
        'directories': check_directories(),
        'databases': check_databases(),
        'state_file': check_state_file(),
        'permissions': check_permissions(),
    }
    
    if not all(checks.values()):
        # 自动修复
        auto_repair(checks)
    
    return checks
```

### 4.2 检查项

| 检查项 | 操作 | 失败处理 |
|--------|------|----------|
| logs/ | 存在? 可写? | 创建目录 |
| db/ | 存在? SQLite 可读? | 初始化数据库 |
| state/ | 存在? | 创建目录 |
| events.db | 表结构正确? | 重建表 |
| tasks.db | 表结构正确? | 重建表 |
| memory.db | 表结构正确? | 重建表 |

### 4.3 恢复流程

```
Boot Check
    │
    ├── 检查目录 ──→ 缺失则创建
    │
    ├── 检查数据库 ──→ 损坏则重建 + 备份旧文件
    │
    ├── 检查状态文件 ──→ 解析上次状态
    │
    └── 返回检查结果
```

---

## 5. 数据持久化

### 5.1 必须持久化的数据

| 数据库 | 内容 | 重启恢复 |
|--------|------|----------|
| events.db | 未处理事件 | ✅ 重新发布 |
| tasks.db | PENDING/RUNNING 任务 | ✅ 恢复执行 |
| memory.db | 记忆向量 | ✅ 加载缓存 |
| state.json | 系统状态 | ✅ 读取判断 |

### 5.2 SQLite 备份策略

```bash
# 自动备份（如果检测到损坏）
mv events.db events.db.bak.$(date +%Y%m%d_%H%M%S)

# 重建空数据库
sqlite3 events.db < schema.sql
```

---

## 6. 使用指南

### 6.1 安装服务

```bash
cd /root/.openclaw/workspace/agent
sudo ./install_service.sh
```

**install_service.sh 内容**:
```bash
#!/bin/bash
# 安装并启用所有服务

# 主服务
sudo cp systemd/aeon-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aeon-agent
sudo systemctl start aeon-agent

# 定时器
sudo cp systemd/aeon-memory.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aeon-memory.timer

# 验证
echo "检查服务状态:"
systemctl list-unit-files | grep aeon

echo ""
echo "检查定时器:"
systemctl list-timers | grep aeon
```

### 6.2 验证 Enable 状态

```bash
# 检查所有 aeon 服务
systemctl list-unit-files | grep aeon

# 预期输出:
# aeon-agent.service      enabled
# aeon-memory.timer       enabled
# aeon-watchdog.service   enabled
```

### 6.3 管理服务

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

### 6.4 模拟重启测试

```bash
# 1. 创建一些任务
cd /root/.openclaw/workspace/agent
python3 -c "
from launcher import AeonLauncher
launcher = AeonLauncher()
components = launcher.start(recover=False)
queue = components['queue']
from tasks.task_system import Task
queue.add_task(Task(action='create_file', params={'path': '/tmp/test_recovery.txt', 'content': 'test'}))
"

# 2. 检查任务存在
sqlite3 db/tasks.db "SELECT task_id, status FROM tasks;"

# 3. 停止服务
sudo systemctl stop aeon-agent

# 4. 启动服务（模拟重启）
sudo systemctl start aeon-agent

# 5. 检查任务是否恢复
sudo journalctl -u aeon-agent | grep "recover"
```

---

## 7. 故障处理

### 7.1 启动失败

```bash
# 检查日志
sudo journalctl -u aeon-agent --no-pager -n 50

# 检查状态
sudo systemctl status aeon-agent

# 手动运行查看错误
sudo python3 /root/.openclaw/workspace/agent/launcher.py --no-recover
```

### 7.2 数据损坏

```bash
# 备份损坏的数据库
cd /root/.openclaw/workspace/agent/db
cp events.db events.db.corrupted.$(date +%Y%m%d)
cp tasks.db tasks.db.corrupted.$(date +%Y%m%d)

# 删除损坏文件（系统会自动重建）
rm -f events.db tasks.db memory.db

# 重启服务
sudo systemctl restart aeon-agent
```

### 7.3 网络未就绪

```bash
# 检查网络状态
systemctl status network-online.target

# 如果网络慢，增加启动延迟
# 在 /etc/systemd/system/aeon-agent.service 中添加:
# ExecStartPre=/bin/sleep 10
```

---

## 8. 监控

### 8.1 健康检查脚本

```bash
#!/bin/bash
# health_check.sh

# 检查服务运行
if ! systemctl is-active --quiet aeon-agent; then
    echo "❌ aeon-agent 未运行"
    exit 1
fi

# 检查 enable 状态
if ! systemctl is-enabled --quiet aeon-agent 2>/dev/null; then
    echo "⚠️  aeon-agent 未启用开机自启"
fi

# 检查数据库
for db in events.db tasks.db memory.db; do
    if [ ! -f "db/$db" ]; then
        echo "❌ 数据库缺失: $db"
    fi
done

echo "✅ 系统健康"
```

### 8.2 定时健康检查

```bash
# 添加到 crontab
echo "*/5 * * * * /root/.openclaw/workspace/agent/health_check.sh || systemctl restart aeon-agent" | sudo crontab -
```

---

## 9. 检查清单

部署后必须验证:

- [ ] `sudo systemctl enable aeon-agent` 成功
- [ ] `systemctl list-unit-files | grep aeon` 显示 enabled
- [ ] 重启服务器后服务自动启动
- [ ] 任务在重启后自动恢复
- [ ] 事件在重启后自动恢复
- [ ] 网络未就绪时服务等待而非崩溃
- [ ] 服务崩溃后 5 秒内自动重启
- [ ] 日志正常写入 journal

---

## 10. 总结

### 关键命令

```bash
# 安装
sudo ./install_service.sh

# 验证
systemctl list-unit-files | grep aeon
systemctl list-timers | grep aeon

# 管理
sudo systemctl start|stop|restart|status aeon-agent
sudo journalctl -u aeon-agent -f

# 故障排查
sudo systemctl status aeon-agent
sudo journalctl -u aeon-agent --no-pager -n 100
```

### 核心配置

```ini
[Unit]
After=network-online.target
Wants=network-online.target

[Service]
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Deploy Checklist**:
1. ✅ 所有服务 `enabled`
2. ✅ 网络就绪后启动
3. ✅ 崩溃自动重启
4. ✅ 数据持久化
5. ✅ Boot Check 正常
6. ✅ 重启测试通过