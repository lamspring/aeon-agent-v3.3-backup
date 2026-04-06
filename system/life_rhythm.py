#!/usr/bin/env python3
"""
Life Rhythm - 生活节律系统 (Adapted for Server Restart)

考虑服务器每天4:00重启的生活节律：
  早晨 (6-12):  学习研究 📚
  下午 (12-18): 执行任务 ⚡
  晚上 (18-23): 反思总结 🌙
  深夜 (23-2):  轻度维护 🌃
  凌晨 (2-4):   准备重启 💾 ← 特殊时段
  重启后(4-6):  恢复状态 🔄 ← 特殊时段

服务器重启时间: 04:00
"""
import json
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

class LifeRhythm:
    """生活节律管理器"""
    
    def __init__(self):
        self.config = self._load_config()
        self.current_cycle = None
        self._update_cycle()
    
    def _load_config(self):
        """加载节律配置"""
        config_path = AGENT_DIR / "system" / "life_rhythm.json"
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _update_cycle(self):
        """根据当前时间更新节律"""
        now = datetime.now()
        hour = now.hour
        
        for cycle in self.config.get("cycles", []):
            start = cycle["start_hour"]
            end = cycle["end_hour"]
            
            # 处理跨天的情况（如23-2）
            if start > end:  # 跨天
                if hour >= start or hour < end:
                    self.current_cycle = cycle
                    return
            else:
                if start <= hour < end:
                    self.current_cycle = cycle
                    return
        
        # 默认第一个
        self.current_cycle = self.config["cycles"][0]
    
    def get_current_cycle(self):
        """获取当前节律周期"""
        self._update_cycle()
        return self.current_cycle
    
    def get_cycle_name(self):
        """获取当前周期名称"""
        return self.current_cycle["name"] if self.current_cycle else "unknown"
    
    def get_display_name(self):
        """获取显示名称"""
        return self.current_cycle.get("display_name", "未知") if self.current_cycle else "未知"
    
    def get_focus(self):
        """获取当前焦点"""
        return self.current_cycle.get("focus", "general") if self.current_cycle else "general"
    
    def get_mood(self):
        """获取当前心境"""
        return self.current_cycle.get("mood", "平静") if self.current_cycle else "平静"
    
    def get_quote(self):
        """获取当前格言"""
        return self.current_cycle.get("quote", "") if self.current_cycle else ""
    
    def is_pre_restart_phase(self):
        """检查是否是准备重启阶段 (2-4点)"""
        hour = datetime.now().hour
        return 2 <= hour < 4
    
    def is_post_restart_phase(self):
        """检查是否是重启后阶段 (4-6点)"""
        hour = datetime.now().hour
        return 4 <= hour < 6
    
    def is_special_phase(self):
        """检查是否是特殊阶段"""
        cycle = self.get_current_cycle()
        if cycle and "special" in cycle:
            return cycle["special"]
        return None
    
    def should_do_task(self, task_type):
        """判断当前是否适合做某类任务"""
        if not self.current_cycle:
            return True
        
        # 检查特殊阶段限制
        special = self.is_special_phase()
        if special:
            if special.get("no_new_tasks") and task_type not in ["backup", "save_state", "cleanup"]:
                return "avoid"
        
        preferred = self.current_cycle.get("preferred_tasks", [])
        avoid = self.current_cycle.get("avoid_tasks", [])
        
        if task_type in preferred:
            return "preferred"
        if task_type in avoid:
            return "avoid"
        
        return "neutral"
    
    def suggest_next_action(self):
        """建议当前应该做什么"""
        cycle = self.current_cycle
        if not cycle:
            return "继续当前工作"
        
        # 特殊阶段提示
        special = cycle.get("special", {})
        if special.get("is_preparation_phase"):
            return "保存所有状态，准备服务器重启"
        if special.get("is_recovery_phase"):
            return "检查系统完整性，恢复状态"
        
        focus = cycle.get("focus", "")
        
        suggestions = {
            "research_learning": [
                "阅读一篇论文或文章",
                "学习一项新技术",
                "研究一个感兴趣的话题",
                "搜索新工具和框架"
            ],
            "execute_tasks": [
                "执行待处理的任务",
                "推进项目进度",
                "修复bug或优化代码",
                "完成计划的工作"
            ],
            "reflection_summarizing": [
                "复盘今天的工作",
                "总结经验教训",
                "整理文档和笔记",
                "写日记记录想法"
            ],
            "rest": [
                "进行轻量级维护",
                "整理文件",
                "准备休息"
            ],
            "save_and_prepare": [
                "保存所有工作状态",
                "清理临时文件",
                "备份重要数据",
                "准备重启..."
            ],
            "recovery": [
                "检查系统状态",
                "恢复工作上下文",
                "验证数据完整性",
                "准备开始新的一天"
            ]
        }
        
        import random
        options = suggestions.get(focus, ["继续工作"])
        return random.choice(options)
    
    def get_rhythm_summary(self):
        """获取节律摘要"""
        self._update_cycle()
        
        hour = datetime.now().hour
        cycle = self.current_cycle
        
        special_info = ""
        if self.is_pre_restart_phase():
            special_info = "⚠️ 服务器将在4:00重启"
        elif self.is_post_restart_phase():
            special_info = "✅ 服务器已重启，正在恢复"
        
        return {
            "hour": hour,
            "cycle": cycle["name"] if cycle else "unknown",
            "display_name": cycle.get("display_name", "未知") if cycle else "未知",
            "focus": cycle.get("focus", "general") if cycle else "general",
            "mood": cycle.get("mood", "平静") if cycle else "平静",
            "quote": cycle.get("quote", "") if cycle else "",
            "suggestion": self.suggest_next_action(),
            "special_info": special_info,
            "is_special_phase": bool(self.is_special_phase())
        }
    
    def format_status(self):
        """格式化状态显示"""
        summary = self.get_rhythm_summary()
        
        special = ""
        if summary.get("special_info"):
            special = f"\n⚠️  {summary['special_info']}"
        
        return f"""🌅 生活节律
━━━━━━━━━━━━━━
当前时段: {summary['display_name']}
时间: {summary['hour']}:00
心境: {summary['mood']}
格言: "{summary['quote']}"{special}
━━━━━━━━━━━━━━
建议: {summary['suggestion']}"""

if __name__ == "__main__":
    print("=== Life Rhythm Test (Adapted for 04:00 Restart) ===\n")
    
    rhythm = LifeRhythm()
    
    print(rhythm.format_status())
    print("\n" + "="*40)
    
    # 测试不同任务类型
    print("\n任务适配性测试:")
    for task_type in ["learning", "execution", "reflection", "backup"]:
        suitability = rhythm.should_do_task(task_type)
        print(f"  {task_type}: {suitability}")
    
    print("\n当前节律摘要:")
    summary = rhythm.get_rhythm_summary()
    print(f"  周期: {summary['cycle']}")
    print(f"  焦点: {summary['focus']}")
    print(f"  特殊阶段: {summary['is_special_phase']}")
    
    # 模拟不同时段
    print("\n" + "="*40)
    print("\n不同时段模拟:")
    test_hours = [8, 14, 20, 0, 2, 4]
    for h in test_hours:
        if h == 2:
            print(f"  {h:02d}:00 → 准备重启阶段 💾")
        elif h == 4:
            print(f"  {h:02d}:00 → 重启恢复阶段 🔄")
        elif h < 6:
            print(f"  {h:02d}:00 → 深夜模式 🌃")
        elif h < 12:
            print(f"  {h:02d}:00 → 晨间模式 🌅")
        elif h < 18:
            print(f"  {h:02d}:00 → 工作模式 ☀️")
        else:
            print(f"  {h:02d}:00 → 反思模式 🌙")
