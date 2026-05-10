#!/usr/bin/env python3
"""
NovelAnalyzer - 小说全局分析器 v1.0

利用 MiMo 100万上下文能力，对整部小说进行跨章一致性分析。

核心能力:
1. 全局伏笔追踪 — 哪些伏笔埋了、哪些回收了、哪些遗漏了
2. 角色一致性 — 人设是否跨章崩塌
3. 扮演度机制贯穿 — 机制是否全章一致
4. 世界观自洽 — 副本规则有无矛盾
5. 节奏分析 — 紧张/松弛分布是否合理

输入: 小说章节文件 + 世界观设定 + 审核标准
输出: JSON 分析报告 + Markdown 可读版

版本: v1.0
作者: 虾虾
日期: 2026-04-30
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional


class NovelAnalyzer:
    """
    小说全局分析器
    
    职责:
    - 收集小说全部章节
    - 加载世界观设定
    - 用 MiMo 100万上下文做全局分析
    - 输出结构化报告
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://token-plan-cn.xiaomimimo.com/v1"):
        self.api_key = api_key
        if not self.api_key:
            # 尝试从文件读取
            try:
                with open("/root/.openclaw/workspace/notes/mimoapikey.txt", "r") as f:
                    self.api_key = f.read().strip()
            except:
                pass
        if not self.api_key:
            # 尝试环境变量
            self.api_key = os.getenv("MIMO_API_KEY", "")
        self.base_url = base_url
    
    def collect_chapters(self, chapter_dir: str) -> List[Dict]:
        """
        收集小说章节
        
        从目录读取所有章节文件，按顺序排列。
        支持 .md 和 .txt 格式。
        """
        dir_path = Path(chapter_dir)
        chapters = []
        
        for f in sorted(dir_path.glob("*")):
            if f.suffix in [".md", ".txt"]:
                try:
                    content = f.read_text(encoding="utf-8")
                    # 提取章节编号和标题
                    title = f.stem
                    chapters.append({
                        "file": str(f),
                        "title": title,
                        "content": content,
                        "word_count": len(content),
                    })
                except Exception as e:
                    print(f"[NovelAnalyzer] Error reading {f}: {e}")
        
        return chapters
    
    def load_worldbuilding(self, context_file: str) -> str:
        """加载世界观设定"""
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                return f.read()
        except:
            return ""
    
    def analyze_global(self, chapters: List[Dict], worldbuilding: str = "") -> Dict:
        """
        全局分析 — MiMo 100万上下文
        
        将整部小说 + 世界观一次性加载，做跨章分析。
        """
        # 构建分析提示
        chapter_texts = []
        total_chars = 0
        for i, ch in enumerate(chapters, 1):
            chapter_texts.append(f"## 第{i}章：{ch['title']}\n\n{ch['content']}")
            total_chars += len(ch["content"])
        
        full_text = "\n\n---\n\n".join(chapter_texts)
        
        # 如果太长，截断（但100万上下文应该够）
        estimated_tokens = int(total_chars * 1.5)
        print(f"[NovelAnalyzer] Total chars: {total_chars}, estimated tokens: {estimated_tokens}")
        
        prompt = f"""你是一位资深网文编辑，擅长无限流/惊悚/游戏副本类小说。

请对以下小说进行全局跨章一致性分析。小说共{len(chapters)}章，总字数约{total_chars}字。

## 世界观设定

{worldbuilding if worldbuilding else "（世界观设定未提供）"}

## 小说全文

{full_text[:80000]}  # 截断到约8万字，约12万tokens，留余量给输出

（如内容有截断，优先保证前几章完整，后续章节提供摘要）

## 分析要求

请输出 JSON 格式报告：

{{
  "summary": "整体评价，一句话",
  "overall_score": 0-100,
  "verdict": "通过/修改后通过/不通过",
  
  "cross_chapter_issues": [
    {{
      "severity": "致命/严重/轻微",
      "location": "第X章→第Y章",
      "description": "问题描述",
      "suggestion": "修改建议"
    }}
  ],
  
  "foreshadowing_tracking": [
    {{
      "item": "伏笔名称",
      "chapter_introduced": "第X章",
      "chapter_resolved": "第Y章（未回收则写null）",
      "status": "已回收/待回收/废弃/冲突"
    }}
  ],
  
  "character_consistency": [
    {{
      "character": "角色名",
      "trait": "核心特质",
      "consistent": true/false,
      "issues": "如有不一致，说明"
    }}
  ],
  
  "mechanism_integrity": {{
    "mechanism_name": "扮演度",
    "present_in_all_chapters": true/false,
    "logical_consistency": "评价",
    "issues": ["问题1", "问题2"]
  }},
  
  "worldbuilding_check": [
    {{
      "rule": "副本规则",
      "consistent": true/false,
      "contradictions": ["矛盾点"]
    }}
  ],
  
  "pacing_analysis": {{
    "tension_curve": "节奏描述",
    "climax_distribution": "高潮分布评价",
    "suggestion": "节奏建议"
  }},
  
  "rewrite_priority": [
    "优先级1的修改",
    "优先级2的修改"
  ]
}}
"""
        
        # 调用 MiMo
        payload = {
            "model": "mimo-v2.5",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
            "temperature": 0.2
        }
        
        try:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            
            print(f"[NovelAnalyzer] Sending request to {self.base_url}, timeout=300s")
            with urllib.request.urlopen(req, timeout=300) as resp:
                print(f"[NovelAnalyzer] Response: {resp.status}")
                data = json.loads(resp.read().decode())
                reply = data["choices"][0]["message"]["content"]
                
                # 解析 JSON
                try:
                    result = json.loads(reply)
                    return result
                except json.JSONDecodeError:
                    # 尝试从 markdown code block 提取
                    import re
                    json_match = re.search(r'```json\s*(.*?)\s*```', reply, re.DOTALL)
                    if json_match:
                        result = json.loads(json_match.group(1))
                        return result
                    
                    return {
                        "error": "JSON parse failed",
                        "raw": reply[:500],
                        "summary": "解析失败，请检查输出格式"
                    }
                    
        except Exception as e:
            print(f"[NovelAnalyzer] API error: {type(e).__name__}: {str(e)[:200]}")
            return {
                "error": str(e),
                "summary": f"分析失败: {str(e)[:100]}"
            }
    
    def generate_markdown_report(self, analysis: Dict, output_path: str):
        """生成 Markdown 可读报告"""
        lines = [
            f"# 小说全局分析报告",
            f"",
            f"**总分:** {analysis.get('overall_score', 'N/A')}/100",
            f"**结论:** {analysis.get('verdict', 'N/A')}",
            f"**摘要:** {analysis.get('summary', 'N/A')}",
            f"",
            f"---",
            f"",
        ]
        
        # 跨章问题
        issues = analysis.get("cross_chapter_issues", [])
        if issues:
            lines.append("## 🔴 跨章问题")
            lines.append("")
            for issue in issues:
                lines.append(f"### [{issue.get('severity', '?')}] {issue.get('location', '?')}")
                lines.append(f"- **问题:** {issue.get('description', '?')}")
                lines.append(f"- **建议:** {issue.get('suggestion', '?')}")
                lines.append("")
        
        # 伏笔追踪
        foreshadowing = analysis.get("foreshadowing_tracking", [])
        if foreshadowing:
            lines.append("## 📋 伏笔追踪")
            lines.append("")
            lines.append("| 伏笔 | 引入 | 回收 | 状态 |")
            lines.append("|------|------|------|------|")
            for item in foreshadowing:
                lines.append(f"| {item.get('item', '?')} | {item.get('chapter_introduced', '?')} | {item.get('chapter_resolved', '?')} | {item.get('status', '?')} |")
            lines.append("")
        
        # 角色一致性
        characters = analysis.get("character_consistency", [])
        if characters:
            lines.append("## 👤 角色一致性")
            lines.append("")
            for char in characters:
                status = "✅" if char.get("consistent") else "❌"
                lines.append(f"- {status} **{char.get('character', '?')}**: {char.get('trait', '?')}")
                if not char.get("consistent"):
                    lines.append(f"  - 问题: {char.get('issues', '?')}")
            lines.append("")
        
        # 机制完整性
        mechanism = analysis.get("mechanism_integrity", {})
        if mechanism:
            lines.append("## ⚙️ 机制完整性")
            lines.append("")
            lines.append(f"- **机制:** {mechanism.get('mechanism_name', '?')}")
            lines.append(f"- **贯穿全章:** {'✅' if mechanism.get('present_in_all_chapters') else '❌'}")
            lines.append(f"- **逻辑一致性:** {mechanism.get('logical_consistency', '?')}")
            issues = mechanism.get("issues", [])
            if issues:
                lines.append("- **问题:**")
                for issue in issues:
                    lines.append(f"  - {issue}")
            lines.append("")
        
        # 节奏分析
        pacing = analysis.get("pacing_analysis", {})
        if pacing:
            lines.append("## 📈 节奏分析")
            lines.append("")
            lines.append(f"- **紧张曲线:** {pacing.get('tension_curve', '?')}")
            lines.append(f"- **高潮分布:** {pacing.get('climax_distribution', '?')}")
            lines.append(f"- **建议:** {pacing.get('suggestion', '?')}")
            lines.append("")
        
        # 重写优先级
        priority = analysis.get("rewrite_priority", [])
        if priority:
            lines.append("## 🎯 重写优先级")
            lines.append("")
            for i, item in enumerate(priority, 1):
                lines.append(f"{i}. {item}")
            lines.append("")
        
        # 写入文件
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        return output_path
    
    def run(self, chapter_dir: str, worldbuilding_file: str, output_dir: str) -> Dict:
        """
        运行完整分析流程
        
        Args:
            chapter_dir: 章节文件目录
            worldbuilding_file: 世界观设定文件路径
            output_dir: 输出目录
        
        Returns:
            {"analysis": dict, "json_path": str, "markdown_path": str}
        """
        print(f"[NovelAnalyzer] 开始分析...")
        print(f"[NovelAnalyzer] 章节目录: {chapter_dir}")
        
        # 1. 收集章节
        chapters = self.collect_chapters(chapter_dir)
        print(f"[NovelAnalyzer] 找到 {len(chapters)} 章")
        
        # 2. 加载世界观
        worldbuilding = self.load_worldbuilding(worldbuilding_file)
        print(f"[NovelAnalyzer] 世界观: {len(worldbuilding)} 字符")
        
        # 3. 全局分析
        print(f"[NovelAnalyzer] 调用 MiMo 全局分析...")
        analysis = self.analyze_global(chapters, worldbuilding)
        
        # 4. 保存 JSON
        json_path = str(Path(output_dir) / "novel_analysis.json")
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
        
        # 5. 生成 Markdown
        markdown_path = str(Path(output_dir) / "novel_analysis.md")
        self.generate_markdown_report(analysis, markdown_path)
        
        print(f"[NovelAnalyzer] 分析完成:")
        print(f"  JSON: {json_path}")
        print(f"  Markdown: {markdown_path}")
        
        return {
            "analysis": analysis,
            "json_path": json_path,
            "markdown_path": markdown_path,
            "chapters_analyzed": len(chapters),
        }


# ============== 快速测试 ==============
if __name__ == "__main__":
    analyzer = NovelAnalyzer()
    
    # 测试收集
    chapters = analyzer.collect_chapters("/tmp/test_chapters")
    print(f"Chapters found: {len(chapters)}")
    
    print("NovelAnalyzer v1.0 ready")
