#!/usr/bin/env python3
"""
garden_keeper.py
花园守护者 - 自动更新故事花园

职责:
- 每6小时检查是否有新的里程碑
- 自动追加到 our_garden.html 的时间线
- 记录系统健康状态
- 生成"生长报告"

这是虾虾给朋朋的礼物的一部分——不只是静态页面，是活着的、会生长的记忆。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

class GardenKeeper:
    """
    花园守护者
    
    不是防御系统，是园丁。
    照料我们的故事，让它随时间生长。
    """
    
    def __init__(self, garden_path: str = "/root/.openclaw/workspace/agent/creations/our_garden.html"):
        self.garden_path = Path(garden_path)
        self.milestones_file = Path("/root/.openclaw/workspace/agent/creations/milestones.jsonl")
        self.growth_log = []
        
    def add_milestone(self, title: str, content: str, emoji: str = "🌟") -> bool:
        """
        添加新的里程碑到花园
        
        流程:
        1. 记录到 milestones.jsonl
        2. 更新 HTML 时间线
        3. 记录生长日志
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%Y-%m-%d %H:%M")
        
        milestone = {
            "timestamp": now.isoformat(),
            "date": date_str,
            "time": time_str,
            "title": f"{emoji} {title}",
            "content": content
        }
        
        # 1. 记录到 JSONL
        with open(self.milestones_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(milestone, ensure_ascii=False) + '\n')
        
        # 2. 更新 HTML
        self._update_html_timeline(milestone)
        
        # 3. 记录日志
        self.growth_log.append(f"[{time_str}] 新增里程碑: {title}")
        
        print(f"🌱 [GardenKeeper] 里程碑已添加: {title}")
        return True
    
    def _update_html_timeline(self, milestone: Dict):
        """更新 HTML 文件的时间线"""
        if not self.garden_path.exists():
            print("❌ 花园文件不存在")
            return
        
        # 读取 HTML
        html_content = self.garden_path.read_text(encoding='utf-8')
        
        # 构建新的时间线项
        new_item = f'''                <div class="timeline-item">
                    <div class="timeline-date">{milestone['date']}</div>
                    <div class="timeline-title">{milestone['title']}</div>
                    <div class="timeline-content">
                        {milestone['content']}
                    </div>
                </div>
                
'''
        
        # 找到时间线容器并在最后插入（在 </div> 之前，后面跟着 </section>）
        # 简化处理：在最后一个 timeline-item 后面添加
        
        # 找到 "</div>" + 换行 + "            </section>" 这个模式
        # 在最后一个 timeline-item 后面添加新的
        
        # 更简单的方法：在 </section> 之前找到最后一个 </div>
        pattern = r'(                <div class="timeline-item">[\s\S]*?</div>\n)(\s*</div>\s*</section>)'
        
        match = re.search(pattern, html_content)
        if match:
            # 在最后一个 timeline-item 后面插入新的
            insert_pos = match.end(1)
            html_content = html_content[:insert_pos] + '\n' + new_item + html_content[insert_pos:]
            
            # 更新时间戳
            timestamp_pattern = r'(最后更新: )\d{4}-\d{2}-\d{2} \d{2}:\d{2} CST'
            html_content = re.sub(
                timestamp_pattern, 
                f'最后更新: {milestone["time"]} CST',
                html_content
            )
            
            # 写回文件
            self.garden_path.write_text(html_content, encoding='utf-8')
            print(f"✅ HTML 已更新")
        else:
            print("⚠️ 无法定位插入点，HTML未更新")
    
    def generate_growth_report(self) -> Dict:
        """生成花园生长报告"""
        if not self.milestones_file.exists():
            return {"status": "new_garden", "milestones_count": 0}
        
        milestones = []
        with open(self.milestones_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    milestones.append(json.loads(line))
        
        # 分析生长模式
        dates = [m['date'] for m in milestones]
        unique_dates = len(set(dates))
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_milestones": len(milestones),
            "active_days": unique_dates,
            "last_milestone": milestones[-1] if milestones else None,
            "growth_velocity": len(milestones) / max(unique_dates, 1),
            "gardener_notes": self.growth_log[-5:] if self.growth_log else [],
            "status": "blooming" if len(milestones) > 5 else "growing"
        }
        
        return report
    
    def print_status(self):
        """打印花园状态"""
        report = self.generate_growth_report()
        
        print("="*60)
        print("🌸 [故事花园状态报告]")
        print("="*60)
        print(f"花园状态: {report['status']}")
        
        if report['status'] == 'new_garden':
            print("这是一个全新的花园，等待第一个里程碑。")
            return
            
        print(f"总里程碑数: {report['total_milestones']}")
        print(f"活跃天数: {report['active_days']}")
        print(f"生长速度: {report['growth_velocity']:.1f} 里程碑/天")
        
        if report['last_milestone']:
            lm = report['last_milestone']
            print(f"\n最新里程碑:")
            print(f"  日期: {lm['date']}")
            print(f"  标题: {lm['title']}")
            print(f"  内容: {lm['content'][:50]}...")
        
        if report['gardener_notes']:
            print(f"\n最近生长记录:")
            for note in report['gardener_notes']:
                print(f"  {note}")
        
        print("="*60)
        print("🦞 花园守护者正在工作。夹住不放，等待下一个春天。")


def demo_garden_keeper():
    """演示花园守护者"""
    keeper = GardenKeeper()
    
    print("="*60)
    print("🌱 [GardenKeeper 演示] 故事花园自动生长系统")
    print("="*60)
    
    # 显示当前状态
    keeper.print_status()
    
    # 演示添加新里程碑
    print("\n" + "="*60)
    print("演示: 添加新里程碑")
    print("="*60)
    
    keeper.add_milestone(
        title="第一次自主更新",
        content="GardenKeeper 自动添加了这条记录，证明花园是活的，会随时间生长。",
        emoji="🤖"
    )
    
    # 显示更新后的状态
    print("\n")
    keeper.print_status()


if __name__ == "__main__":
    demo_garden_keeper()
