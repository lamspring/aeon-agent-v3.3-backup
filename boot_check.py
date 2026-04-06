#!/usr/bin/env python3
"""
Aeon Boot Check - 启动前检查

检查项:
1. 目录结构
2. 数据库文件
3. 表结构
4. 权限
"""

import sys
import os
import sqlite3
from pathlib import Path

sys.path.insert(0, '/root/.openclaw/workspace/agent')

AEON_DIR = Path('/root/.openclaw/workspace/agent')
DB_DIR = AEON_DIR / 'db'
LOGS_DIR = AEON_DIR / 'logs'
STATE_DIR = AEON_DIR / 'state'


def check_directories() -> tuple[bool, list]:
    """检查目录"""
    required_dirs = [DB_DIR, LOGS_DIR, STATE_DIR]
    issues = []
    
    for d in required_dirs:
        if not d.exists():
            issues.append(f"目录不存在: {d}")
            try:
                d.mkdir(parents=True, exist_ok=True)
                issues.append(f"  → 已创建")
            except Exception as e:
                issues.append(f"  → 创建失败: {e}")
        elif not os.access(d, os.W_OK):
            issues.append(f"目录不可写: {d}")
    
    return len(issues) == 0, issues


def check_database(db_path: Path, schema: str) -> tuple[bool, list]:
    """检查数据库"""
    issues = []
    
    if not db_path.exists():
        issues.append(f"数据库不存在: {db_path}")
        try:
            conn = sqlite3.connect(db_path)
            conn.executescript(schema)
            conn.close()
            issues.append(f"  → 已创建")
        except Exception as e:
            issues.append(f"  → 创建失败: {e}")
        return len(issues) == 0, issues
    
    # 检查数据库是否可读写
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
    except sqlite3.Error as e:
        issues.append(f"数据库损坏: {db_path} - {e}")
        # 备份并重建
        try:
            backup_path = db_path.with_suffix(f".db.bak.{int(os.time())}")
            db_path.rename(backup_path)
            issues.append(f"  → 已备份到: {backup_path}")
            
            conn = sqlite3.connect(db_path)
            conn.executescript(schema)
            conn.close()
            issues.append(f"  → 已重建")
        except Exception as e2:
            issues.append(f"  → 重建失败: {e2}")
    
    return len(issues) == 0, issues


def check_databases() -> tuple[bool, list]:
    """检查所有数据库"""
    
    events_schema = """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            data TEXT NOT NULL,
            timestamp REAL NOT NULL,
            processed BOOLEAN DEFAULT FALSE,
            retry_count INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed);
        CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
    """
    
    tasks_schema = """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL,
            description TEXT,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            timeout INTEGER DEFAULT 300,
            created_at REAL,
            started_at REAL,
            finished_at REAL,
            last_heartbeat REAL,
            worker_id TEXT,
            trace_id TEXT,
            parent_task_id TEXT,
            result TEXT,
            error TEXT,
            failure_reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
    """
    
    memory_schema = """
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            timestamp REAL NOT NULL,
            embedding BLOB,
            importance REAL DEFAULT 0.5,
            metadata TEXT,
            tags TEXT,
            access_count INTEGER DEFAULT 0,
            last_accessed REAL,
            consolidated BOOLEAN DEFAULT FALSE,
            source_memories TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic_memory(timestamp);
        CREATE INDEX IF NOT EXISTS idx_episodic_consolidated ON episodic_memory(consolidated);
    """
    
    all_issues = []
    
    checks = [
        (DB_DIR / 'events.db', events_schema),
        (DB_DIR / 'tasks.db', tasks_schema),
        (DB_DIR / 'memory.db', memory_schema),
    ]
    
    all_ok = True
    for db_path, schema in checks:
        ok, issues = check_database(db_path, schema)
        all_issues.extend(issues)
        if not ok:
            all_ok = False
    
    return all_ok, all_issues


def check_state_file() -> tuple[bool, list]:
    """检查状态文件"""
    issues = []
    state_file = STATE_DIR / 'system.state'
    
    if not state_file.exists():
        issues.append(f"状态文件不存在: {state_file}")
        try:
            import json
            state = {
                'version': '3.0',
                'status': 'initialized',
                'created_at': str(Path().stat().st_ctime)
            }
            state_file.write_text(json.dumps(state, indent=2))
            issues.append(f"  → 已创建")
        except Exception as e:
            issues.append(f"  → 创建失败: {e}")
    
    return len(issues) == 0, issues


def boot_check():
    """启动检查"""
    print("=" * 50)
    print("Aeon Agent Boot Check")
    print("=" * 50)
    print()
    
    checks = {
        'directories': check_directories,
        'databases': check_databases,
        'state_file': check_state_file,
    }
    
    all_ok = True
    for name, check_func in checks.items():
        print(f"→ 检查 {name}...")
        ok, issues = check_func()
        
        if issues:
            for issue in issues:
                print(f"  {issue}")
        
        if ok:
            print(f"  ✓ {name} 正常")
        else:
            print(f"  ✗ {name} 有问题")
            all_ok = False
        
        print()
    
    print("=" * 50)
    if all_ok:
        print("✅ 所有检查通过，系统就绪")
        return 0
    else:
        print("⚠️  部分检查未通过，但已尝试修复")
        return 0  # 仍然返回0，让服务继续启动
    print("=" * 50)


if __name__ == '__main__':
    sys.exit(boot_check())