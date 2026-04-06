#!/bin/bash
#
# Aeon Agent 服务卸载脚本
#

set -e

SERVICE_NAME="aeon-agent"

echo "==============================================="
echo "Aeon Agent v3.0 - 服务卸载"
echo "==============================================="
echo ""

# 检查root权限
if [ "$EUID" -ne 0 ]; then 
    echo "❌ 请使用 sudo 运行此脚本"
    exit 1
fi

# 确认
echo "⚠️  这将停止并卸载 Aeon Agent 系统服务"
echo "   数据文件将保留"
echo ""
echo "确认卸载? (y/n)"
read -r response
if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "→ 停止定时器..."
systemctl stop aeon-memory.timer 2>/dev/null || true

echo "→ 停止服务..."
systemctl stop aeon-agent 2>/dev/null || true

echo "→ 禁用定时器..."
systemctl disable aeon-memory.timer 2>/dev/null || true

echo "→ 禁用服务..."
systemctl disable aeon-agent 2>/dev/null || true

echo "→ 删除服务文件..."
rm -f "/etc/systemd/system/aeon-agent.service"
rm -f "/etc/systemd/system/aeon-memory.service"
rm -f "/etc/systemd/system/aeon-memory.timer"

echo "→ 重新加载 systemd..."
systemctl daemon-reload

echo ""
echo "==============================================="
echo "✅ 卸载完成"
echo "==============================================="
echo ""
echo "数据文件位置 (未删除):"
echo "  /root/.openclaw/workspace/agent/db/"
echo "  /root/.openclaw/workspace/agent/logs/"
echo "  /root/.openclaw/workspace/agent/state/"
echo ""
echo "如需完全删除，请手动执行:"
echo "  rm -rf /root/.openclaw/workspace/agent/"