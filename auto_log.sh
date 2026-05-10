#!/bin/bash
# 对话自动记录脚本
# 
# 用法: 在每次回复后调用
# ./auto_log.sh "用户消息" "回复摘要"

cd /root/.openclaw/workspace/agent
source venv/bin/activate 2>/dev/null

USER_MSG="$1"
MY_REPLY="$2"

if [ -z "$USER_MSG" ] || [ -z "$MY_REPLY" ]; then
    echo "Usage: $0 '用户消息' '回复摘要'"
    exit 1
fi

python3 log_conversation.py "$USER_MSG" "$MY_REPLY"
