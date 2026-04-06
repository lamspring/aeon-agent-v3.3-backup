#!/bin/bash
#
# Aeon Agent 快速启动脚本
# 用于手动启动（不安装系统服务）
#

cd /root/.openclaw/workspace/agent

echo "==============================================="
echo "Aeon Agent v3.0 - 快速启动"
echo "==============================================="
echo ""

# 检查是否已在运行
if pgrep -f "launcher.py --daemon" > /dev/null; then
    echo "⚠️  Aeon Agent 已在运行"
    echo ""
    echo "查看状态: ./health_check.sh"
    echo "停止服务: ./stop.sh"
    exit 1
fi

echo "→ 启动 Aeon Agent..."
echo "   按 Ctrl+C 停止"
echo ""

# 启动
exec python3 launcher.py --daemon