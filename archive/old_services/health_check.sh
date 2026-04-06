#!/bin/bash
#
# Aeon Agent 健康检查脚本
#

SERVICE_NAME="aeon-agent"
AEON_DIR="/root/.openclaw/workspace/agent"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "==============================================="
echo "Aeon Agent 健康检查"
echo "==============================================="
echo ""

# 检查服务状态
echo -e "${BLUE}→ 检查服务状态...${NC}"
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} aeon-agent 运行中"
else
    echo -e "  ${RED}✗${NC} aeon-agent 未运行"
fi

# 检查开机自启
echo ""
echo -e "${BLUE}→ 检查开机自启...${NC}"
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} aeon-agent 已启用"
else
    echo -e "  ${YELLOW}⚠${NC} aeon-agent 未启用开机自启"
fi

# 检查定时器
echo ""
echo -e "${BLUE}→ 检查定时器...${NC}"
if systemctl is-enabled --quiet aeon-memory.timer 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} aeon-memory.timer 已启用"
else
    echo -e "  ${YELLOW}⚠${NC} aeon-memory.timer 未启用"
fi

echo ""
echo "==============================================="
echo "已安装的 Aeon 服务"
echo "==============================================="
systemctl list-unit-files | grep aeon || echo "  (无)"

echo ""
echo "==============================================="
echo "数据库状态"
echo "==============================================="

# 检查数据库文件
dbs=("$AEON_DIR/db/events.db" "$AEON_DIR/db/tasks.db" "$AEON_DIR/db/memory.db")
for db in "${dbs[@]}"; do
    if [ -f "$db" ]; then
        size=$(du -h "$db" 2>/dev/null | cut -f1)
        echo -e "  ${GREEN}✓${NC} $(basename "$db"): $size"
    else
        echo -e "  ${RED}✗${NC} $(basename "$db"): 不存在"
    fi
done

echo ""
echo "==============================================="
echo "日志状态"
echo "==============================================="

# 检查日志文件
logs=("$AEON_DIR/logs/agent.log" "$AEON_DIR/logs/agent.jsonl")
for log in "${logs[@]}"; do
    if [ -f "$log" ]; then
        size=$(du -h "$log" 2>/dev/null | cut -f1)
        lines=$(wc -l < "$log" 2>/dev/null)
        echo -e "  ${GREEN}✓${NC} $(basename "$log"): $size ($lines 行)"
    else
        echo -e "  ${YELLOW}⚠${NC} $(basename "$log"): 不存在"
    fi
done

echo ""
echo "==============================================="
echo "Systemd 状态"
echo "==============================================="

if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl status "$SERVICE_NAME" --no-pager 2>/dev/null || true
else
    echo "  服务未运行，无法获取状态"
fi

echo ""
echo "==============================================="
echo "最近日志 (最近5条)"
echo "==============================================="
journalctl -u "$SERVICE_NAME" --no-pager -n 5 2>/dev/null || echo "  无法获取日志"

echo ""
echo "==============================================="
echo "定时器状态"
echo "==============================================="
systemctl list-timers | grep aeon || echo "  (无定时器)"

echo ""
echo "==============================================="
echo "检查完成"
echo "==============================================="
echo ""
echo "常用命令:"
echo "  sudo systemctl start aeon-agent      # 启动"
echo "  sudo systemctl stop aeon-agent       # 停止"
echo "  sudo systemctl restart aeon-agent    # 重启"
echo "  sudo systemctl status aeon-agent     # 状态"
echo "  sudo journalctl -u aeon-agent -f     # 查看日志"