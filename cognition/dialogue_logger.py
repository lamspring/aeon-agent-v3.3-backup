#!/usr/bin/env python3
"""
DialogueLogger - Aeon 对话记录器 v1.0

轻量级对话桥接：将 OpenClaw 会话消息追加写入 Aeon memory 文件。

设计原则:
- 不碰 EventBus（已有积压46条）
- 不碰 Gateway API（无端点）
- 只写文件，Aeon 每日总结自然读取
- 每轮对话只写一次，不频刷

记录格式:
    ## 对话片段 [HH:MM]
    **朋朋:** [消息摘要]
    **虾虾:** [回复摘要]

版本: v1.0
作者: 虾虾
日期: 2026-04-29
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict


class DialogueLogger:
    """
    对话记录器
    
    每次对话回合调用一次 log_exchange()，追加写入当天 memory 文件。
    """
    
    MEMORY_DIR = "/root/.openclaw/workspace/memory"
    MAX_MSG_LENGTH = 500  # 单条消息最大记录长度，超限截断
    
    def __init__(self, memory_dir: Optional[str] = None):
        self.memory_dir = Path(memory_dir or self.MEMORY_DIR)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._today_file = self._get_today_file()
        self._last_log_time = 0
    
    def _get_today_file(self) -> Path:
        """获取今天的 memory 文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.memory_dir / f"{today}.md"
    
    def _ensure_header(self):
        """确保文件有对话记录头部"""
        if not self._today_file.exists():
            with open(self._today_file, 'w', encoding='utf-8') as f:
                f.write(f"# {datetime.now().strftime('%Y年%m月%d日')} 对话记录\n\n")
                f.write(f"> 自动生成于 Aeon DialogueLogger v1.0\n")
                f.write(f"> 来源: OpenClaw session → Aeon memory bridge\n\n")
            return
        
        # 检查是否已有对话记录头部
        content = self._today_file.read_text(encoding='utf-8', errors='ignore')
        if "对话记录" not in content[:200]:
            with open(self._today_file, 'a', encoding='utf-8') as f:
                f.write(f"\n\n---\n\n")
                f.write(f"# 对话记录\n\n")
    
    def _truncate(self, text: str, max_len: int = None) -> str:
        """截断长文本"""
        max_len = max_len or self.MAX_MSG_LENGTH
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"\n...[截断，原长{len(text)}字]"
    
    def log_exchange(self, user_msg: str, assistant_reply: str, 
                     user_time: Optional[str] = None,
                     assistant_time: Optional[str] = None,
                     context: Optional[Dict] = None) -> bool:
        """
        记录一轮对话交换
        
        Args:
            user_msg: 用户消息内容
            assistant_reply: 助手回复内容
            user_time: 用户消息时间 (HH:MM 格式，默认当前时间)
            assistant_time: 助手回复时间 (HH:MM 格式，默认当前时间)
            context: 额外上下文（如工具调用、文件操作等）
        
        Returns:
            bool: 是否成功写入
        """
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        
        user_time = user_time or time_str
        assistant_time = assistant_time or time_str
        
        # 构建记录块
        lines = [
            f"\n## 对话片段 [{user_time}]\n",
            f"**朋朋:** {self._truncate(user_msg)}\n",
            f"**虾虾:** {self._truncate(assistant_reply)}\n",
        ]
        
        # 如果有上下文，记录操作摘要
        if context:
            ops = context.get('operations', [])
            if ops:
                lines.append("**操作:**\n")
                for op in ops[:5]:  # 最多记录5个操作
                    lines.append(f"- {op}\n")
        
        # 写入文件
        try:
            self._ensure_header()
            with open(self._today_file, 'a', encoding='utf-8') as f:
                f.writelines(lines)
            
            self._last_log_time = now.timestamp()
            return True
            
        except Exception as e:
            # 静默失败，不打扰对话
            print(f"[DialogueLogger] Write failed: {e}")
            return False
    
    def log_simple(self, role: str, content: str, 
                   note: Optional[str] = None) -> bool:
        """
        记录单条消息（用于系统通知、心跳等）
        
        Args:
            role: 角色名（如 "系统", "Aeon", "虾虾"）
            content: 内容
            note: 备注
        """
        time_str = datetime.now().strftime("%H:%M")
        
        lines = [
            f"\n## 记录 [{time_str}]\n",
            f"**{role}:** {self._truncate(content)}\n",
        ]
        if note:
            lines.append(f"_注: {note}_\n")
        
        try:
            self._ensure_header()
            with open(self._today_file, 'a', encoding='utf-8') as f:
                f.writelines(lines)
            return True
        except Exception as e:
            print(f"[DialogueLogger] Write failed: {e}")
            return False
    
    def get_stats(self) -> Dict:
        """获取记录统计"""
        return {
            "today_file": str(self._today_file),
            "file_exists": self._today_file.exists(),
            "file_size": self._today_file.stat().st_size if self._today_file.exists() else 0,
            "last_log_time": datetime.fromtimestamp(self._last_log_time).strftime('%H:%M:%S') if self._last_log_time else None,
        }


# ============== 快速测试 ==============
if __name__ == "__main__":
    logger = DialogueLogger()
    
    print(f"=== DialogueLogger v1.0 ===")
    print(f"Target: {logger._today_file}")
    print(f"Stats: {logger.get_stats()}")
    
    # 测试记录
    # result = logger.log_exchange(
    #     user_msg="测试消息",
    #     assistant_reply="收到测试",
    #     context={"operations": ["写入测试"]}
    # )
    # print(f"Log result: {result}")
    # print(f"Stats after: {logger.get_stats()}")
