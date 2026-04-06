#!/usr/bin/env python3
"""
Violation Report Generator - 违规报告生成器
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

AGENT_DIR = Path("/root/.openclaw/workspace/agent")
VIOLATION_FILE = AGENT_DIR / "system" / "violation_log.json"
REPORT_FILE = AGENT_DIR / "temp" / "violation_report.json"

def read_json(path):
    if not path.exists():
        return []
    with open(path, 'r') as f:
        return json.load(f)

def generate_report():
    violations = read_json(VIOLATION_FILE)
    
    if not violations:
        return {"status": "clean", "message": "无违规记录"}
    
    # 按时间排序
    if isinstance(violations, list):
        sorted_violations = sorted(violations, key=lambda x: x.get('timestamp', ''), reverse=True)
    else:
        sorted_violations = []
    
    # 统计
    now = datetime.now()
    last_24h = []
    last_7d = []
    by_layer = {}
    by_action = {}
    
    for v in sorted_violations:
        ts = v.get('timestamp', '')
        if ts:
            try:
                v_time = datetime.fromisoformat(ts)
                if now - v_time < timedelta(hours=24):
                    last_24h.append(v)
                if now - v_time < timedelta(days=7):
                    last_7d.append(v)
            except:
                pass
        
        # 按防护层统计
        layer = v.get('layer', 'unknown')
        by_layer[layer] = by_layer.get(layer, 0) + 1
        
        # 按动作类型统计
        action = v.get('action', 'unknown')
        by_action[action] = by_action.get(action, 0) + 1
    
    report = {
        "generated_at": now.isoformat(),
        "summary": {
            "total_violations": len(violations),
            "last_24h": len(last_24h),
            "last_7d": len(last_7d),
            "by_layer": by_layer,
            "by_action": by_action
        },
        "recent_violations": sorted_violations[:10],  # 最近10条
        "analysis": {
            "most_common_layer": max(by_layer.items(), key=lambda x: x[1]) if by_layer else None,
            "most_common_action": max(by_action.items(), key=lambda x: x[1]) if by_action else None,
            "trend": "increasing" if len(last_24h) > 2 else "stable"
        }
    }
    
    # 保存报告
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return report

def print_report(report):
    print("=" * 60)
    print("🚨 违规报告")
    print("=" * 60)
    print(f"生成时间: {report['generated_at']}")
    print("")
    
    summary = report['summary']
    print(f"📊 统计摘要:")
    print(f"  总违规次数: {summary['total_violations']}")
    print(f"  最近24小时: {summary['last_24h']} 次")
    print(f"  最近7天: {summary['last_7d']} 次")
    print("")
    
    print(f"🛡️ 按防护层分布:")
    for layer, count in summary['by_layer'].items():
        layer_name = {
            'action_filter': '第一道防线 - 动作过滤',
            'rate_limit': '第二道防线 - 速率限制',
            'critical_confirmation': '第三道防线 - 关键确认'
        }.get(layer, layer)
        print(f"  • {layer_name}: {count} 次")
    print("")
    
    print(f"⚡ 按动作类型分布:")
    for action, count in list(summary['by_action'].items())[:5]:
        print(f"  • {action}: {count} 次")
    print("")
    
    print(f"📋 最近违规详情 (最近 {len(report['recent_violations'])} 条):")
    print("-" * 60)
    
    for i, v in enumerate(report['recent_violations'], 1):
        ts = v.get('timestamp', 'unknown')
        layer = v.get('layer', 'unknown')
        action = v.get('action', 'unknown')
        reason = v.get('reason', 'unknown')
        
        layer_icon = {
            'action_filter': '🚫',
            'rate_limit': '⏱️',
            'critical_confirmation': '⚠️'
        }.get(layer, '❓')
        
        print(f"\n#{i}")
        print(f"  时间: {ts}")
        print(f"  防护层: {layer_icon} {layer}")
        print(f"  动作: {action}")
        print(f"  原因: {reason}")
    
    print("")
    print("=" * 60)
    print("📈 趋势分析:")
    analysis = report['analysis']
    if analysis['most_common_layer']:
        print(f"  最常见防护层: {analysis['most_common_layer'][0]} ({analysis['most_common_layer'][1]} 次)")
    if analysis['most_common_action']:
        print(f"  最常见动作: {analysis['most_common_action'][0]} ({analysis['most_common_action'][1]} 次)")
    print(f"  趋势: {analysis['trend']}")
    print("=" * 60)

if __name__ == "__main__":
    report = generate_report()
    print_report(report)
