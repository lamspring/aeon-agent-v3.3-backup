#!/usr/bin/env python3
"""
Weekly Reflection - 每周反思

每周日晚上8点，自动总结：
  - 本周做了什么
  - 学到了什么
  - 下周目标
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR))

def read_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def log_simple(msg):
    """简化日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file = AGENT_DIR / "logs" / "execution_log.txt"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {msg}\n")

def read_text(path, max_lines=100):
    """读取文本文件，限制行数"""
    if not path.exists():
        return ""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return ''.join(lines[-max_lines:])
    except:
        return ""

class WeeklyReflection:
    """每周反思"""
    
    def __init__(self):
        self.config = self._load_config()
        self.reflection_file = AGENT_DIR / self.config["output"]["file"]
    
    def _load_config(self):
        """加载配置"""
        config_path = AGENT_DIR / "system" / "weekly_reflection.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_this_week_range(self):
        """获取本周时间范围"""
        now = datetime.now()
        # 本周一
        monday = now - timedelta(days=now.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        # 本周日(今天)
        sunday = now
        return monday, sunday
    
    def _collect_data(self):
        """收集本周数据"""
        monday, sunday = self._get_this_week_range()
        
        data = {
            "week_range": f"{monday.strftime('%Y-%m-%d')} ~ {sunday.strftime('%Y-%m-%d')}",
            "logs": "",
            "finished_tasks": [],
            "diary": "",
            "long_term": ""
        }
        
        # 1. 执行日志 (最近200行)
        log_path = AGENT_DIR / "logs" / "execution_log.txt"
        data["logs"] = read_text(log_path, 200)
        
        # 2. 已完成的任务
        finished_path = AGENT_DIR / "tasks" / "queue" / "finished.json"
        if finished_path.exists():
            try:
                finished = read_json(finished_path)
                # 筛选本周完成的任务
                week_tasks = []
                for task in finished.get("tasks", []):
                    finished_at = task.get("finished_at", "")
                    if finished_at:
                        try:
                            task_time = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                            if monday <= task_time <= sunday:
                                week_tasks.append({
                                    "goal": task.get("goal", ""),
                                    "finished_at": finished_at,
                                    "result": task.get("result", "")[:100]  # 限制长度
                                })
                        except:
                            pass
                data["finished_tasks"] = week_tasks[-10:]  # 最近10个
            except:
                pass
        
        # 3. 日记
        diary_path = AGENT_DIR / "memory" / "diary.md"
        data["diary"] = read_text(diary_path, 50)
        
        # 4. 长期记忆
        long_term_path = AGENT_DIR / "memory" / "long_term.md"
        data["long_term"] = read_text(long_term_path, 30)
        
        return data
    
    def _build_prompt(self, data):
        """构建反思提示词"""
        prompt = self.config["reflection_prompt"]
        
        # 添加数据上下文
        context = f"""
\n=== 本周数据 ===

周期间: {data['week_range']}

【本周完成的任务】(共{len(data['finished_tasks'])}个)
"""
        if data['finished_tasks']:
            for task in data['finished_tasks']:
                context += f"\n- {task['goal']}"
        else:
            context += "\n(无)"
        
        context += f"""

【本周执行日志】
{data['logs'][:2000]}

【本周日记】
{data['diary'][:1000]}

【长期记忆参考】
{data['long_term'][:500]}

=== 请生成周报反思 ===
"""
        
        return prompt + context
    
    def run(self):
        """执行每周反思"""
        if not self.config.get("enabled", True):
            return {"status": "disabled"}
        
        # 收集数据
        data = self._collect_data()
        
        # 构建提示词
        prompt = self._build_prompt(data)
        
        # 保存提示词到临时文件 (供外部模型调用)
        temp_prompt_file = AGENT_DIR / "temp" / "weekly_reflection_prompt.txt"
        temp_prompt_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        # 记录到简化日志
        from system.simple_logger import log
        log(f"[WEEKLY_REFLECTION] 数据已收集，周期: {data['week_range']}")
        log(f"[WEEKLY_REFLECTION] 完成任务数: {len(data['finished_tasks'])}")
        log(f"[WEEKLY_REFLECTION] 提示词已保存到: {temp_prompt_file}")
        
        return {
            "status": "data_collected",
            "week_range": data['week_range'],
            "finished_tasks_count": len(data['finished_tasks']),
            "prompt_file": str(temp_prompt_file),
            "output_file": str(self.reflection_file)
        }
    
    def save_reflection(self, content: str):
        """保存反思结果"""
        # 确保目录存在
        self.reflection_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加标题
        week_title = f"## 周报 {datetime.now().strftime('%Y-%m-%d')}"
        full_content = f"\n{week_title}\n\n{content}\n{'='*40}\n"
        
        # 追加到文件
        with open(self.reflection_file, 'a', encoding='utf-8') as f:
            f.write(full_content)
        
        # 记录
        log_simple(f"[WEEKLY_REFLECTION] 周报已保存到: {self.reflection_file}")
        
        return {"status": "saved", "file": str(self.reflection_file)}

if __name__ == "__main__":
    print("=== Weekly Reflection Test ===\n")
    
    reflection = WeeklyReflection()
    result = reflection.run()
    
    print(f"状态: {result['status']}")
    print(f"周期: {result['week_range']}")
    print(f"完成任务: {result['finished_tasks_count']}")
    print(f"提示词文件: {result['prompt_file']}")
    print(f"输出文件: {result['output_file']}")
    
    # 显示提示词前500字
    if Path(result['prompt_file']).exists():
        print("\n--- 提示词预览 ---")
        with open(result['prompt_file'], 'r') as f:
            print(f.read()[:500] + "...")
