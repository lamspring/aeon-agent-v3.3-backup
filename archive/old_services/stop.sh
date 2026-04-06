#!/bin/bash
#
# Aeon Agent 停止脚本
#

SERVICE_NAME="aeon-agent"

echo "==============================================="
echo "Aeon Agent v3.0 - 停止服务"
echo "==============================================="
echo ""

# 检查系统服务
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "→ 停止系统服务..."
    systemctl stop "$SERVICE_NAME"
    echo "✅ 系统服务已停止"
    exit 0
fi

# 检查手动启动的进程
PID=$(pgrep -f "launcher.py --daemon" || true)

if [ -n "$PID" ]; then
    echo "→ 停止手动启动的进程 (PID: $PID)..."
    kill -SIGTERM "$PID" 2>/dev/null || true
    
    # 等待进程结束
    for i in {1..10}; do
        if ! pgrep -f "launcher.py --daemon" > /dev/null; then
            echo "✅ 进程已停止"
            exit 0
        fi
        sleep 1
    done
    
    # 强制终止
    echo "→ 强制终止..."
    kill -SIGKILL "$PID" 2>/dev/null || true
    echo "✅ 进程已强制终止"
else
    echo "ℹ️  Aeon Agent 未在运行"
fi