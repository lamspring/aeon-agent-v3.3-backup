#!/usr/bin/env python3
"""
Weekly Reflection Runner - 每周反思执行器

每周日晚上8点执行：
1. 收集本周数据
2. 调用AI模型生成反思
3. 保存到 weekly_reflections.md

使用方式:
  python3 run_weekly_reflection.py

cron设置 (每周日20:00):
  0 20 * * 0 cd /root/.openclaw/workspace/agent && python3 run_weekly_reflection.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
sys.path.insert(0, str(AGENT_DIR))

from system.weekly_reflection import WeeklyReflection

def main():
    print("=" * 50)
    print("🗓️  Weekly Reflection - 每周反思")
    print("=" * 50)
    print()
    
    # 1. 收集数据
    print("[1/3] 收集本周数据...")
    reflection = WeeklyReflection()
    result = reflection.run()
    
    if result["status"] == "disabled":
        print("⏸️  每周反思已禁用")
        return
    
    print(f"  ✓ 周期: {result['week_range']}")
    print(f"  ✓ 完成任务: {result['finished_tasks_count']}")
    print(f"  ✓ 提示词已生成: {result['prompt_file']}")
    print()
    
    # 2. 读取提示词
    prompt_file = Path(result['prompt_file'])
    if not prompt_file.exists():
        print("❌ 提示词文件不存在")
        return
    
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt = f.read()
    
    print("[2/3] 提示词准备完成")
    print(f"  长度: {len(prompt)} 字符")
    print()
    
    # 3. 输出提示词 (供外部模型使用)
    print("[3/3] 请使用以下提示词调用模型生成反思报告:")
    print()
    print("-" * 50)
    print(prompt)
    print("-" * 50)
    print()
    
    # 4. 保存占位符 (等待模型输出)
    output_file = Path(result['output_file'])
    placeholder = f"""## 周报 {datetime.now().strftime('%Y-%m-%d')}

⏳ 等待模型生成反思报告...

请将模型输出保存到此文件。

---
"""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(placeholder)
    
    print(f"✅ 数据收集完成!")
    print(f"📄 输出文件: {result['output_file']}")
    print()
    print("💡 下一步:")
    print("  1. 复制上面的提示词")
    print("  2. 调用AI模型生成反思")
    print("  3. 将输出保存到 weekly_reflections.md")
    print()

if __name__ == "__main__":
    main()
