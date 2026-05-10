#!/usr/bin/env python3
"""
DialogueReader - Aeon 对话感知器 v1.0

轻量级读取 OpenClaw 对话日志，提取最近话题和关键词。
供 Aeon Observe 阶段调用，不增加 EventBus 负担。

读取策略:
- 只读当天 memory 文件的最后 N 行
- 每 tick 读取一次（30秒），但只记录变化
- 输出: 最近话题列表、用户关心关键词

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class DialogueReader:
    """
    对话感知器
    
    职责:
    - 读取当天对话记录
    - 提取最近 N 轮话题
    - 识别用户高频关键词
    - 输出结构化摘要供 Aeon 消费
    """
    
    MEMORY_DIR = "/root/.openclaw/workspace/memory"
    
    def __init__(self, memory_dir: Optional[str] = None):
        self.memory_dir = Path(memory_dir or self.MEMORY_DIR)
        self._last_read_size = 0
        self._cached_topics = []
    
    def read_recent(self, max_lines: int = 100, max_exchanges: int = 5) -> Dict:
        """
        读取最近对话
        
        Args:
            max_lines: 读取文件最后多少行
            max_exchanges: 返回最近多少轮对话
        
        Returns:
            {
                "has_new_content": bool,
                "recent_exchanges": [
                    {"time": "HH:MM", "user_topic": "...", "assistant_action": "..."}
                ],
                "keywords": [str],
                "user_mood_hint": str,
            }
        """
        today_file = self._get_today_file()
        if not today_file.exists():
            return {"has_new_content": False, "recent_exchanges": [], "keywords": []}
        
        current_size = today_file.stat().st_size
        
        # 读取新增内容
        if current_size > self._last_read_size:
            new_content = self._read_new_content(today_file, self._last_read_size)
            self._last_read_size = current_size
        else:
            # 没有新内容，返回缓存
            return {
                "has_new_content": False,
                "recent_exchanges": self._cached_topics[-max_exchanges:],
                "keywords": self._extract_keywords(self._cached_topics),
            }
        
        # 解析对话片段
        exchanges = self._parse_exchanges(new_content)
        self._cached_topics.extend(exchanges)
        
        # 只保留最近 max_exchanges
        recent = self._cached_topics[-max_exchanges:]
        
        return {
            "has_new_content": True,
            "recent_exchanges": recent,
            "keywords": self._extract_keywords(recent),
            "user_mood_hint": self._guess_mood(recent),
        }
    
    def _get_today_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.memory_dir / f"{today}.md"
    
    def _read_new_content(self, file_path: Path, last_pos: int) -> str:
        """读取文件新增部分"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(last_pos)
            return f.read()
    
    def _parse_exchanges(self, content: str) -> List[Dict]:
        """解析对话片段"""
        exchanges = []
        
        # 按 "## 对话片段" 分割
        blocks = re.split(r'\n## 对话片段 \[(\d{2}:\d{2})\]\n', content)
        
        for i in range(1, len(blocks), 2):
            if i+1 >= len(blocks):
                break
            time_str = blocks[i]
            block = blocks[i+1]
            
            # 提取用户消息（朋朋）
            user_match = re.search(r'\*\*朋朋:\*\* (.+?)(?=\n\*\*虾虾|\Z)', block, re.DOTALL)
            user_msg = user_match.group(1).strip() if user_match else ""
            
            # 提取助手回复（虾虾）
            assistant_match = re.search(r'\*\*虾虾:\*\* (.+?)(?=\n\*\*操作|\Z)', block, re.DOTALL)
            assistant_msg = assistant_match.group(1).strip() if assistant_match else ""
            
            # 提取操作
            ops_match = re.search(r'\*\*操作:\*\*\n((?:- .+\n)+)', block)
            operations = []
            if ops_match:
                ops_text = ops_match.group(1)
                operations = [line.strip('- \n') for line in ops_text.split('\n') if line.strip()]
            
            if user_msg or assistant_msg:
                exchanges.append({
                    "time": time_str,
                    "user_topic": user_msg[:100] + "..." if len(user_msg) > 100 else user_msg,
                    "assistant_action": assistant_msg[:100] + "..." if len(assistant_msg) > 100 else assistant_msg,
                    "operations": operations,
                })
        
        return exchanges
    
    def _extract_keywords(self, exchanges: List[Dict]) -> List[str]:
        """提取关键词"""
        text = " ".join(e["user_topic"] for e in exchanges)
        
        # 简单关键词提取：找2-4字的实体词
        keywords = []
        
        # 技术/产品名词
        tech_terms = ["小米", "Aeon", "OpenClaw", "Kimi", "MiMo", "DeepSeek", 
                      "股票", "股价", "小说", "写手", "扮演度", "Gateway",
                      "工具", "API", "模型", "k2.6", "Token", "微信"]
        for term in tech_terms:
            if term in text:
                keywords.append(term)
        
        # 去重并限制数量
        seen = set()
        unique = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                unique.append(k)
                if len(unique) >= 8:
                    break
        
        return unique
    
    def inject_context(self, result: Dict) -> bool:
        """
        将对话感知结果写入上下文提示文件
        供虾虾读取使用
        """
        try:
            from context_injector import ContextInjector
            
            keywords = result.get("keywords", [])
            mood = result.get("user_mood_hint", "neutral")
            exchanges = result.get("recent_exchanges", [])
            
            if not keywords and not exchanges:
                return False
            
            # 构建提示文本
            if exchanges:
                last_topic = exchanges[-1].get("user_topic", "")[:60]
                hint = f"用户最近关心: {', '.join(keywords[:3])}。最新话题: {last_topic}"
            else:
                hint = f"用户最近关心: {', '.join(keywords[:3])}"
            
            injector = ContextInjector()
            return injector.write_hint(
                hint=hint,
                topics=keywords,
                mood=mood,
                confidence=0.7 if keywords else 0.3,
                metadata={
                    "exchange_count": len(exchanges),
                    "source": "DialogueReader"
                }
            )
        except Exception as e:
            print(f"[DialogueReader] Context injection failed: {e}")
            return False
    
    def _guess_mood(self, exchanges: List[Dict]) -> str:
        """猜测用户情绪倾向"""
        if not exchanges:
            return "unknown"
        
        last_user = exchanges[-1]["user_topic"].lower()
        
        # 简单规则
        if any(w in last_user for w in ["谢谢", "棒", "好", "ok"]):
            return "positive"
        elif any(w in last_user for w in [" bug", "问题", "错误", "失败", "慢", "卡"]):
            return "frustrated"
        elif any(w in last_user for w in ["？", "?", "怎么", "为什么"]):
            return "curious"
        elif "继续" in last_user or "开始" in last_user:
            return "proactive"
        else:
            return "neutral"


# ============== 快速测试 ==============
if __name__ == "__main__":
    reader = DialogueReader()
    result = reader.read_recent()
    
    print("=== DialogueReader v1.0 - 测试 ===")
    print(f"has_new_content: {result['has_new_content']}")
    print(f"recent_exchanges: {len(result['recent_exchanges'])}")
    for ex in result['recent_exchanges']:
        print(f"  [{ex['time']}] 朋朋: {ex['user_topic'][:40]}...")
    print(f"keywords: {result['keywords']}")
    print(f"mood: {result['user_mood_hint']}")
