#!/usr/bin/env python3
"""
EventBus Cleanup - 积压清理脚本 v1.0

用途: 清理 EventBus 积压的 pending 事件
策略:
1. 删除已过期的事件
2. 归档重复的 reflect 事件（只保留最新50条）
3. 批量标记旧的 subconscious 事件为 done
4. 保留 message.received 和 test.event

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import sqlite3
import time
from datetime import datetime

DB_PATH = "/root/.openclaw/workspace/agent/db/events.db"


def get_stats():
    """获取当前统计"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT status, COUNT(*) FROM events GROUP BY status")
    stats = dict(cursor.fetchall())
    conn.close()
    return stats


def cleanup_expired():
    """清理已过期的事件"""
    conn = sqlite3.connect(DB_PATH)
    now = time.time()
    
    cursor = conn.execute("""
        DELETE FROM events 
        WHERE status = 'pending' 
        AND expires_at IS NOT NULL 
        AND expires_at < ?
    """, (now,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ 清理过期事件: {deleted} 条")
    return deleted


def cleanup_old_reflects(keep_latest=50):
    """清理旧的 reflect 事件，只保留最新 N 条"""
    conn = sqlite3.connect(DB_PATH)
    
    # 获取 reflect 相关类型
    reflect_types = [
        'cognition.reflect',
        'cognition.reflect_completed', 
        'cognition.self_reflection'
    ]
    
    total_archived = 0
    for event_type in reflect_types:
        # 找到需要归档的 ID（除了最新的 N 条）
        cursor = conn.execute("""
            SELECT event_id FROM events 
            WHERE type = ? AND status = 'pending'
            ORDER BY timestamp DESC
            LIMIT -1 OFFSET ?
        """, (event_type, keep_latest))
        
        ids_to_archive = [row[0] for row in cursor.fetchall()]
        
        if ids_to_archive:
            # 批量归档
            placeholders = ','.join('?' * len(ids_to_archive))
            cursor = conn.execute(f"""
                UPDATE events 
                SET status = 'archived', updated_at = ?
                WHERE event_id IN ({placeholders})
            """, (time.time(), *ids_to_archive))
            
            archived = cursor.rowcount
            total_archived += archived
            print(f"  {event_type}: 归档 {archived} 条")
    
    conn.commit()
    conn.close()
    
    print(f"✅ 归档旧 reflect 事件: {total_archived} 条")
    return total_archived


def cleanup_subconscious(keep_latest=10):
    """清理 subconscious 事件"""
    conn = sqlite3.connect(DB_PATH)
    
    subconscious_types = [
        'subconscious.strong_signal',
        'subconscious.state_update'
    ]
    
    total_archived = 0
    for event_type in subconscious_types:
        cursor = conn.execute("""
            SELECT event_id FROM events 
            WHERE type = ? AND status = 'pending'
            ORDER BY timestamp DESC
            LIMIT -1 OFFSET ?
        """, (event_type, keep_latest))
        
        ids_to_archive = [row[0] for row in cursor.fetchall()]
        
        if ids_to_archive:
            placeholders = ','.join('?' * len(ids_to_archive))
            cursor = conn.execute(f"""
                UPDATE events 
                SET status = 'archived', updated_at = ?
                WHERE event_id IN ({placeholders})
            """, (time.time(), *ids_to_archive))
            
            archived = cursor.rowcount
            total_archived += archived
            print(f"  {event_type}: 归档 {archived} 条")
    
    conn.commit()
    conn.close()
    
    print(f"✅ 归档旧 subconscious 事件: {total_archived} 条")
    return total_archived


def cleanup_plan_executed(keep_latest=20):
    """清理 plan_executed 事件"""
    conn = sqlite3.connect(DB_PATH)
    
    cursor = conn.execute("""
        SELECT event_id FROM events 
        WHERE type = 'cognition.plan_executed' AND status = 'pending'
        ORDER BY timestamp DESC
        LIMIT -1 OFFSET ?
    """, (keep_latest,))
    
    ids_to_archive = [row[0] for row in cursor.fetchall()]
    
    if ids_to_archive:
        placeholders = ','.join('?' * len(ids_to_archive))
        cursor = conn.execute(f"""
            UPDATE events 
            SET status = 'archived', updated_at = ?
            WHERE event_id IN ({placeholders})
        """, (time.time(), *ids_to_archive))
        
        archived = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ 归档旧 plan_executed 事件: {archived} 条")
        return archived
    
    conn.close()
    return 0


def vacuum_db():
    """数据库瘦身"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("VACUUM")
    conn.close()
    print("✅ 数据库 VACUUM 完成")


def main():
    print("=" * 50)
    print("EventBus Cleanup v1.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 清理前统计
    before = get_stats()
    print(f"\n清理前:")
    print(f"  pending: {before.get('pending', 0)}")
    print(f"  done: {before.get('done', 0)}")
    print(f"  archived: {before.get('archived', 0)}")
    print(f"  failed: {before.get('failed', 0)}")
    
    # 执行清理
    print(f"\n开始清理...")
    
    deleted = cleanup_expired()
    archived_reflect = cleanup_old_reflects(keep_latest=50)
    archived_sub = cleanup_subconscious(keep_latest=10)
    archived_plan = cleanup_plan_executed(keep_latest=20)
    
    # 清理后统计
    after = get_stats()
    print(f"\n清理后:")
    print(f"  pending: {after.get('pending', 0)} (↓{before.get('pending', 0) - after.get('pending', 0)})")
    print(f"  done: {after.get('done', 0)}")
    print(f"  archived: {after.get('archived', 0)} (↑{after.get('archived', 0) - before.get('archived', 0)})")
    print(f"  failed: {after.get('failed', 0)}")
    
    # 数据库瘦身
    vacuum_db()
    
    total_cleaned = deleted + archived_reflect + archived_sub + archived_plan
    print(f"\n{'=' * 50}")
    print(f"总计清理: {total_cleaned} 条")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
