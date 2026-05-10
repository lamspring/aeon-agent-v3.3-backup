"""
ConflictDetector - PMN 冲突检测模块 v1.0

职责：
- 检测 SemanticMemory 中的语义冲突
- 支持时间维度（同一时期才冲突）
- 批量检测减少 API 调用
- 熔断机制：API 失败不阻塞写入

作者：虾虾
日期：2026-05-01
"""

import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ConflictResult:
    """冲突检测结果"""
    node_a_id: str
    node_b_id: str
    conflict_score: float  # 0-1
    conflict_type: str  # "compatible", "supersedes", "contradicts", "temporal"
    reason: str
    suggested_action: str  # "keep_both", "keep_higher_confidence", "flag_for_review"


class ConflictDetector:
    """
    冲突检测器
    
    设计原则（MiMo 审查后）：
    1. 放 PMNManager 内部使用（后置钩子）
    2. 同一 subject 的节点批量检测
    3. MiMo 失败时不阻塞主流程（熔断）
    4. 考虑时间维度（valid_from/valid_until）
    """
    
    def __init__(self, mimo_api_key: Optional[str] = None,
                 mimo_base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
                 max_daily_checks: int = 50):
        self.mimo_api_key = mimo_api_key
        self.mimo_base_url = mimo_base_url
        self.max_daily_checks = max_daily_checks
        
        # 熔断状态
        self._circuit_open = False
        self._circuit_open_time = 0
        self._circuit_reset_seconds = 300  # 5分钟后重试
        
        # 配额追踪
        self._today = time.strftime("%Y-%m-%d")
        self._checks_today = 0
    
    def _check_circuit(self) -> bool:
        """检查熔断状态"""
        if not self._circuit_open:
            return True
        
        if time.time() - self._circuit_open_time > self._circuit_reset_seconds:
            self._circuit_open = False
            return True
        
        return False
    
    def _open_circuit(self):
        """打开熔断"""
        self._circuit_open = True
        self._circuit_open_time = time.time()
    
    def _check_quota(self) -> bool:
        """检查日配额"""
        today = time.strftime("%Y-%m-%d")
        if today != self._today:
            self._today = today
            self._checks_today = 0
        
        return self._checks_today < self.max_daily_checks
    
    def detect_conflicts(self, new_node: Dict, existing_nodes: List[Dict]) -> List[ConflictResult]:
        """
        检测新节点与现有节点的冲突
        
        Args:
            new_node: 新插入的语义记忆节点
            existing_nodes: 同一 subject 的现有节点（已按时间过滤）
        
        Returns:
            冲突列表（空列表表示无冲突）
        """
        # 1. 熔断检查
        if not self._check_circuit():
            return []
        
        # 2. 配额检查
        if not self._check_quota():
            return []
        
        # 3. 时间过滤：只检查时间重叠的节点
        overlapping = self._filter_temporal_overlap(new_node, existing_nodes)
        if not overlapping:
            return []
        
        # 4. 本地规则快速过滤（减少 API 调用）
        candidates = self._local_filter(new_node, overlapping)
        if not candidates:
            return []
        
        # 5. MiMo 批量冲突检测
        try:
            conflicts = self._mimo_batch_check(new_node, candidates)
            self._checks_today += 1
            return conflicts
        except Exception as e:
            # API 失败 → 打开熔断
            self._open_circuit()
            return []
    
    def _filter_temporal_overlap(self, new_node: Dict, existing_nodes: List[Dict]) -> List[Dict]:
        """
        时间重叠过滤
        
        原则：如果两条记录的时间范围不重叠，则不是冲突
        （例："去年喜欢A" vs "今年喜欢B" 不是冲突）
        """
        new_start = new_node.get("created_at", 0)
        # 默认有效期：创建后7天（偏好/信念通常不会瞬间改变）
        new_end = new_node.get("valid_until", new_start + 7 * 86400)
        
        overlapping = []
        for node in existing_nodes:
            if node.get("node_id") == new_node.get("node_id"):
                continue
            
            old_start = node.get("created_at", 0)
            old_end = node.get("valid_until", old_start + 7 * 86400)
            
            # 检查时间重叠
            if new_start <= old_end and old_start <= new_end:
                overlapping.append(node)
        
        return overlapping
    
    def _local_filter(self, new_node: Dict, candidates: List[Dict]) -> List[Dict]:
        """
        本地规则快速过滤
        
        策略：
        - category 不同 → 不冲突（belief vs skill 不会冲突）
        - predicate 不同且非同义词 → 可能不冲突（likes vs knows）
        - object 完全相同 → 重复（不是冲突，是更新）
        """
        filtered = []
        new_pred = new_node.get("predicate", "")
        new_obj = new_node.get("object", "")
        new_cat = new_node.get("category", "")
        
        for node in candidates:
            # category 不同，不冲突
            if node.get("category") != new_cat:
                continue
            
            # object 完全相同 → 重复，不是冲突
            if node.get("object") == new_obj:
                continue
            
            # predicate 完全不同 → 大概率不冲突
            old_pred = node.get("predicate", "")
            if old_pred != new_pred:
                # 例外：likes/dislikes 是相反的
                opposite_pairs = [("likes", "dislikes"), ("prefers", "avoids")]
                if not any((old_pred == p[0] and new_pred == p[1]) or 
                          (old_pred == p[1] and new_pred == p[0]) for p in opposite_pairs):
                    continue
            
            filtered.append(node)
        
        return filtered
    
    def _mimo_batch_check(self, new_node: Dict, candidates: List[Dict]) -> List[ConflictResult]:
        """
        MiMo 批量冲突检测
        
        一次 API 调用检查所有候选节点
        """
        if not self.mimo_api_key:
            return []
        
        # 构建提示
        new_stmt = f"{new_node.get('subject', 'unknown')} {new_node.get('predicate', '')} {new_node.get('object', '')}"
        
        candidate_stmts = []
        for i, node in enumerate(candidates):
            stmt = f"{i+1}. {node.get('subject', '')} {node.get('predicate', '')} {node.get('object', '')}"
            candidate_stmts.append(stmt)
        
        prompt = f"""你是一位语义一致性检查专家。请分析以下陈述是否存在冲突。

新陈述：
{new_stmt}

现有陈述：
{chr(10).join(candidate_stmts)}

请逐条判断新陈述与每条现有陈述的关系：
1. compatible（兼容）— 可以同时成立
2. supersedes（取代）— 新陈述更精确/更新，应取代旧陈述
3. contradicts（矛盾）— 不可能同时成立
4. temporal（时间性）— 不同时间成立，不冲突

输出JSON数组：
[
  {{"index": 1, "relation": "compatible", "score": 0.1, "reason": "理由"}},
  ...
]

注意：
- score 是冲突强度，0=完全兼容，1=完全矛盾
- 只输出JSON，不要其他文字"""
        
        try:
            import urllib.request
            
            payload = {
                "model": "mimo-v2.5",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.3,
            }
            
            req = urllib.request.Request(
                f"{self.mimo_base_url}/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.mimo_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"]
                
                # 解析 JSON
                try:
                    results = json.loads(reply)
                except json.JSONDecodeError:
                    import re
                    match = re.search(r"\[.*\]", reply, re.DOTALL)
                    if match:
                        results = json.loads(match.group(0))
                    else:
                        return []
                
                # 构建 ConflictResult
                conflicts = []
                for r in results:
                    idx = r.get("index", 0) - 1
                    if 0 <= idx < len(candidates):
                        relation = r.get("relation", "compatible")
                        score = r.get("score", 0)
                        
                        if relation in ("contradicts", "supersedes") and score > 0.5:
                            action = "keep_higher_confidence" if relation == "supersedes" else "flag_for_review"
                            
                            conflicts.append(ConflictResult(
                                node_a_id=new_node.get("node_id", ""),
                                node_b_id=candidates[idx].get("node_id", ""),
                                conflict_score=score,
                                conflict_type=relation,
                                reason=r.get("reason", ""),
                                suggested_action=action,
                            ))
                
                return conflicts
                
        except Exception as e:
            raise e  # 让上层打开熔断
    
    def auto_resolve(self, conflicts: List[ConflictResult], 
                    node_a: Dict, node_b: Dict) -> str:
        """
        自动解决冲突
        
        策略：
        - supersedes → 保留置信度高的
        - contradicts → 标记待审（不自动删除）
        """
        if not conflicts:
            return "no_conflict"
        
        for conflict in conflicts:
            if conflict.conflict_type == "supersedes":
                # 保留置信度高的
                conf_a = node_a.get("confidence", 0.5)
                conf_b = node_b.get("confidence", 0.5)
                
                if conf_a > conf_b:
                    return f"keep_a:{conflict.node_a_id}"
                else:
                    return f"keep_b:{conflict.node_b_id}"
            
            elif conflict.conflict_type == "contradicts":
                # 矛盾：不自动解决，标记待审
                return f"flag_for_review:{conflict.node_b_id}"
        
        return "no_action"


# ============== 快速测试 ==============
if __name__ == "__main__":
    print("=== ConflictDetector v1.0 ===")
    
    cd = ConflictDetector()
    
    # 测试本地过滤
    new = {"node_id": "n1", "subject": "self", "predicate": "prefers", "object": "简洁", "category": "preference", "created_at": time.time()}
    existing = [
        {"node_id": "n2", "subject": "self", "predicate": "prefers", "object": "详细", "category": "preference", "created_at": time.time() - 100},
        {"node_id": "n3", "subject": "self", "predicate": "knows", "object": "Python", "category": "knowledge", "created_at": time.time() - 100},
    ]
    
    # 测试时间过滤
    overlap = cd._filter_temporal_overlap(new, existing)
    print(f"Temporal overlap: {len(overlap)} nodes")
    
    # 测试本地过滤
    filtered = cd._local_filter(new, overlap)
    print(f"After local filter: {len(filtered)} nodes")
    for n in filtered:
        print(f"  Candidate: {n['predicate']} {n['object']}")
    
    print("✅ ConflictDetector ready")
