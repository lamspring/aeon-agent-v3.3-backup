#!/bin/bash
# Aeon Agent 18:59 运行报告 - 直接发送到用户
# NOTE: 企业微信 Webhook URL 需通过环境变量 WECHAT_WEBHOOK_URL 注入

cd /root/.openclaw/workspace/agent

REPORT=$(python3 -c "
import json
import urllib.request
import subprocess
from datetime import datetime

try:
    from goals import GoalManager
    gm = GoalManager()
    stats = gm.get_statistics()
    active_goal = gm.get_active_goal()
    goal_info = active_goal.description[:30] if active_goal else 'None'
except:
    stats = {'active': '?', 'pending': '?'}
    goal_info = 'Error'

try:
    response = urllib.request.urlopen('http://localhost:9090/health', timeout=5)
    health = json.loads(response.read())
    health_status = health['status']
    queue_size = health['checks']['queue_size']
except Exception as e:
    health_status = f'Error: {e}'
    queue_size = '?'

try:
    result = subprocess.run(['systemctl', 'is-active', 'aeon-agent.service'],
                           capture_output=True, text=True)
    systemd_status = result.stdout.strip()
except:
    systemd_status = 'unknown'

print(f'''AEON AGENT v3.1 - 18:59 运行报告
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔧 Systemd: {systemd_status}
🏥 Health: {health_status}
📊 Queue: {queue_size}
🎯 Goals: {stats.get('active', '?')} active, {stats.get('pending', '?')} pending
📌 Current: {goal_info}

—虾虾''')
")

# 从环境变量读取 Webhook URL（安全最佳实践）
WEBHOOK="${WECHAT_WEBHOOK_URL:-}"

if [ -n "$WEBHOOK" ]; then
    curl -s -X POST "$WEBHOOK" \
      -H "Content-Type: application/json" \
      -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"$REPORT\"}}" > /dev/null 2>&1
    echo "[$(date)] Report sent via webhook" >> /var/log/aeon-report.log
else
    echo "[$(date)] WECHAT_WEBHOOK_URL not set, skipping webhook" >> /var/log/aeon-report.log
fi
