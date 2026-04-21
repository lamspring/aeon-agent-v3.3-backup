
import os
import sqlite3

def patch_goal_manager_runtime(gm):
    # 修复断手：注入数据库路径属性
    if not hasattr(gm, 'db_path'):
        gm.db_path = '/root/.openclaw/workspace/agent/db/goals.db'
        print(f"[Bridge] 🛠️ 已补全 GoalManager.db_path: {gm.db_path}")

def on_tick_start(agent):
    # 每个 tick 开始时，确保 GM 的属性正常
    if hasattr(agent, 'goal_manager'):
        patch_goal_manager_runtime(agent.goal_manager)
