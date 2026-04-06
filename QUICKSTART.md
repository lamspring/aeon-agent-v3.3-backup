# Aeon Agent 快速参考

## 安装与启用

```bash
cd /root/.openclaw/workspace/agent

# 安装并启用所有服务
sudo ./install_service.sh

# 验证 enable 状态
systemctl list-unit-files | grep aeon
```

## 日常管理

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

# 健康检查
./health_check.sh
```

## 检查清单 (Deploy 必做)

- [ ] `sudo systemctl enable aeon-agent` 成功
- [ ] `systemctl list-unit-files | grep aeon` 显示 enabled
- [ ] 重启服务器后服务自动启动
- [ ] `./health_check.sh` 显示全绿

## 故障排查

```bash
# 查看详细日志
sudo journalctl -u aeon-agent --no-pager -n 100

# 手动运行查看错误
sudo python3 /root/.openclaw/workspace/agent/launcher.py --no-recover

# 数据库检查
sqlite3 /root/.openclaw/workspace/agent/db/tasks.db "SELECT * FROM tasks;"

# 重新安装服务
sudo ./uninstall_service.sh
sudo ./install_service.sh
```

## 关键配置说明

```ini
[Unit]
After=network-online.target    # 网络就绪后启动
Wants=network-online.target

[Service]
Restart=always                 # 崩溃自动重启
RestartSec=5                   # 5秒后重启

[Install]
WantedBy=multi-user.target     # 多用户模式启动
```

## 文件位置

| 文件 | 路径 |
|------|------|
| 主服务 | `/etc/systemd/system/aeon-agent.service` |
| 定时器 | `/etc/systemd/system/aeon-memory.timer` |
| 数据库 | `/root/.openclaw/workspace/agent/db/` |
| 日志 | `/root/.openclaw/workspace/agent/logs/` |
| 状态 | `/root/.openclaw/workspace/agent/state/` |