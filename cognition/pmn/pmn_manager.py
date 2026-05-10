"""
PMNManager - 人格记忆网络核心管理器 v2.0

职责：
- 管理三层记忆：EpisodicMemory / SemanticMemory / AutobiographicalMemory
- SQLite原子操作 + WAL模式
- 敏感数据隔离存储
- 版本控制与回滚

作者：虾虾
日期：2026-04-30
"""

import os
import time
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

from sanitizer import ContextSanitizer

# 导入冲突检测器
try:
    from conflict_detector import ConflictDetector
    CONFLICT_AVAILABLE = True
except ImportError:
    CONFLICT_AVAILABLE = False
    ConflictDetector = None


@dataclass
class EpisodicMemoryNode:
    node_id: str
    timestamp: float
    event_type: str
    content: str
    raw_context_hash: Optional[str] = None
    emotional_valence: float = 0.0
    emotional_arousal: float = 0.0
    importance_score: float = 0.5
    related_semantic_ids: List[str] = field(default_factory=list)


@dataclass
class SemanticMemoryNode:
    node_id: str
    created_at: float
    updated_at: float
    category: str
    subject: str
    predicate: str
    object: Optional[str] = None
    confidence: float = 0.5
    evidence_count: int = 1
    source_episode_ids: List[str] = field(default_factory=list)


@dataclass
class AutobiographicalMemoryNode:
    node_id: str
    created_at: float
    updated_at: float
    layer: str
    content: str
    stability_score: float = 0.8
    version: int = 1
    previous_version_id: Optional[str] = None


# 受控谓词词表
VALID_PREDICATES = {
    "belief": ["thinks", "believes", "knows", "doubts", "fails_at", "improving_in"],
    "preference": ["likes", "dislikes", "prefers", "avoids", "enjoys"],
    "knowledge": ["knows", "understands", "has_skill_in", "learned"],
    "skill": ["excels_in", "fails_at", "improving_in", "mastered"]
}


class PMNManager:
    """
    人格记忆网络管理器
    
    核心方法：
    - record_event(): 原子性记录事件到三层记忆
    - recall_context(): 检索记忆
    - get_personality_snapshot(): 获取人格快照（供BDI使用）
    - rollback_autobiographical(): 回滚自传层
    """
    
    def __init__(self, 
                 db_path: Optional[str] = None,
                 sensitive_dir: Optional[str] = None,
                 enable_faiss: bool = False):
        
        # 配置路径
        if db_path is None:
            db_path = os.environ.get(
                "PMN_DB_PATH",
                "/root/.openclaw/workspace/agent/memory/pmn/pmn.db"
            )
        if sensitive_dir is None:
            sensitive_dir = os.environ.get(
                "PMN_SENSITIVE_DIR",
                "/root/.openclaw/workspace/agent/memory/pmn/sensitive/raw_contexts"
            )
        
        self.db_path = Path(db_path)
        self.sensitive_dir = Path(sensitive_dir)
        self.enable_faiss = enable_faiss
        
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sensitive_dir.mkdir(parents=True, exist_ok=True)
        
        # 数据库连接（每个线程一个）
        self._local = threading.local()
        
        # 初始化冲突检测器
        self.conflict_detector = None
        if CONFLICT_AVAILABLE:
            try:
                self.conflict_detector = ConflictDetector()
            except Exception as e:
                pass
        
        # 初始化数据库
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row  # 启用行工厂
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn
    
    def _init_db(self) -> None:
        """初始化数据库表结构"""
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                schema = f.read()
            conn = self._get_conn()
            conn.executescript(schema)
            conn.commit()
    
    def record_event(self, event: Dict) -> str:
        """
        原子性记录事件到三层记忆
        
        事务保证：任一失败全部回滚
        
        Args:
            event: {
                "timestamp": float,
                "event_type": str,
                "raw_context": Dict,
                "importance_score": float (可选),
            }
        
        Returns:
            episodic_node_id
        """
        conn = self._get_conn()
        episodic_id = None
        
        try:
            # SQLite自动事务管理（WAL模式下）
            # 移除显式BEGIN，使用SAVEPOINT替代
            # 1. 清洗和存储敏感数据
            raw_context = event.get("raw_context", {})
            safe_summary, sensitive_fields, is_safe = ContextSanitizer.sanitize(raw_context)
            
            # 存储敏感数据到隔离区
            context_hash = None
            if sensitive_fields:
                context_hash = ContextSanitizer.generate_hash(raw_context)
                self._store_sensitive(context_hash, sensitive_fields)
            
            # 2. 写入 EpisodicMemory
            episodic_id = self._insert_episodic(
                timestamp=event.get("timestamp", time.time()),
                event_type=event.get("event_type", "unknown"),
                content=safe_summary,
                raw_context_hash=context_hash,
                importance_score=event.get("importance_score", 0.5),
            )
            
            # 3. 提取语义并写入 SemanticMemory
            semantic_nodes = self._extract_semantic(
                episodic_id,
                event.get("event_type", ""),
                safe_summary,
                event.get("emotional_valence", 0),
                event.get("emotional_arousal", 0),
            )
            
            related_semantic_ids = []
            for node in semantic_nodes:
                sid = self._insert_semantic(node)
                related_semantic_ids.append(sid)
            
            # 更新 episodic 的 related_semantic_ids
            if related_semantic_ids:
                self._update_episodic_semantic_links(episodic_id, related_semantic_ids)
            
            # 4. 更新 AutobiographicalMemory（条件触发）
            self._update_autobiographical(semantic_nodes)
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            raise e
        
        return episodic_id
    
    def recall_context(self, query: str,
                     layer: str = "all",
                     limit: int = 10,
                     time_range: Optional[Tuple[float, float]] = None) -> List[Dict]:
        """
        检索记忆
        
        Args:
            query: 查询文本
            layer: all / episodic / semantic / autobiographical
            limit: 返回数量
            time_range: (start, end) 时间过滤
        """
        results = []
        
        if layer in ("all", "episodic"):
            results.extend(self._recall_episodic(query, limit, time_range))
        
        if layer in ("all", "semantic"):
            results.extend(self._recall_semantic(query, limit))
        
        if layer in ("all", "autobiographical"):
            results.extend(self._recall_autobiographical(query, limit))
        
        # 按时间排序
        results.sort(key=lambda x: x.get("timestamp", x.get("created_at", 0)), reverse=True)
        return results[:limit]
    
    def get_personality_snapshot(self) -> Dict:
        """
        获取人格快照（供BDI决策引擎使用）
        
        Returns:
            {
                "beliefs": [...],
                "preferences": [...],
                "identity": [...],
                "values": [...],
                "recent_episodes": [...],
            }
        """
        conn = self._get_conn()
        snapshot = {
            "beliefs": [],
            "preferences": [],
            "identity": [],
            "values": [],
            "recent_episodes": [],
        }
        
        # 高置信度信念
        cursor = conn.execute(
            "SELECT * FROM semantic_nodes WHERE category='belief' AND confidence > 0.6 ORDER BY confidence DESC LIMIT 10"
        )
        snapshot["beliefs"] = [self._row_to_dict(row) for row in cursor.fetchall()]
        
        # 用户偏好
        cursor = conn.execute(
            "SELECT * FROM semantic_nodes WHERE category='preference' ORDER BY evidence_count DESC LIMIT 10"
        )
        snapshot["preferences"] = [self._row_to_dict(row) for row in cursor.fetchall()]
        
        # 身份定义
        cursor = conn.execute(
            "SELECT * FROM autobiographical_nodes WHERE layer='identity' ORDER BY stability_score DESC LIMIT 5"
        )
        snapshot["identity"] = [self._row_to_dict(row) for row in cursor.fetchall()]
        
        # 价值观
        cursor = conn.execute(
            "SELECT * FROM autobiographical_nodes WHERE layer='values' ORDER BY stability_score DESC LIMIT 5"
        )
        snapshot["values"] = [self._row_to_dict(row) for row in cursor.fetchall()]
        
        # 最近情景
        cursor = conn.execute(
            "SELECT * FROM episodic_nodes ORDER BY timestamp DESC LIMIT 10"
        )
        snapshot["recent_episodes"] = [self._row_to_dict(row) for row in cursor.fetchall()]
        
        return snapshot
    
    def rollback_autobiographical(self, node_id: str, to_version: Optional[int] = None) -> bool:
        """
        回滚自传层节点到指定版本
        
        Args:
            node_id: 节点ID
            to_version: 目标版本（None=上一版本）
        
        Returns:
            是否成功
        """
        conn = self._get_conn()
        
        try:
            conn.execute("BEGIN")
            
            # 获取当前版本
            cursor = conn.execute(
                "SELECT version FROM autobiographical_nodes WHERE node_id=?",
                (node_id,)
            )
            current = cursor.fetchone()
            if not current:
                conn.rollback()
                return False
            
            current_version = current[0]
            target_version = to_version if to_version else current_version - 1
            
            if target_version < 1:
                conn.rollback()
                return False
            
            # 获取历史版本
            cursor = conn.execute(
                "SELECT content FROM autobiographical_history WHERE node_id=? AND version=?",
                (node_id, target_version)
            )
            hist = cursor.fetchone()
            if not hist:
                conn.rollback()
                return False
            
            # 更新当前节点
            conn.execute(
                """UPDATE autobiographical_nodes 
                   SET content=?, version=?, updated_at=?, previous_version_id=?
                   WHERE node_id=?""",
                (hist[0], target_version, time.time(), None, node_id)
            )
            
            conn.commit()
            return True
            
        except Exception:
            conn.rollback()
            return False
    
    def migrate_from_journal(self, journal_path: str) -> Dict:
        """
        从 personality_journal.jsonl 迁移数据
        
        修正后的映射逻辑（MiMo审查后）：
        - "user_preference" → SemanticMemory (category="preference")
        - "execution_error" → SemanticMemory (category="belief", subject="self")
        - "negative_reflection" → 仅累积3次以上才写入 AutobiographicalMemory (layer="values")
        """
        journal_file = Path(journal_path)
        if not journal_file.exists():
            return {"status": "error", "reason": "journal file not found"}
        
        migrated = {"episodic": 0, "semantic": 0, "autobiographical": 0, "errors": 0}
        
        # 统计 negative_reflection 累积
        reflection_counts = {}
        
        with open(journal_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    event_type = entry.get("event_type", "")
                    
                    if event_type in ("preference_detected", "user_preference"):
                        # → SemanticMemory (preference)
                        node = SemanticMemoryNode(
                            node_id=str(uuid.uuid4())[:8],
                            created_at=entry.get("timestamp", time.time()),
                            updated_at=time.time(),
                            category="preference",
                            subject="user_pengpeng",
                            predicate="prefers",
                            object=entry.get("content", "")[:100],
                            confidence=0.6,
                            evidence_count=1,
                        )
                        self._insert_semantic(node)
                        migrated["semantic"] += 1
                    
                    elif event_type in ("error", "execution_error"):
                        # → SemanticMemory (belief about self)
                        node = SemanticMemoryNode(
                            node_id=str(uuid.uuid4())[:8],
                            created_at=entry.get("timestamp", time.time()),
                            updated_at=time.time(),
                            category="belief",
                            subject="self",
                            predicate="fails_at",
                            object=entry.get("content", "")[:100],
                            confidence=0.5,
                            evidence_count=1,
                        )
                        self._insert_semantic(node)
                        migrated["semantic"] += 1
                    
                    elif event_type == "negative_reflection":
                        # 累积计数
                        key = entry.get("content", "")[:50]
                        reflection_counts[key] = reflection_counts.get(key, 0) + 1
                        
                        # 仅3次以上写入自传层
                        if reflection_counts[key] >= 3:
                            node = AutobiographicalMemoryNode(
                                node_id=str(uuid.uuid4())[:8],
                                created_at=time.time(),
                                updated_at=time.time(),
                                layer="values",
                                content=f"需要注意改进: {key}",
                                stability_score=0.7,
                            )
                            self._insert_autobiographical(node)
                            migrated["autobiographical"] += 1
                    
                except Exception:
                    migrated["errors"] += 1
        
        return migrated
    
    # ============ 私有方法 ============
    
    def _store_sensitive(self, hash_id: str, sensitive_fields: Dict) -> None:
        """存储敏感数据到隔离区"""
        date_dir = self.sensitive_dir / time.strftime("%Y-%m-%d")
        date_dir.mkdir(exist_ok=True)
        
        file_path = date_dir / f"{hash_id}.json"
        with open(file_path, 'w') as f:
            json.dump(sensitive_fields, f)
        
        # 设置权限 600
        os.chmod(file_path, 0o600)
    
    def _insert_episodic(self, **kwargs) -> str:
        """插入情景记忆节点"""
        node_id = str(uuid.uuid4())[:8]
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO episodic_nodes 
               (node_id, timestamp, event_type, content, raw_context_hash,
                emotional_valence, emotional_arousal, importance_score, related_semantic_ids)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (node_id, kwargs["timestamp"], kwargs["event_type"], kwargs["content"],
             kwargs.get("raw_context_hash"), kwargs.get("emotional_valence", 0),
             kwargs.get("emotional_arousal", 0), kwargs.get("importance_score", 0.5),
             json.dumps([]))
        )
        return node_id
    
    def _update_episodic_semantic_links(self, episodic_id: str, semantic_ids: List[str]) -> None:
        """更新情景记忆的语义关联"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE episodic_nodes SET related_semantic_ids=? WHERE node_id=?",
            (json.dumps(semantic_ids), episodic_id)
        )
    
    def _insert_semantic(self, node: SemanticMemoryNode) -> str:
        """插入语义记忆节点（存在则更新置信度）"""
        conn = self._get_conn()
        
        # 检查是否已存在相同 subject+predicate+object
        cursor = conn.execute(
            "SELECT node_id, confidence, evidence_count FROM semantic_nodes WHERE subject=? AND predicate=? AND object=?",
            (node.subject, node.predicate, node.object)
        )
        existing = cursor.fetchone()
        
        if existing:
            # 更新现有节点
            node_id, old_conf, old_count = existing
            new_conf = min(1.0, (old_conf * old_count + node.confidence) / (old_count + 1))
            new_count = old_count + 1
            
            conn.execute(
                """UPDATE semantic_nodes 
                   SET confidence=?, evidence_count=?, updated_at=?,
                       source_episode_ids=?
                   WHERE node_id=?""",
                (new_conf, new_count, time.time(),
                 json.dumps(node.source_episode_ids + [node_id]), node_id)
            )
            # v3.3: 冲突检测（后置钩子）
            if self.conflict_detector:
                try:
                    self._check_conflicts(node)
                except Exception:
                    pass  # 冲突检测失败不阻塞主流程
            return node_id
        else:
            # 插入新节点
            conn.execute(
                """INSERT INTO semantic_nodes
                   (node_id, created_at, updated_at, category, subject, predicate,
                    object, confidence, evidence_count, source_episode_ids)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (node.node_id, node.created_at, node.updated_at, node.category,
                 node.subject, node.predicate, node.object, node.confidence,
                 node.evidence_count, json.dumps(node.source_episode_ids))
            )
            # v3.3: 冲突检测（后置钩子）
            if self.conflict_detector:
                try:
                    self._check_conflicts(node)
                except Exception:
                    pass  # 冲突检测失败不阻塞主流程
            return node.node_id
    
    def _check_conflicts(self, new_node: SemanticMemoryNode) -> None:
        """
        检查新语义节点与现有节点的冲突
        """
        conn = self._get_conn()
        
        # 获取同一 subject 的现有节点
        cursor = conn.execute(
            """SELECT node_id, created_at, updated_at, category, subject, predicate,
                      object, confidence, evidence_count
               FROM semantic_nodes
               WHERE subject=? AND category=? AND node_id != ?
               ORDER BY created_at DESC LIMIT 10""",
            (new_node.subject, new_node.category, new_node.node_id)
        )
        
        existing = []
        for row in cursor.fetchall():
            existing.append({
                "node_id": row[0], "created_at": row[1], "updated_at": row[2],
                "category": row[3], "subject": row[4], "predicate": row[5],
                "object": row[6], "confidence": row[7], "evidence_count": row[8],
            })
        
        if not existing:
            return
        
        # 转换新节点为 dict
        new_dict = {
            "node_id": new_node.node_id, "created_at": new_node.created_at,
            "category": new_node.category, "subject": new_node.subject,
            "predicate": new_node.predicate, "object": new_node.object,
            "confidence": new_node.confidence,
        }
        
        # 运行冲突检测
        conflicts = self.conflict_detector.detect_conflicts(new_dict, existing)
        
        if conflicts:
            # 记录冲突日志（不写数据库列，避免schema变更）
            conflict_log = Path("/root/.openclaw/workspace/agent/logs/pmn_conflicts.jsonl")
            conflict_log.parent.mkdir(parents=True, exist_ok=True)
            with open(conflict_log, "a") as f:
                for c in conflicts:
                    f.write(json.dumps({
                        "timestamp": time.time(),
                        "node_a": c.node_a_id,
                        "node_b": c.node_b_id,
                        "type": c.conflict_type,
                        "score": c.conflict_score,
                        "reason": c.reason,
                    }, ensure_ascii=False) + "\n")
            
            print(f"[ConflictDetector] ⚠️ 检测到 {len(conflicts)} 个冲突！已记录到日志。")
    
    def _insert_autobiographical(self, node: AutobiographicalMemoryNode) -> str:
        """插入自传记忆节点"""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO autobiographical_nodes
               (node_id, created_at, updated_at, layer, content, stability_score, version, previous_version_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (node.node_id, node.created_at, node.updated_at, node.layer,
             node.content, node.stability_score, node.version, node.previous_version_id)
        )
        return node.node_id
    
    def _extract_semantic(self, episodic_id: str, event_type: str, 
                          content: str, valence: float, arousal: float) -> List[SemanticMemoryNode]:
        """从情景记忆提取语义信息"""
        nodes = []
        now = time.time()
        
        if event_type == "user_preference" or "喜欢" in content or "偏好" in content:
            nodes.append(SemanticMemoryNode(
                node_id=str(uuid.uuid4())[:8],
                created_at=now, updated_at=now,
                category="preference", subject="user_pengpeng",
                predicate="prefers", object=content[:100],
                confidence=0.6, evidence_count=1,
                source_episode_ids=[episodic_id]
            ))
        
        if event_type == "execution_error" or "error" in content.lower():
            nodes.append(SemanticMemoryNode(
                node_id=str(uuid.uuid4())[:8],
                created_at=now, updated_at=now,
                category="belief", subject="self",
                predicate="fails_at", object=content[:100],
                confidence=0.5, evidence_count=1,
                source_episode_ids=[episodic_id]
            ))
        
        if valence < -0.3:  # 负面情绪
            nodes.append(SemanticMemoryNode(
                node_id=str(uuid.uuid4())[:8],
                created_at=now, updated_at=now,
                category="belief", subject="self",
                predicate="improving_in", object="情绪管理",
                confidence=0.4, evidence_count=1,
                source_episode_ids=[episodic_id]
            ))
        
        return nodes
    
    def _update_autobiographical(self, semantic_nodes: List[SemanticMemoryNode]) -> None:
        """条件更新自传层"""
        for node in semantic_nodes:
            # 条件：置信度 > 0.7 且 evidence_count >= 3
            if node.confidence > 0.7 and node.evidence_count >= 3:
                # 升级为自传层
                layer = "core_beliefs" if node.category == "belief" else "values"
                auto_node = AutobiographicalMemoryNode(
                    node_id=str(uuid.uuid4())[:8],
                    created_at=time.time(), updated_at=time.time(),
                    layer=layer, content=f"{node.subject} {node.predicate} {node.object}",
                    stability_score=0.8, version=1,
                )
                self._insert_autobiographical(auto_node)
    
    def _recall_episodic(self, query: str, limit: int, 
                        time_range: Optional[Tuple[float, float]]) -> List[Dict]:
        """检索情景记忆"""
        conn = self._get_conn()
        sql = "SELECT * FROM episodic_nodes WHERE content LIKE ?"
        params = [f"%{query}%"]
        
        if time_range:
            sql += " AND timestamp BETWEEN ? AND ?"
            params.extend(time_range)
        
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(sql, params)
        return [self._row_to_dict(row, cursor) for row in cursor.fetchall()]
    
    def _recall_semantic(self, query: str, limit: int) -> List[Dict]:
        """检索语义记忆"""
        conn = self._get_conn()
        cursor = conn.execute(
            """SELECT * FROM semantic_nodes 
               WHERE subject LIKE ? OR predicate LIKE ? OR object LIKE ?
               ORDER BY confidence DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit)
        )
        return [self._row_to_dict(row, cursor) for row in cursor.fetchall()]
    
    def _recall_autobiographical(self, query: str, limit: int) -> List[Dict]:
        """检索自传记忆"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM autobiographical_nodes WHERE content LIKE ? ORDER BY stability_score DESC LIMIT ?",
            (f"%{query}%", limit)
        )
        return [self._row_to_dict(row, cursor) for row in cursor.fetchall()]
    
    @staticmethod
    def _row_to_dict(row, cursor=None) -> Dict:
        """SQLite行转字典"""
        if cursor is not None:
            return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
        # 如果没有cursor，手动构建（fallback）
        if hasattr(row, 'keys'):
            return {key: row[key] for key in row.keys()}
        return {f"col_{i}": val for i, val in enumerate(row)}


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== PMNManager Test ===")
    
    # 创建测试实例（使用临时数据库）
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    pmn = PMNManager(db_path=db_path, sensitive_dir="/tmp/pmn_test_sensitive")
    
    # 测试1：记录事件
    event1 = {
        "timestamp": time.time(),
        "event_type": "preference_detected",  # 使用有效的event_type
        "raw_context": {"message": "我喜欢简洁的回答", "user_id": "pengpeng"},
        "importance_score": 0.8,
    }
    eid1 = pmn.record_event(event1)
    print(f"Test1: Recorded event, id={eid1}")
    
    # 测试2：记录错误事件
    event2 = {
        "timestamp": time.time(),
        "event_type": "error",  # 使用有效的event_type
        "raw_context": {"error": "tool failed", "tool": "search"},
        "importance_score": 0.7,
    }
    eid2 = pmn.record_event(event2)
    print(f"Test2: Recorded error event, id={eid2}")
    
    # 测试3：人格快照
    snapshot = pmn.get_personality_snapshot()
    print(f"Test3: Snapshot keys={list(snapshot.keys())}")
    print(f"  preferences={len(snapshot['preferences'])}")
    print(f"  beliefs={len(snapshot['beliefs'])}")
    
    # 测试4：检索
    results = pmn.recall_context("简洁", layer="semantic", limit=5)
    print(f"Test4: Recall '简洁' -> {len(results)} results")
    
    # 测试5：迁移
    # 先创建一个测试 journal
    with open("/tmp/test_journal.jsonl", "w") as f:
        f.write(json.dumps({"timestamp": time.time(), "event_type": "preference_detected", "content": "我喜欢蓝色"}) + "\n")
        f.write(json.dumps({"timestamp": time.time(), "event_type": "error", "content": "文件读取失败"}) + "\n")
    
    migrated = pmn.migrate_from_journal("/tmp/test_journal.jsonl")
    print(f"Test5: Migrated {migrated}")
    
    # 测试6：重复写入同一偏好（置信度更新）
    for _ in range(3):
        event3 = {
            "timestamp": time.time(),
            "event_type": "preference_detected",
            "raw_context": {"message": "我喜欢简洁的回答", "user_id": "pengpeng"},
        }
        pmn.record_event(event3)
    
    # 检查置信度
    conn = pmn._get_conn()
    cursor = conn.execute("SELECT confidence, evidence_count FROM semantic_nodes WHERE predicate='prefers'")
    for row in cursor.fetchall():
        print(f"Test6: confidence={row[0]:.2f}, evidence={row[1]}")
    
    # 测试7：冲突检测（本地过滤验证）
    if pmn.conflict_detector:
        print("Test7: ConflictDetector available")
        new_node = {"node_id": "test_n1", "subject": "self", "predicate": "prefers", "object": "简洁", "category": "preference", "created_at": time.time()}
        existing = [
            {"node_id": "test_n2", "subject": "self", "predicate": "prefers", "object": "详细", "category": "preference", "created_at": time.time() - 100},
        ]
        overlap = pmn.conflict_detector._filter_temporal_overlap(new_node, existing)
        filtered = pmn.conflict_detector._local_filter(new_node, overlap)
        print(f"  Conflict candidates: {len(filtered)}")
        if filtered:
            print(f"  -> Potential conflict: prefers 简洁 vs prefers 详细")
    else:
        print("Test7: ConflictDetector not available (no MiMo key)")
    
    # 清理
    os.unlink(db_path)
    import shutil
    shutil.rmtree("/tmp/pmn_test_sensitive", ignore_errors=True)
    
    print("\n✅ PMNManager v2.0 + ConflictDetector ready")
