-- PMNManager SQLite Schema v2.0
-- 人格记忆网络数据库表结构

-- EpisodicMemory（情景层）
CREATE TABLE IF NOT EXISTS episodic_nodes (
    node_id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('user_message', 'tool_call', 'error', 'reflection', 'preference_detected', 'milestone')),
    content TEXT NOT NULL,
    raw_context_hash TEXT,
    emotional_valence REAL DEFAULT 0 CHECK(emotional_valence BETWEEN -1 AND 1),
    emotional_arousal REAL DEFAULT 0 CHECK(emotional_arousal BETWEEN 0 AND 1),
    importance_score REAL DEFAULT 0.5 CHECK(importance_score BETWEEN 0 AND 1),
    related_semantic_ids TEXT  -- JSON array
);

CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic_nodes(timestamp);
CREATE INDEX IF NOT EXISTS idx_episodic_type ON episodic_nodes(event_type);
CREATE INDEX IF NOT EXISTS idx_episodic_importance ON episodic_nodes(importance_score DESC);

-- SemanticMemory（语义层）
CREATE TABLE IF NOT EXISTS semantic_nodes (
    node_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('belief', 'preference', 'knowledge', 'skill')),
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT,
    confidence REAL DEFAULT 0.5 CHECK(confidence BETWEEN 0 AND 1),
    evidence_count INTEGER DEFAULT 1,
    source_episode_ids TEXT,  -- JSON array
    embedding BLOB  -- 向量嵌入（可选）
);

CREATE INDEX IF NOT EXISTS idx_semantic_category ON semantic_nodes(category);
CREATE INDEX IF NOT EXISTS idx_semantic_subject ON semantic_nodes(subject);
CREATE INDEX IF NOT EXISTS idx_semantic_predicate ON semantic_nodes(predicate);
CREATE INDEX IF NOT EXISTS idx_semantic_confidence ON semantic_nodes(confidence DESC);

-- AutobiographicalMemory（自传层）
CREATE TABLE IF NOT EXISTS autobiographical_nodes (
    node_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    layer TEXT NOT NULL CHECK(layer IN ('identity', 'values', 'long_term_goals', 'core_beliefs')),
    content TEXT NOT NULL,
    stability_score REAL DEFAULT 0.8 CHECK(stability_score BETWEEN 0 AND 1),
    version INTEGER DEFAULT 1,
    previous_version_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_auto_layer ON autobiographical_nodes(layer);
CREATE INDEX IF NOT EXISTS idx_auto_stability ON autobiographical_nodes(stability_score DESC);

-- 版本快照表（自传层历史）
CREATE TABLE IF NOT EXISTS autobiographical_history (
    history_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    content TEXT NOT NULL,
    change_reason TEXT,
    FOREIGN KEY(node_id) REFERENCES autobiographical_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_hist_node ON autobiographical_history(node_id);

-- 元数据表（记录系统状态）
CREATE TABLE IF NOT EXISTS pmn_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);

INSERT OR IGNORE INTO pmn_meta (key, value, updated_at) 
VALUES ('schema_version', '2.0', CAST(strftime('%s', 'now') AS REAL));
