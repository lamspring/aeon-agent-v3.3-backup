-- BDI Engine SQLite Schema v2.0
-- 意图表（持久化意图生命周期）

CREATE TABLE IF NOT EXISTS intentions (
    intention_id TEXT PRIMARY KEY,
    plan_id TEXT,
    plan_description TEXT,
    bdi_score REAL,
    belief_alignment REAL,
    desire_alignment REAL,
    personality_bonus REAL,
    selected INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- pending/active/succeeded/failed/dropped
    created_at REAL,
    activated_at REAL,
    completed_at REAL,
    failure_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_intention_status ON intentions(status);
CREATE INDEX IF NOT EXISTS idx_intention_selected ON intentions(selected);

-- 信念更新日志（记录信念置信度变化历史）
CREATE TABLE IF NOT EXISTS belief_history (
    history_id TEXT PRIMARY KEY,
    belief_id TEXT NOT NULL,
    old_confidence REAL,
    new_confidence REAL,
    feedback INTEGER,  -- +1/-1/0
    reason TEXT,
    timestamp REAL
);

CREATE INDEX IF NOT EXISTS idx_belief_history_belief_id ON belief_history(belief_id);

-- 元数据
CREATE TABLE IF NOT EXISTS bdi_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);

INSERT OR IGNORE INTO bdi_meta (key, value, updated_at) 
VALUES ('schema_version', '2.0', CAST(strftime('%s', 'now') AS REAL));
