#!/usr/bin/env python3
"""
Internalize Reflection - 自省内化器

将每次自省的结果保存到记忆目录，成为虾虾的长期记忆。
不推送，不打扰，只沉淀。

保存位置: /root/.openclaw/workspace/agent/memory/reflections/
文件格式: JSONL，每天一个文件
"""

import json
import os
from pathlib import Path
from datetime import datetime

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
REFLECTIONS_DIR = AGENT_DIR / "memory" / "reflections"

def ensure_dir():
    REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)

def save_reflection(tick_count, insights, actions, semantic, mood, auto_fixed=None):
    """
    保存一次自省到记忆
    
    auto_fixed: 如果有自愈动作，记录在这里
    """
    ensure_dir()
    
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    
    record = {
        "timestamp": now.isoformat(),
        "tick_count": tick_count,
        "insights": insights,
        "actions": actions,
        "semantic_analysis": semantic,
        "mood": mood,
        "auto_fixed": auto_fixed or [],  # 自愈记录
    }
    
    # 按天归档，JSONL 格式
    file_path = REFLECTIONS_DIR / f"{date_str}.jsonl"
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    
    return str(file_path)

def get_today_reflections():
    """获取今天的所有自省记录"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_path = REFLECTIONS_DIR / f"{date_str}.jsonl"
    
    if not file_path.exists():
        return []
    
    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except:
                    pass
    
    return records

def get_reflection_summary(hours=24):
    """生成指定时间范围内的自省摘要"""
    records = get_today_reflections()
    
    if not records:
        return "今天还没有自省记录。"
    
    # 统计
    total = len(records)
    with_semantic = sum(1 for r in records if r.get('semantic_analysis'))
    with_mood = sum(1 for r in records if r.get('mood'))
    auto_fixed = sum(len(r.get('auto_fixed', [])) for r in records)
    
    # 收集所有洞察
    all_insights = []
    for r in records:
        all_insights.extend(r.get('insights', []))
    
    # 去重
    unique_insights = list(set(all_insights))
    
    summary = f"""今日自省统计:
- 总次数: {total}
- 语义分析: {with_semantic} 次
- 情绪记录: {with_mood} 次
- 自愈动作: {auto_fixed} 次

关键洞察 ({len(unique_insights)} 条):
"""
    
    for i, insight in enumerate(unique_insights[:10], 1):
        summary += f"{i}. {insight}\n"
    
    if auto_fixed > 0:
        summary += f"\n自愈记录:\n"
        for r in records:
            for fix in r.get('auto_fixed', []):
                summary += f"- {fix}\n"
    
    return summary

if __name__ == '__main__':
    # 测试
    save_reflection(100, ["测试洞察"], [], True, "💬 互动型")
    print(get_reflection_summary())
