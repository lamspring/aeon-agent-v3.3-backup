# Aeon Agent v3.3 完整恢复操作手册

**版本**: v3.3  
**备份时间**: 2026-04-06  
**适用场景**: 新机器部署 / 灾难恢复 / 环境迁移

---

## 📋 恢复前准备

### 1. 系统要求

| 项目 | 要求 |
|------|------|
| OS | Linux (Ubuntu 22.04+ / Debian 12+ / CentOS 8+) |
| Python | 3.10+ |
| 内存 | 最低 512MB，推荐 1GB+ |
| 磁盘 | 最低 2GB 可用空间 |
| Git | 已安装 |
| Systemd | 已安装并运行 |

### 2. 安装依赖

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y  # Debian/Ubuntu
# 或
sudo yum update -y  # CentOS/RHEL

# 安装基础依赖
sudo apt install -y python3 python3-pip python3-venv git curl  # Debian/Ubuntu
# 或
sudo yum install -y python3 python3-pip git curl  # CentOS/RHEL
```

---

## 🚀 完整恢复步骤

### 步骤 1: 克隆备份仓库

```bash
# 创建工作目录
mkdir -p /root/.openclaw/workspace
cd /root/.openclaw/workspace

# 克隆备份仓库（需要你的GitHub Token或有权限的SSH密钥）
git clone https://github.com/lamspring/aeon-agent-v3.3-backup.git agent

# 进入目录
cd agent
```

### 步骤 2: 安装 Python 依赖

```bash
# 安装核心依赖
pip3 install -r requirements.txt

# 如果使用虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 步骤 3: 恢复 OpenClaw Gateway 配置（可选）

```bash
# 创建 OpenClaw 配置目录
mkdir -p ~/.openclaw

# 复制配置文件
cp -r openclaw-config/* ~/.openclaw/

# 设置权限
chmod 600 ~/.openclaw/config*.json 2>/dev/null || true
```

### 步骤 4: 注册系统服务

```bash
# 复制 systemd 服务文件
sudo cp system-services/aeon-agent.service /etc/systemd/system/
sudo cp system-services/aeon-memory.service /etc/systemd/system/ 2>/dev/null || true
sudo cp system-services/aeon-memory.timer /etc/systemd/system/ 2>/dev/null || true
sudo cp system-services/xiaxia-boot-check.service /etc/systemd/system/ 2>/dev/null || true

# 重载 systemd
sudo systemctl daemon-reload

# 设置开机自启
sudo systemctl enable aeon-agent.service
sudo systemctl enable aeon-memory.timer 2>/dev/null || true
```

### 步骤 5: 创建必要的目录结构

```bash
# Agent 会自动创建，但我们可以提前确保权限
sudo mkdir -p /root/.openclaw/workspace/agent/{logs,db,temp,state}
sudo mkdir -p /root/.openclaw/workspace/memory

# 如果需要，修正权限（如果使用非root用户运行）
# sudo chown -R youruser:youruser /root/.openclaw/
```

### 步骤 6: 安装 OpenClaw Gateway（如果未安装）

```bash
# 检查是否已安装
which openclaw

# 如果未安装，需要安装
# 参考: https://docs.openclaw.ai/installation
# 或执行你的安装脚本
```

### 步骤 7: 启动服务

```bash
# 启动 Agent
sudo systemctl start aeon-agent

# 检查状态
sudo systemctl status aeon-agent

# 查看日志
sudo journalctl -u aeon-agent -f
# 或
tail -f /root/.openclaw/workspace/agent/logs/agent.log
```

### 步骤 8: 验证恢复

```bash
# 运行健康检查
cd /root/.openclaw/workspace/agent
python3 -c "
import sys
sys.path.insert(0, '.')
from bus.event_bus_v2 import get_event_bus
from goals import get_goal_manager

bus = get_event_bus()
gm = get_goal_manager()

print('✅ EventBus:', '队列=', bus.get_queue_size())
print('✅ GoalManager:', '活跃Goal=', gm.get_active_goal().goal_id[:8] if gm.get_active_goal() else 'None')
print('✅ 恢复成功!')
"
```

---

## 🔧 常见问题

### Q1: 启动失败，提示模块找不到

```bash
# 确保在正确的目录
export PYTHONPATH=/root/.openclaw/workspace/agent:$PYTHONPATH

# 或者安装为可编辑包
cd /root/.openclaw/workspace/agent
pip install -e .
```

### Q2: 数据库损坏或版本不兼容

```bash
# 备份当前数据库
cd /root/.openclaw/workspace/agent/db
cp events.db events.db.backup.$(date +%Y%m%d)
cp goals.db goals.db.backup.$(date +%Y%m%d)

# 如果需要重置（会丢失数据！）
# rm *.db
# 然后重启服务，系统会创建新数据库
```

### Q3: 服务启动后立即退出

```bash
# 检查日志
sudo journalctl -u aeon-agent --no-pager -n 50

# 检查权限
ls -la /root/.openclaw/workspace/agent/

# 手动运行查看错误
cd /root/.openclaw/workspace/agent
python3 launcher.py --dry-run 2>&1 | head -20
```

### Q4: 端口冲突

```bash
# 检查端口占用
sudo netstat -tlnp | grep 8080  # 或其他端口

# 修改配置中的端口
vim /root/.openclaw/workspace/agent/config/aeon.json
```

### Q5: 定时任务未生效

```bash
# 检查 cron 配置
sudo ls -la /etc/cron.d/aeon*

# 重新加载 cron
sudo systemctl restart cron

# 检查 cron 日志
sudo grep CRON /var/log/syslog | tail -10
```

---

## 📊 验证清单

恢复完成后，确认以下项目：

- [ ] `sudo systemctl status aeon-agent` 显示 active (running)
- [ ] `/root/.openclaw/workspace/agent/logs/agent.log` 有最新日志
- [ ] `curl http://localhost:8080/health` 返回健康状态（如果启用了健康检查）
- [ ] 数据库文件存在且有大小（db/*.db）
- [ ] 定时任务已启用（`systemctl list-timers | grep aeon`）
- [ ] 内存使用正常（`ps -o pid,cmd,pmem -p $(pgrep -f launcher.py)`）

---

## 🔄 增量备份建议

恢复后，建议设置定期备份：

```bash
# 添加到 crontab
sudo crontab -e

# 添加行（每天凌晨3点备份到GitHub）
0 3 * * * cd /root/.openclaw/workspace/agent && git add . && git commit -m "Auto backup $(date +\%Y\%m\%d)" && git push origin main
```

---

## 🆘 紧急恢复

如果完全无法启动：

```bash
# 1. 保留数据
cp -r /root/.openclaw/workspace/agent/db /tmp/agent-db-backup

# 2. 重新克隆
cd /root/.openclaw/workspace
rm -rf agent
git clone https://github.com/lamspring/aeon-agent-v3.3-backup.git agent

# 3. 恢复数据
cp /tmp/agent-db-backup/*.db /root/.openclaw/workspace/agent/db/

# 4. 重新启动
sudo systemctl restart aeon-agent
```

---

## 📞 联系支持

如果遇到无法解决的问题：
- 检查 GitHub Issues（如果有公开仓库）
- 查看日志：`/root/.openclaw/workspace/agent/logs/`
- 运行诊断脚本（如果存在）：`python3 health_check.sh`

---

**备份创建时间**: 2026-04-06  
**最后更新**: 2026-04-06  
**版本**: v3.3
