"""
LLM 精分析模块（P1阶段实现）

功能：
- 对模糊消息进行主题/情绪精分析
- 生成 llm_insight（一天的洞察）
- 识别隐式待办
"""

from typing import Dict
from digest.models import DailyDigest


def analyze_ambiguous_message(content: str) -> Dict:
    """对规则无法明确判断的消息进行LLM分析"""
    # P0 返回空，P1 实现
    return {"topic": None, "emotion": None, "confidence": 0}


def generate_llm_insight(digest: DailyDigest) -> str:
    """生成LLM洞察（虾虾视角）"""
    # P0 返回空字符串，P1 实现
    return ""
