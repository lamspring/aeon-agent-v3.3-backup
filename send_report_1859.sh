#!/bin/bash
# Aeon Agent 18:59 运行报告 - 直接发送到用户

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

# 发送到企业微信
WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=aa988b51-fb13-4b21-bee2-da30d16c92b1"

curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"$REPORT\"}}" > /dev/null 2>&1

# 同时记录到日志
echo "[$(date)] Report sent" >> /var/log/aeon-report.log
