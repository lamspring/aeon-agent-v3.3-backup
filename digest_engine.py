#!/usr/bin/env python3
"""
Digest Engine - 结构化摘要生成器

每天 02:45 运行：
1. 从 events.db 读取最近24小时的用户消息
2. 用 rules.py 进行规则分析
3. 生成 DailyDigest
4. 保存到 events.db（类型：daily.digest）

Usage:
    python3 digest_engine.py
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent')

import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from digest.models import DailyDigest
from digest.rules import generate_daily_digest

DB_PATH = '/root/.openclaw/workspace/agent/db/events.db'


def load_recent_messages(hours: int = 24) -> List[Dict]:
    """从 events.db 读取最近的用户消息"""
    messages = []
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_ts = cutoff.timestamp()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT data, timestamp
                FROM events
                WHERE type = 'message.received'
                  AND source = 'session_sync'
                  AND timestamp > ?
                ORDER BY timestamp ASC
            """, (cutoff_ts,))

            for row in cursor.fetchall():
                try:
                    data = json.loads(row[0]) if row[0] else {}
                    ts = row[1]

                    msg = data.get('message', '')
                    if not msg or not msg.strip():
                        continue

                    messages.append({
                        'message_id': data.get('message_id', ''),
                        'timestamp': ts,
                        'channel': data.get('channel', 'unknown'),
                        'user_id': data.get('user_id', 'unknown'),
                        'content': msg,
                        'received_at': data.get('received_at', ''),
                        'source_file': data.get('source_file', ''),
                    })
                except Exception as e:
                    print(f"[DigestEngine] Error parsing message row: {e}")
                    continue
    except Exception as e:
        print(f"[DigestEngine] Error loading messages from DB: {e}")

    return messages


def save_digest(digest: DailyDigest):
    """保存摘要到 events.db"""
    try:
        # 将 digest 序列化为 JSON
        digest_data = {
            'date': digest.date,
            'generated_at': digest.generated_at.isoformat(),
            'total_messages': digest.total_messages,
            'channels': digest.channels,
            'topic_distribution': digest.topic_distribution,
            'emotion_distribution': digest.emotion_distribution,
            'message_digests': [
                {
                    'message_id': md.message_id,
                    'timestamp': md.timestamp.isoformat() if isinstance(md.timestamp, datetime) else md.timestamp,
                    'channel': md.channel,
                    'user_id': md.user_id,
                    'content_preview': md.content_preview,
                    'topic': md.topic,
                    'emotion': md.emotion,
                    'is_explicit_todo': md.is_explicit_todo,
                    'hour': md.hour,
                }
                for md in digest.message_digests
            ],
            'explicit_todos': digest.explicit_todos,
            'late_night_flag': digest.late_night_flag,
            'late_night_hours': digest.late_night_hours,
            'key_topics': digest.key_topics,
            'llm_insight': digest.llm_insight,
        }

        # 先检查是否已有同日期摘要
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("""
                SELECT event_id FROM events
                WHERE type = 'daily.digest'
                  AND json_extract(data, '$.date') = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (digest.date,))

            existing = cursor.fetchone()

            if existing:
                # 更新已有记录
                conn.execute("""
                    UPDATE events
                    SET data = ?, timestamp = ?, processed = FALSE
                    WHERE event_id = ?
                """, (
                    json.dumps(digest_data, ensure_ascii=False),
                    datetime.now().timestamp(),
                    existing[0],
                ))
                print(f"[DigestEngine] Updated existing digest for {digest.date}")
            else:
                # 插入新记录
                event_id = f"digest_{digest.date}_{uuid.uuid4().hex[:8]}"
                conn.execute("""
                    INSERT INTO events
                    (event_id, type, data, timestamp, status, source, processed)
                    VALUES (?, 'daily.digest', ?, ?, 'completed', 'digest_engine', TRUE)
                """, (
                    event_id,
                    json.dumps(digest_data, ensure_ascii=False),
                    datetime.now().timestamp(),
                ))
                print(f"[DigestEngine] Inserted new digest for {digest.date}")

            conn.commit()

    except Exception as e:
        print(f"[DigestEngine] Error saving digest: {e}")
        raise


def main():
    print(f"[{datetime.now().isoformat()}] Digest engine started")

    # 1. 加载消息
    messages = load_recent_messages(hours=24)
    print(f"[DigestEngine] Loaded {len(messages)} messages")

    if not messages:
        print("[DigestEngine] No messages, skipping")
        return

    # 2. 生成摘要
    today = datetime.now().strftime('%Y-%m-%d')
    digest = generate_daily_digest(messages, today)
    print(f"[DigestEngine] Generated digest: {digest.total_messages} msgs, "
          f"topics: {digest.topic_distribution}")

    # 3. 保存
    save_digest(digest)
    print(f"[DigestEngine] Digest saved")

    print(f"[{datetime.now().isoformat()}] Digest engine completed")


if __name__ == '__main__':
    main()
