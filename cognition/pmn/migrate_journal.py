"""
PMN数据迁移脚本

将 personality_journal.jsonl 迁移到 PMN SQLite数据库

用法：
    python3 migrate_journal.py
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace/agent/cognition/pmn')

from pmn_manager import PMNManager

JOURNAL_PATH = "/root/.openclaw/workspace/personality_journal.jsonl"
DB_PATH = "/root/.openclaw/workspace/agent/memory/pmn/pmn.db"

def main():
    print("=== PMN 数据迁移 ===")
    
    # 检查journal文件
    from pathlib import Path
    journal = Path(JOURNAL_PATH)
    if not journal.exists() or journal.stat().st_size == 0:
        print(f"Journal file not found or empty: {JOURNAL_PATH}")
        print("Creating PMNManager with empty database...")
    
    # 创建PMNManager（会自动初始化数据库）
    pmn = PMNManager(db_path=DB_PATH)
    
    # 迁移数据
    if journal.exists() and journal.stat().st_size > 0:
        result = pmn.migrate_from_journal(JOURNAL_PATH)
        print(f"Migration result: {result}")
    
    # 验证
    snapshot = pmn.get_personality_snapshot()
    print(f"\nPost-migration snapshot:")
    print(f"  Preferences: {len(snapshot['preferences'])}")
    print(f"  Beliefs: {len(snapshot['beliefs'])}")
    print(f"  Identity: {len(snapshot['identity'])}")
    print(f"  Values: {len(snapshot['values'])}")
    print(f"  Recent episodes: {len(snapshot['recent_episodes'])}")
    
    print("\n✅ Migration complete")

if __name__ == "__main__":
    main()
