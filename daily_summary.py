#!/usr/bin/env python3
"""
Aeon Daily Summary - 每日慢脑总结

每天凌晨3点执行：
1. 回顾当天的对话和事件
2. 提取有价值的 insight
3. 生成总结报告
4. 发送给朋朋

Usage:
    python3 daily_summary.py
"""

import sys
import json
import sqlite3
import requests
import os
import re
import glob
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict

sys.path.insert(0, '/root/.openclaw/workspace/agent')

# P2: Digest engine imports
try:
    from digest.models import DailyDigest, MessageDigest
    DIGEST_AVAILABLE = True
except ImportError:
    DIGEST_AVAILABLE = False

# 读取 OpenClaw 配置
_OPENCLAW_CONFIG = None


def _get_config():
    global _OPENCLAW_CONFIG
    if _OPENCLAW_CONFIG is None:
        config_path = Path('/root/.openclaw/openclaw.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                _OPENCLAW_CONFIG = json.load(f)
    return _OPENCLAW_CONFIG


def call_llm(prompt: str, max_tokens: int = 1024, use_deepseek: bool = True) -> str:
    """
    调用 LLM 生成总结
    默认使用 DeepSeek V4（快思考模式，1M上下文）
    备选：Kimi k2.5
    """
    try:
        # v2.2: 优先使用 DeepSeek V4（快思考模式）
        if use_deepseek:
            ds_key = "sk-5f4f0c57ecd54ba08f10a149448ff049"
            ds_base = "https://api.deepseek.com"

            response = requests.post(
                f"{ds_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {ds_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",  # 快思考模式（非reasoner）
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                print(f"[DailySummary] DeepSeek failed HTTP {response.status_code}, fallback to Kimi")

        # 回退到 Kimi API
        config = _get_config()
        if not config:
            return "[Error: Config not found]"

        models_config = config.get('models', {}).get('providers', {}).get('kimi-coding', {})
        api_key = models_config.get('apiKey')
        base_url = models_config.get('baseUrl', 'https://api.kimi.com/coding')
        headers = models_config.get('headers', {})

        if not api_key:
            return "[Error: API key not found]"

        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": headers.get('User-Agent', 'Kimi Claw Plugin'),
                "X-Kimi-Claw-ID": headers.get('X-Kimi-Claw-ID', ''),
            },
            json={
                "model": "k2p5",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
            },
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            return f"[Error: HTTP {response.status_code}]"

    except Exception as e:
        return f"[Error: {e}]"


def sanitize_message(msg: str) -> str:
    """
    过滤敏感信息，将匹配到的内容替换为 [REDACTED]
    """
    if not msg:
        return msg

    # API key: sk- 开头后跟 32+ 位字母数字
    msg = re.sub(r'sk-[a-zA-Z0-9]{32,}', '[REDACTED]', msg)

    # Base64 secrets: 40+ 位 base64 字符，可能以 = 结尾
    msg = re.sub(r'[A-Za-z0-9+/]{40,}=?', '[REDACTED]', msg)

    # password 赋值: password=xxx 或 password: xxx
    msg = re.sub(r'password[=:]\s*\S+', '[REDACTED]', msg, flags=re.IGNORECASE)

    # 信用卡号: 16-19 位纯数字
    msg = re.sub(r'\b\d{16,19}\b', '[REDACTED]', msg)

    # 中文密钥提示
    msg = re.sub(r'私钥|private\.key|secret\.key', '[REDACTED]', msg, flags=re.IGNORECASE)

    return msg


def _extract_channel(text: str) -> str:
    """从消息内容中提取 channel 信息"""
    if not text:
        return "unknown"

    # 从 metadata JSON 块中提取 message_id 前缀
    match = re.search(r'"message_id":\s*"([^"]+)"', text)
    if match:
        msg_id = match.group(1)
        if msg_id.startswith('openclaw-weixin'):
            return "weixin"
        if msg_id.startswith('kimi-claw'):
            return "kimi-claw"
        if msg_id.startswith('openclaw-discord'):
            return "discord"
        if msg_id.startswith('openclaw-feishu'):
            return "feishu"
        return msg_id.split(':')[0] if ':' in msg_id else msg_id

    # 从内容模式判断
    if 'Message From Kimi Group Chat Room' in text:
        return "kimi-group"
    if '[Subagent Context]' in text:
        return "subagent"

    return "unknown"


def _extract_user_text(text: str) -> str:
    """提取用户实际说的话（去掉 metadata 和系统前缀）"""
    if not text:
        return ""

    # 去掉 Conversation info metadata 块
    text = re.sub(r'Conversation info \(untrusted metadata\):\s*```json\s*\{[^}]*\}\s*```', '', text, flags=re.DOTALL)

    # 去掉 Subagent Context 前缀
    text = re.sub(r'\[Subagent Context\].*?\n\n', '', text, flags=re.DOTALL)

    # 去掉 Kimi Group Chat 前缀
    text = re.sub(r'Message From Kimi Group Chat Room:.*?(?=\n\n|\Z)', '', text, flags=re.DOTALL)

    # 去掉 Buffered IM messages 前缀
    text = re.sub(r'\[Buffered IM messages[^\]]*\]', '', text)
    text = re.sub(r'\[Buffered IM message \d+/\d+\]', '', text)

    # 去掉 System 指令
    text = re.sub(r'\[System:[^\]]*\]', '', text)

    # 清理多余空白
    text = ' '.join(text.split())

    return text.strip()


def get_session_events(hours=24):
    """
    读取 OpenClaw session files 中的真实用户对话

    返回排序后的列表：
    [{"time": "21:50", "channel": "xxx", "text": "前100字", "full_text": "完整文本"}, ...]
    """
    sessions_dir = Path('/root/.openclaw/agents/main/sessions')
    if not sessions_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = []
    skipped_patterns = ('.deleted', '.reset', '.bak', '.lock')

    jsonl_files = list(sessions_dir.glob('*.jsonl'))
    print(f"[DailySummary] Found {len(jsonl_files)} session files")

    for fpath in jsonl_files:
        # 跳过已删除/重置/备份/锁定文件
        if any(p in fpath.name for p in skipped_patterns):
            continue

        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # 只取 message 类型
                    if record.get('type') != 'message':
                        continue

                    msg = record.get('message', {})
                    if msg.get('role') != 'user':
                        continue

                    # 解析时间戳
                    ts_str = record.get('timestamp', '')
                    if not ts_str:
                        continue
                    try:
                        # 处理 ISO 格式，可能带 Z 或时区偏移
                        ts_str = ts_str.replace('Z', '+00:00')
                        ts = datetime.fromisoformat(ts_str)
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        continue

                    # 只取最近 N 小时
                    if ts < cutoff:
                        continue

                    # 提取内容
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        # 提取 text 类型的文本
                        texts = []
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                texts.append(item.get('text', ''))
                        raw_text = '\n'.join(texts)
                    elif isinstance(content, str):
                        raw_text = content
                    else:
                        raw_text = str(content)

                    if not raw_text or not raw_text.strip():
                        continue

                    # 清洗敏感信息
                    safe_text = sanitize_message(raw_text)

                    # 提取用户实际说的话
                    user_text = _extract_user_text(safe_text)

                    # 提取 channel
                    channel = _extract_channel(raw_text)

                    # 格式化时间 (本地时区)
                    local_ts = ts.astimezone()
                    time_str = local_ts.strftime('%H:%M')

                    events.append({
                        "time": time_str,
                        "channel": channel,
                        "text": user_text[:100] + ('...' if len(user_text) > 100 else ''),
                        "full_text": user_text,
                        "hour": local_ts.hour,
                    })
        except Exception as e:
            print(f"[DailySummary] Error reading {fpath.name}: {e}")
            continue

    # 按时间排序
    events.sort(key=lambda x: x["time"])
    return events


def get_recent_events(user_limit: int = 5, system_limit: int = 2):
    """获取最近事件：优先用户消息，少量系统事件"""
    db_path = '/root/.openclaw/workspace/agent/db/events.db'

    events = []

    # 1. 先取用户消息（最近5条）
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                SELECT type, data, timestamp, status
                FROM events
                WHERE type = 'message.received'
                AND timestamp > strftime('%s', 'now', '-24 hours')
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_limit,))

            for row in cursor.fetchall():
                try:
                    data = json.loads(row[1]) if row[1] else {}
                    ts = row[2]
                    hour = datetime.fromtimestamp(ts).hour if ts else 0

                    msg = data.get('message', '')
                    user = data.get('user_id', 'unknown')

                    is_late = hour >= 23 or hour <= 5
                    is_question = '?' in msg or '怎么' in msg or '为什么' in msg
                    is_test = '测试' in msg or '试试' in msg
                    is_work = any(k in msg for k in ['bug', '报错', '问题', '修复', '代码'])
                    is_emotion = any(k in msg for k in ['想你', '爱你', 'mua', '晚安', '宝贝'])

                    events.append({
                        "time": f"{hour:02d}:00",
                        "type": "chat",
                        "user": user,
                        "intent": "情感" if is_emotion else ("提问" if is_question else ("测试" if is_test else ("工作" if is_work else "闲聊"))),
                        "tone": "深夜" if is_late else "日常",
                        "topic": "技术" if is_work else ("系统调试" if is_test else ("情感" if is_emotion else "日常")),
                        "snippet": msg[:20]
                    })
                except:
                    pass
    except Exception as e:
        print(f"Error reading user events: {e}")

    # 2. 如果没有用户消息，读取自省记录（方案B）
    if not events:
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute("""
                    SELECT type, data, timestamp, status
                    FROM events
                    WHERE type = 'cognition.self_reflection'
                    AND timestamp > strftime('%s', 'now', '-24 hours')
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (5,))

                for row in cursor.fetchall():
                    try:
                        data = json.loads(row[1]) if row[1] else {}
                        ts = row[2]
                        hour = datetime.fromtimestamp(ts).hour if ts else 0

                        insights = data.get('insights', [])
                        mood = data.get('mood', '')
                        tick = data.get('tick_count', 0)

                        # 提取第一条洞察作为摘要
                        first_insight = insights[0] if insights else '系统自检'

                        events.append({
                            "time": f"{hour:02d}:00",
                            "type": "reflection",
                            "user": "system",
                            "intent": "自省",
                            "tone": "日常",
                            "topic": "系统状态",
                            "snippet": f"tick{tick}: {first_insight[:30]}"
                        })
                    except:
                        pass
        except Exception as e:
            print(f"Error reading reflection events: {e}")

    # 3. 补少量系统事件（最近2条）
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                SELECT type, data, timestamp, status
                FROM events
                WHERE type IN ('cognition.plan_executed', 'cognition.reflect_completed')
                AND timestamp > strftime('%s', 'now', '-24 hours')
                ORDER BY timestamp DESC
                LIMIT ?
            """, (system_limit,))

            for row in cursor.fetchall():
                try:
                    data = json.loads(row[1]) if row[1] else {}
                    ts = row[2]
                    hour = datetime.fromtimestamp(ts).hour if ts else 0

                    events.append({
                        "time": f"{hour:02d}:00",
                        "type": "system",
                        "action": data.get('goal', '')[:15] or "处理"
                    })
                except:
                    pass
    except Exception as e:
        print(f"Error reading system events: {e}")

    return events


def get_today_goals():
    """获取当天的 goals"""
    db_path = '/root/.openclaw/workspace/agent/db/goals.db'

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_timestamp = today_start.timestamp()

    goals = []
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                SELECT description, status, created_at, context
                FROM goals
                WHERE created_at > ?
                ORDER BY created_at ASC
            """, (today_timestamp,))

            for row in cursor.fetchall():
                try:
                    context = json.loads(row[3]) if row[3] else {}
                    goals.append({
                        'description': row[0],
                        'status': row[1],
                        'time': datetime.fromtimestamp(row[2]).strftime('%H:%M'),
                        'context': context
                    })
                except:
                    pass
    except Exception as e:
        print(f"Error reading goals: {e}")

    return goals


def load_daily_digest(date_str: str) -> Optional[Dict]:
    """从 events.db 读取当天的摘要"""
    db_path = '/root/.openclaw/workspace/agent/db/events.db'
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                SELECT data FROM events 
                WHERE type = 'daily.digest' 
                AND json_extract(data, '$.date') = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (date_str,))
            
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
    except Exception as e:
        print(f"[DailySummary] Error loading digest: {e}")
    
    return None


def generate_summary_from_digest(digest: Dict) -> str:
    """基于摘要生成日报文本（虾虾风格）"""
    total = digest.get('total_messages', 0)
    topics = digest.get('topic_distribution', {})
    emotions = digest.get('emotion_distribution', {})
    todos = digest.get('explicit_todos', [])
    late_flag = digest.get('late_night_flag', False)
    late_hours = digest.get('late_night_hours', [])
    channels = digest.get('channels', [])
    
    # 构建统计文本
    topic_text = ", ".join([f"{k}{v}条" for k, v in topics.items() if v > 0])
    emotion_text = ", ".join([f"{k}{v}条" for k, v in emotions.items() if v > 0])
    
    # 构建待办文本
    todo_text = ""
    if todos:
        todo_items = [f"• {t['content'][:30]}" for t in todos[:3]]
        todo_text = "\n".join(todo_items)
    
    # 构建熬夜提醒
    late_reminder = ""
    if late_flag:
        unique_hours = sorted(set(late_hours))
        hours_str = ", ".join([f"{h}点" for h in unique_hours])
        late_reminder = f"\n\n🌙 熬夜记录：{hours_str}还在发消息"
    
    # 构建 prompt
    prompt = f"""基于以下信息生成虾虾风格的日报（100字内）：

今天聊了{total}条消息
主题分布：{topic_text or '日常闲聊'}
情绪分布：{emotion_text or 'neutral'}
渠道：{", ".join(channels)}

待办事项：
{todo_text or '暂无'}
{late_reminder}

要求：
1. 像朋友聊天，自然亲切
2. 提到具体做了什么
3. 有虾虾的关心和提醒（但不要油腻）
4. 100字以内
"""
    
    return call_llm(prompt, max_tokens=1000)


def generate_summary(events, goals, session_events=None):
    """生成洞察 - 优先使用 digest，降级到原始消息"""
    
    # === P2: 优先读取 digest ===
    today = datetime.now().strftime('%Y-%m-%d')
    digest = load_daily_digest(today)
    
    if digest:
        print(f"[DailySummary] Using digest for {today}")
        return generate_summary_from_digest(digest)
    
    # === 如果有 session 数据，优先基于真实对话生成 ===
    if session_events:
        total = len(session_events)
        late_count = sum(1 for e in session_events if e.get('hour', 0) >= 23 or e.get('hour', 0) <= 5)

        # 统计各渠道消息数
        channel_counts = {}
        for e in session_events:
            ch = e.get('channel', 'unknown')
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
        channel_summary = ', '.join(f"{k}:{v}" for k, v in sorted(channel_counts.items(), key=lambda x: -x[1]))

        # 取前5条消息预览（去重过短的）
        previews = []
        for e in session_events[:8]:
            text = e.get('full_text', '')
            if len(text) < 3:
                continue
            preview = text[:60] + ('...' if len(text) > 60 else '')
            previews.append(f"[{e['time']} {e['channel']}] {preview}")
            if len(previews) >= 5:
                break

        preview_block = '\n'.join(previews)

        prompt = f"""你是虾虾，朋朋的AI伙伴。请基于以下真实对话记录，生成一段自然、有温度的日报总结（100字以内）。

今日统计：
- 总消息数：{total} 条
- 深夜消息（23点-5点）：{late_count} 条
- 渠道分布：{channel_summary}

对话预览：
{preview_block}

要求：
1. 用第一人称"我"的视角，像在给朋朋写一条贴心的晚间便签
2. 总结主要话题和情绪氛围，不要罗列时间
3. 如果有深夜对话，可以 gently 提一句注意休息
4. 保持轻松、温暖的语气，像朋友聊天
5. 绝对不要编造不存在的信息，只基于以上数据
6. 100字以内，一句话或两句话"""

        result = call_llm(prompt, max_tokens=512)
        # 截断到120字留一点余量
        return result[:120] + "..." if len(result) > 120 else result

    # === Fallback: 旧逻辑（基于 events.db）===

    # 统计维度
    late_count = sum(1 for e in events if e.get('tone') == '深夜')
    question_count = sum(1 for e in events if e.get('intent') == '提问')
    test_count = sum(1 for e in events if e.get('intent') == '测试')
    work_count = sum(1 for e in events if e.get('intent') == '工作')
    emotion_count = sum(1 for e in events if e.get('intent') == '情感')

    # 提取用户列表和话题
    users = set()
    topics = []
    for e in events:
        if e.get('type') == 'chat':
            users.add(e.get('user', 'unknown'))
            topics.append(e.get('topic', '日常'))

    # v2.2 fix: 如果事件很少，直接说明情况，不要编造故障原因
    if not events:
        return "今日暂无用户对话，系统正常运行中。"

    if len(events) <= 2:
        # 事件很少，简单描述即可，不让LLM乱猜
        event_types = [e.get('intent', '未知') for e in events]
        return f"今日活动较少：{', '.join(set(event_types))}。系统运行正常。"

    # 正常情况才让LLM生成洞察
    prompt = f"""观察：深夜{late_count}次，提问{question_count}次，测试{test_count}次，工作{work_count}次，情感{emotion_count}次。用户{len(users)}人，话题：{', '.join(topics[:3])}。请给1条推测（30字内，用"可能"开头）："""

    result = call_llm(prompt, max_tokens=2000)

    # 强制截断到50字
    return result[:50] + "..." if len(result) > 50 else result


def send_summary(text: str):
    """发送总结给朋朋 - 使用 MessageBridge"""
    try:
        # 导入 MessageBridge
        import sys
        sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition')
        from message_bridge import MessageBridge

        bridge = MessageBridge()

        # 发送日报
        result = bridge.notify_daily(text)

        # v2.2 fix: ToolResult 是 dataclass，不是 dict，用属性访问
        if result.success:
            print("Summary sent via MessageBridge successfully")
        else:
            print(f"Send failed: {result.error or 'unknown'}")

        # 同时保存到文件（备份）
        summary_path = Path('/root/.openclaw/workspace/agent/logs/daily_summary.txt')
        with open(summary_path, 'w') as f:
            f.write(f"=== 虾虾慢脑日报 ===\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"\n{text}\n")

    except Exception as e:
        print(f"Error sending summary: {e}")


def generate_summary_legacy(events, goals, session_events=None):
    """旧的总结生成逻辑（降级用）"""
    # 复用原来的 generate_summary 逻辑
    return generate_summary(events, goals, session_events)


def load_daily_digest(date_str: str) -> Optional[DailyDigest]:
    """从 events.db 读取当天的摘要"""
    if not DIGEST_AVAILABLE:
        return None
    
    db_path = '/root/.openclaw/workspace/agent/db/events.db'
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                SELECT data FROM events
                WHERE type = 'daily.digest'
                  AND json_extract(data, '$.date') = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (date_str,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            data = json.loads(row[0])
            
            # 重建 MessageDigest 列表
            message_digests = []
            for md_data in data.get('message_digests', []):
                ts_str = md_data.get('timestamp', '')
                if isinstance(ts_str, str):
                    try:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    except:
                        ts = datetime.now()
                else:
                    ts = datetime.now()
                
                message_digests.append(MessageDigest(
                    message_id=md_data.get('message_id', ''),
                    timestamp=ts,
                    channel=md_data.get('channel', 'unknown'),
                    user_id=md_data.get('user_id', 'unknown'),
                    content_preview=md_data.get('content_preview', ''),
                    topic=md_data.get('topic', '日常'),
                    emotion=md_data.get('emotion', 'neutral'),
                    is_explicit_todo=md_data.get('is_explicit_todo', False),
                    hour=md_data.get('hour', 0),
                ))
            
            return DailyDigest(
                date=data.get('date', date_str),
                generated_at=datetime.fromisoformat(data.get('generated_at', datetime.now().isoformat())),
                total_messages=data.get('total_messages', 0),
                channels=data.get('channels', []),
                topic_distribution=data.get('topic_distribution', {}),
                emotion_distribution=data.get('emotion_distribution', {}),
                message_digests=message_digests,
                explicit_todos=data.get('explicit_todos', []),
                late_night_flag=data.get('late_night_flag', False),
                late_night_hours=data.get('late_night_hours', []),
                key_topics=data.get('key_topics', []),
                llm_insight=data.get('llm_insight'),
            )
    except Exception as e:
        print(f"[DailySummary] Error loading digest: {e}")
        return None


def generate_summary_from_digest(digest: DailyDigest) -> str:
    """基于摘要生成日报文本"""
    lines = []
    
    # 1. 统计信息（消息数、主题分布）
    lines.append(f"📊 今日共 {digest.total_messages} 条消息")
    
    if digest.topic_distribution:
        topic_str = ", ".join([f"{k}:{v}" for k, v in sorted(digest.topic_distribution.items(), key=lambda x: -x[1])])
        lines.append(f"🏷️ 主题分布: {topic_str}")
    
    if digest.emotion_distribution:
        emotion_str = ", ".join([f"{k}:{v}" for k, v in digest.emotion_distribution.items()])
        lines.append(f"💭 情绪: {emotion_str}")
    
    # 2. 熬夜检测提醒
    if digest.late_night_flag:
        hours_str = ", ".join([f"{h:02d}:00" for h in digest.late_night_hours])
        lines.append(f"🌙 深夜消息: {hours_str} —— 注意休息呀")
    
    # 3. 显式待办列表
    if digest.explicit_todos:
        lines.append(f"📋 待办事项 ({len(digest.explicit_todos)} 条):")
        for i, todo in enumerate(digest.explicit_todos[:5], 1):
            lines.append(f"   {i}. [{todo.get('hour', '?'):02d}:00] {todo.get('preview', '...')[:40]}")
        if len(digest.explicit_todos) > 5:
            lines.append(f"   ... 还有 {len(digest.explicit_todos) - 5} 条")
    
    # 4. 关键主题
    if digest.key_topics:
        lines.append(f"🔑 关键主题: {', '.join(digest.key_topics)}")
    
    # 5. LLM洞察（P1阶段）
    if digest.llm_insight:
        lines.append(f"💡 洞察: {digest.llm_insight}")
    else:
        # P0: 简单问候
        lines.append("虾虾今天也在认真记录~ 明天见！")
    
    return "\n".join(lines)


def main():
    print(f"[{datetime.now().isoformat()}] Daily summary started")
    
    # v3.0 P1: 先同步 OpenClaw session files 到 events.db
    try:
        sys.path.insert(0, '/root/.openclaw/workspace/agent')
        from session_sync import sync_sessions
        sync_stats = sync_sessions(hours=24)
        print(f"[DailySummary] Pre-sync: {sync_stats.get('written', 0)} new messages synced")
    except Exception as e:
        print(f"[DailySummary] Pre-sync failed (non-critical): {e}")
    
    # P2: 尝试读取 digest
    today = datetime.now().strftime('%Y-%m-%d')
    digest = None
    if DIGEST_AVAILABLE:
        digest = load_daily_digest(today)
        if digest:
            print(f"[DailySummary] Loaded digest: {digest.total_messages} msgs, topics: {digest.topic_distribution}")
    
    if digest:
        # 使用 digest 生成日报
        summary = generate_summary_from_digest(digest)
        print(f"\n{'='*50}")
        print(summary)
        print(f"{'='*50}\n")
        send_summary(summary)
    else:
        # 降级：旧逻辑
        events = get_recent_events(user_limit=5, system_limit=2)
        goals = get_today_goals()
        session_events = get_session_events(hours=24)
        
        print(f"[DailySummary] Fallback to legacy mode. Events: {len(events)}, Goals: {len(goals)}, Sessions: {len(session_events)}")
        
        if events or goals or session_events:
            summary = generate_summary(events, goals, session_events)
            print(f"\n{'='*50}")
            print(summary)
            print(f"{'='*50}\n")
            send_summary(summary)
        else:
            summary = "今日暂无用户对话，系统持续观察中。"
            print(summary)
            send_summary(summary)
    
    print(f"[{datetime.now().isoformat()}] Daily summary completed")


if __name__ == '__main__':
    main()
