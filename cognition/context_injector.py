#!/usr/bin/env python3
"""
ContextInjector - Aeon → 虾虾 上下文注入器 v1.0

轻量级共享状态：Aeon 检测到用户话题时，写入提示文件。
虾虾每轮对话开始时读取，作为上下文补充。

文件位置: /tmp/aeon_context_hint.json
格式:
{
    "hint": "用户最近关心小米股价和MiMo开源",
    "topics": ["小米", "股价"],
    "mood": "proactive",
    "confidence": 0.8,
    "timestamp": "2026-04-29T13:51:00",
    "expires_at": "2026-04-29T14:21:00",
    "consumed": false
}

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


class ContextInjector:
    """
    上下文注入器
    
    职责:
    - Aeon 检测到话题时，写入提示
    - 虾虾读取提示，融入回复
    - 自动过期/清理
    """
    
    HINT_FILE = "/tmp/aeon_context_hint.json"
    DEFAULT_TTL_MINUTES = 30  # 提示默认存活30分钟
    
    def __init__(self, hint_file: Optional[str] = None, ttl_minutes: int = 30):
        self.hint_file = Path(hint_file or self.HINT_FILE)
        self.ttl_minutes = ttl_minutes
    
    def write_hint(self, hint: str, topics: List[str], mood: str = "neutral",
                   confidence: float = 0.5, metadata: Optional[Dict] = None) -> bool:
        """
        写入上下文提示（Aeon 调用）
        
        Args:
            hint: 提示文本（不超过100字）
            topics: 相关话题列表
            mood: 检测到的用户情绪
            confidence: 置信度 0-1
            metadata: 额外元数据
        """
        now = datetime.now()
        expires = now + timedelta(minutes=self.ttl_minutes)
        
        data = {
            "hint": hint[:100],
            "topics": topics[:5],
            "mood": mood,
            "confidence": min(max(confidence, 0.0), 1.0),
            "timestamp": now.isoformat(),
            "expires_at": expires.isoformat(),
            "consumed": False,
            "metadata": metadata or {},
        }
        
        try:
            with open(self.hint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[ContextInjector] Write failed: {e}")
            return False
    
    def read_hint(self, consume: bool = True) -> Optional[Dict]:
        """
        读取上下文提示（虾虾 调用）
        
        Args:
            consume: 读取后是否标记为已消费
        
        Returns:
            提示字典，或 None（无提示/已过期/已消费）
        """
        if not self.hint_file.exists():
            return None
        
        try:
            with open(self.hint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查是否已消费
            if data.get("consumed", False):
                return None
            
            # 检查是否过期
            expires_str = data.get("expires_at")
            if expires_str:
                expires = datetime.fromisoformat(expires_str)
                if datetime.now() > expires:
                    return None
            
            # 标记为已消费
            if consume:
                data["consumed"] = True
                with open(self.hint_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            
            return data
            
        except (json.JSONDecodeError, ValueError, FileNotFoundError):
            return None
        except Exception as e:
            print(f"[ContextInjector] Read failed: {e}")
            return None
    
    def peek_hint(self) -> Optional[Dict]:
        """只读不消费（用于检查是否有提示）"""
        return self.read_hint(consume=False)
    
    def clear(self) -> bool:
        """手动清除提示"""
        try:
            if self.hint_file.exists():
                self.hint_file.unlink()
            return True
        except Exception as e:
            print(f"[ContextInjector] Clear failed: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """获取提示统计"""
        hint = self.peek_hint()
        if not hint:
            return {"exists": False}
        
        expires = datetime.fromisoformat(hint["expires_at"]) if hint.get("expires_at") else None
        remaining = (expires - datetime.now()).total_seconds() if expires else 0
        
        return {
            "exists": True,
            "hint": hint.get("hint", ""),
            "topics": hint.get("topics", []),
            "mood": hint.get("mood", "unknown"),
            "confidence": hint.get("confidence", 0),
            "consumed": hint.get("consumed", False),
            "remaining_seconds": max(0, int(remaining)),
        }


# ============== 快速测试 ==============
if __name__ == "__main__":
    injector = ContextInjector()
    
    # 测试写入
    injector.write_hint(
        hint="用户最近关心小米股价和MiMo开源进展",
        topics=["小米", "股价", "MiMo"],
        mood="proactive",
        confidence=0.85
    )
    print("=== Written ===")
    print(json.dumps(injector.get_stats(), indent=2, ensure_ascii=False))
    
    # 测试读取
    hint = injector.read_hint()
    print("\n=== Read ===")
    print(json.dumps(hint, indent=2, ensure_ascii=False))
    
    # 测试再次读取（应该为 None，因为已消费）
    hint2 = injector.read_hint()
    print(f"\n=== Second read: {hint2} ===")
