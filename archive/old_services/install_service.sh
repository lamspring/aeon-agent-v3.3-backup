#!/bin/bash
#
# Aeon Agent 系统服务安装脚本
# 设置开机自启动
#

set -e

AEON_DIR="/root/.openclaw/workspace/agent"
SYSTEMD_DIR="/etc/systemd/system"

echo "==============================================="
echo "Aeon Agent v3.0 - 系统服务安装"
echo "==============================================="
echo ""

# 检查root权限
if [ "$EUID" -ne 0 ]; then 
    echo "❌ 请使用 sudo 运行此脚本"
    exit 1
fi

# 检查服务文件
if [ ! -f "$AEON_DIR/systemd/aeon-agent.service" ]; then
    echo "❌ 服务文件不存在: $AEON_DIR/systemd/aeon-agent.service"
    exit 1
fi

echo "✓ 检查通过"
echo ""

# 复制服务文件
echo "→ 安装 systemd 服务..."
cp "$AEON_DIR/systemd/"*.service "$SYSTEMD_DIR/"
cp "$AEON_DIR/systemd/"*.timer "$SYSTEMD_DIR/" 2>/dev/null || true

# 重新加载 systemd
echo "→ 重新加载 systemd..."
systemctl daemon-reload

# 启用主服务（开机自启）
echo "→ 启用 aeon-agent 开机自启..."
systemctl enable aeon-agent

# 启用定时器
echo "→ 启用 aeon-memory 定时器..."
systemctl enable aeon-memory.timer

echo ""
echo "==============================================="
echo "✅ 安装完成！"
echo "==============================================="
echo ""
echo "服务状态:"
systemctl list-unit-files | grep aeon | grep -v "^#"

echo ""
echo "启动命令:"
echo "  sudo systemctl start aeon-agent      # 启动主服务"
echo "  sudo systemctl start aeon-memory.timer # 启动定时器"

echo ""
echo "是否现在启动服务? (y/n)"
read -r response
if [ "$response" = "y" ] || [ "$response" = "Y" ]; then
    echo ""
    echo "→ 启动 aeon-agent..."
    systemctl start aeon-agent
    sleep 2
    
    echo "→ 启动 aeon-memory 定时器..."
    systemctl start aeon-memory.timer
    
    echo ""
    echo "→ 当前状态:"
    systemctl status aeon-agent --no-pager || true
    
    echo ""
    echo "→ 定时器状态:"
    systemctl list-timers | grep aeon || true
fi