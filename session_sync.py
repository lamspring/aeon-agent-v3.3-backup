#!/usr/bin/env python3
"""
AEON Session Sync - 将 OpenClaw session files 中的用户消息同步到 AEON events.db

功能：
- 扫描 /root/.openclaw/agents/main/sessions/*.jsonl
- 读取 type == "message" 且 role == "user" 的记录
- 将消息写入 events.db 的 message.received 事件
- 去重：通过 message_id 或 channel+timestamp+content_hash
- 敏感信息过滤：sanitize_message（复用 daily_summary.py 逻辑）
- 跳过系统消息：user_id == "health_check" 的不写入

运行方式：
    python3 session_sync.py          # 独立脚本运行
    from session_sync import sync_sessions; sync_sessions(hours=24)  # 模块导入
"""

import sys
import json
import sqlite3
import hashlib
import re
import glob
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ============================================================================
# 配置
# ============================================================================
SESSIONS_DIR = Path('/root/.openclaw/agents/main/sessions')
EVENTS_DB = Path('/root/.openclaw/workspace/agent/db/events.db')
SKIP_PATTERNS = ('.deleted', '.reset', '.bak', '.lock')


# ============================================================================
# 敏感信息过滤（直接从 daily_summary.py 复用）
# ============================================================================
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


# ============================================================================
# Channel 提取（复用 daily_summary.py 逻辑）
# ============================================================================
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


def _extract_user_id(text: str, channel: str) -> str:
    """从消息内容中提取 user_id"""
    if not text:
        return "unknown"

    # 尝试从各种格式提取 sender
    # Kimi Group Chat Room 格式
    match = re.search(r'\[sender_short_id:\s*([^\]]+)\]', text)
    if match:
        sender = match.group(1).strip()
        return f"{channel}_{sender}"

    # 其他可能的发送者格式
    match = re.search(r'From:\s*([^\n]+)', text)
    if match:
        sender = match.group(1).strip()
        return f"{channel}_{sender}"

    # 默认使用 channel 作为 user_id 前缀
    return f"{channel}_user"


# ============================================================================
# 内容提取
# ============================================================================
def _extract_text_content(content) -> str:
    """从 message.content 中提取纯文本"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                texts.append(item.get('text', ''))
            elif isinstance(item, dict) and 'text' in item:
                texts.append(item['text'])
        return '\n'.join(texts)
    elif content is None:
        return ''
    else:
        return str(content)


def _compute_content_hash(text: str) -> str:
    """计算内容 hash 用于去重"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# ============================================================================
# 数据库操作
# ============================================================================
def _get_db_columns(db_path: Path) -> set:
    """获取 events 表的列名"""
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute("PRAGMA table_info(events)")
            return {row[1] for row in cursor.fetchall()}
    except Exception as e:
        print(f"[SessionSync] Error reading DB schema: {e}")
        return set()


def _build_insert_sql(columns: set) -> str:
    """根据实际列构建 INSERT SQL"""
    base_columns = ['event_id', 'type', 'data', 'timestamp', 'status', 'source']
    if 'priority' in columns:
        base_columns.append('priority')

    placeholders = ', '.join(['?'] * len(base_columns))
    columns_str = ', '.join(base_columns)
    return f"INSERT INTO events ({columns_str}) VALUES ({placeholders})"


def _get_synced_message_ids(db_path: Path, hours: int) -> set:
    """获取最近 N 小时已同步的 message_id 列表"""
    synced_ids = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_ts = cutoff.timestamp()

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute(
                """
                SELECT data FROM events
                WHERE type = 'message.received'
                AND source = 'session_sync'
                AND timestamp > ?
                """,
                (cutoff_ts,)
            )
            for row in cursor.fetchall():
                try:
                    data = json.loads(row[0]) if row[0] else {}
                    msg_id = data.get('message_id')
                    if msg_id:
                        synced_ids.add(msg_id)
                except (json.JSONDecodeError, Exception):
                    continue
    except Exception as e:
        print(f"[SessionSync] Error reading synced IDs: {e}")

    return synced_ids


# ============================================================================
# 核心同步逻辑
# ============================================================================
def sync_sessions(hours: int = 24) -> dict:
    """
    同步最近 N 小时的 session 消息到 events.db

    返回统计信息 dict:
    {
        'files_scanned': int,
        'messages_found': int,
        'new_messages': int,
        'written': int,
        'errors': int
    }
    """
    stats = {
        'files_scanned': 0,
        'messages_found': 0,
        'new_messages': 0,
        'written': 0,
        'errors': 0
    }

    # 检查 sessions 目录
    if not SESSIONS_DIR.exists():
        print(f"[SessionSync] Sessions dir not found: {SESSIONS_DIR}")
        return stats

    # 检查 events.db
    if not EVENTS_DB.exists():
        print(f"[SessionSync] Events DB not found: {EVENTS_DB}")
        return stats

    # 获取 DB 列信息
    db_columns = _get_db_columns(EVENTS_DB)
    if not db_columns:
        print("[SessionSync] Could not read DB schema, aborting")
        return stats

    insert_sql = _build_insert_sql(db_columns)

    # 获取已同步的 message_id（用于去重）
    synced_ids = _get_synced_message_ids(EVENTS_DB, hours)
    print(f"[SessionSync] Found {len(synced_ids)} already-synced messages in last {hours}h")

    # 扫描 session files
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    jsonl_files = list(SESSIONS_DIR.glob('*.jsonl'))
    print(f"[SessionSync] Scanning {len(jsonl_files)} session files")

    records_to_insert = []

    for fpath in jsonl_files:
        # 跳过已删除/重置/备份/锁定文件
        if any(p in fpath.name for p in SKIP_PATTERNS):
            continue

        stats['files_scanned'] += 1

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

                    stats['messages_found'] += 1

                    # 解析时间戳
                    ts_str = record.get('timestamp', '')
                    if not ts_str:
                        continue
                    try:
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
                    raw_text = _extract_text_content(msg.get('content'))
                    if not raw_text or not raw_text.strip():
                        continue

                    # 清洗敏感信息
                    safe_text = sanitize_message(raw_text)

                    # 跳过系统消息
                    channel = _extract_channel(raw_text)
                    user_id = _extract_user_id(raw_text, channel)
                    if user_id == "health_check":
                        continue

                    # 构建 message_id
                    msg_id = record.get('id', '')
                    if msg_id:
                        message_id = f"{channel}:{msg_id}"
                    else:
                        # 没有 id，用 channel + timestamp + content_hash
                        content_hash = _compute_content_hash(safe_text)
                        message_id = f"{channel}:{ts.isoformat()}:{content_hash}"

                    # 去重检查
                    if message_id in synced_ids:
                        continue

                    stats['new_messages'] += 1

                    # 构建 data JSON
                    data = {
                        "user_id": user_id,
                        "channel": channel,
                        "message": safe_text[:2000],  # 限制长度
                        "message_id": message_id,
                        "received_at": ts.isoformat(),
                        "synced_by": "session_sync",
                        "source_file": fpath.name
                    }

                    # 构建插入参数
                    event_id = f"session_sync:{message_id}"
                    timestamp = ts.timestamp()
                    params = [event_id, 'message.received', json.dumps(data, ensure_ascii=False), timestamp, 'pending', 'session_sync']
                    if 'priority' in db_columns:
                        params.append(3)

                    records_to_insert.append(params)

        except Exception as e:
            print(f"[SessionSync] Error reading {fpath.name}: {e}")
            stats['errors'] += 1
            continue

    # 批量写入数据库
    if records_to_insert:
        try:
            with sqlite3.connect(str(EVENTS_DB)) as conn:
                cursor = conn.cursor()
                cursor.executemany(insert_sql, records_to_insert)
                conn.commit()
                stats['written'] = cursor.rowcount
                print(f"[SessionSync] Written {stats['written']} new messages to events.db")
        except Exception as e:
            print(f"[SessionSync] Error writing to events.db: {e}")
            stats['errors'] += 1
    else:
        print(f"[SessionSync] No new messages to write")

    # 打印统计
    print(f"[SessionSync] Summary: {stats['files_scanned']} files scanned, "
          f"{stats['messages_found']} user messages found, "
          f"{stats['new_messages']} new, {stats['written']} written, "
          f"{stats['errors']} errors")

    return stats


# ============================================================================
# 独立脚本入口
# ============================================================================
def main():
    print(f"[{datetime.now().isoformat()}] Session sync started")
    stats = sync_sessions(hours=24)
    print(f"[{datetime.now().isoformat()}] Session sync completed")
    return stats


if __name__ == '__main__':
    main()
